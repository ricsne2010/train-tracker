"""Poll every feed, keep one normalized vehicle cache, push diffs to browsers over WebSocket."""
import argparse
import asyncio
import errno
import json
import logging
import os
import sys
import time
from pathlib import Path

import aiohttp
from aiohttp import web

from . import __version__, narn
from . import feeds as feedmod
from .gtfs_static import load_static

PKG = Path(__file__).resolve().parent
WEB = PKG / "web"
DEFAULT_CONFIG = PKG / "feeds.json"
DEFAULT_DATA = Path.home() / ".train-tracker"
MAX_SKEW_S = 120
log = logging.getLogger("trains")


def load_dotenv(path: Path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Hub:
    def __init__(self, config):
        self.config = config
        self.stale_after = config.get("stale_after_s", 600)
        self.feeds = []
        self.vehicles = {}      # key -> vehicle json
        self.clients = set()

    def feed_status(self):
        return [f.status() for f in self.feeds]

    async def broadcast(self, msg):
        if not self.clients:
            return
        text = json.dumps(msg, separators=(",", ":"))
        for ws in list(self.clients):
            try:
                await ws.send_str(text)
            except Exception:
                self.clients.discard(ws)

    async def replace_feed(self, feed_id, vehicles):
        """Swap one feed's vehicles for a fresh list and broadcast what changed."""
        now = time.time()
        # Future timestamps are trains that have not departed yet (Transitdocs parks them at their
        # origin with the scheduled time); allow a little clock skew.
        fresh = {v.key: v.to_json() for v in vehicles if -MAX_SKEW_S <= now - v.timestamp < self.stale_after}
        old = {k for k, v in self.vehicles.items() if v["feed"] == feed_id}
        remove = sorted(old - fresh.keys())
        upsert = [v for k, v in fresh.items() if self.vehicles.get(k) != v]
        for k in remove:
            del self.vehicles[k]
        self.vehicles.update(fresh)
        await self.broadcast({"type": "update", "upsert": upsert, "remove": remove,
                              "feeds": self.feed_status(), "t": int(now)})

    def by_id(self, feed_id):
        return next((f for f in self.feeds if f.id == feed_id), None)

    async def poll_loop(self, feed, session):
        primary = self.by_id(feed.fallback_for) if feed.fallback_for else None
        if primary:
            await asyncio.sleep(primary.interval * 3)   # give the primary a chance first
        while True:
            now = time.time()
            if primary and (primary.healthy(now) or primary.disabled):
                # primary is fine: the fallback stays quiet and shows nothing
                if feed.count:
                    feed.count = 0
                    await self.replace_feed(feed.id, [])
            else:
                try:
                    vehicles = await feed.fetch(session)
                    feed.last_ok, feed.last_error, feed.count = time.time(), None, len(vehicles)
                    await self.replace_feed(feed.id, vehicles)
                except Exception as e:
                    feed.last_error = f"{type(e).__name__}: {e}"[:300]
                    log.warning("%s: %s", feed.id, feed.last_error)
                    # drop positions that have aged out while the feed is failing
                    keep = [k for k, v in self.vehicles.items()
                            if v["feed"] == feed.id and now - v["timestamp"] >= self.stale_after]
                    if keep:
                        for k in keep:
                            del self.vehicles[k]
                        await self.broadcast({"type": "update", "upsert": [], "remove": keep,
                                              "feeds": self.feed_status(), "t": int(now)})
            await asyncio.sleep(feed.interval)


async def ws_handler(request):
    hub: Hub = request.app["hub"]
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    await ws.send_json({"type": "snapshot", "vehicles": list(hub.vehicles.values()),
                        "feeds": hub.feed_status(), "t": int(time.time())})
    hub.clients.add(ws)
    try:
        async for _ in ws:
            pass    # clients do not send anything yet
    finally:
        hub.clients.discard(ws)
    return ws


async def vehicles_handler(request):
    return web.json_response(list(request.app["hub"].vehicles.values()))


async def status_handler(request):
    return web.json_response(request.app["hub"].feed_status())


async def index_handler(request):
    return web.FileResponse(WEB / "index.html")


async def track_handler(request):
    path = request.app["data_dir"] / narn.FILENAME
    if not path.exists():
        raise web.HTTPServiceUnavailable(text="track geometry is still downloading")
    return web.FileResponse(path)


async def on_startup(app):
    hub: Hub = app["hub"]
    data_dir: Path = app["data_dir"]
    session = aiohttp.ClientSession(headers={"User-Agent": f"train-tracker/{__version__}"})
    app["session"] = session
    data_dir.mkdir(parents=True, exist_ok=True)
    track = data_dir / narn.FILENAME
    for old in data_dir.glob("narn_passenger*.geojson"):
        if old != track:
            old.unlink()   # earlier track-file format
    if not track.exists():
        log.info("first run: downloading NARN passenger track (about a minute)")
        try:
            await asyncio.to_thread(narn.fetch, track)
        except Exception as e:
            log.warning("NARN download failed (%s); map will show trains without track. "
                        "Retry with: train-tracker fetch-track", e)
    statics = {}
    for cfg in hub.config["feeds"]:
        name = cfg.get("static")
        if name and name not in statics:
            statics[name] = await load_static(name, data_dir, session)
    hub.feeds = [feedmod.build(cfg, statics) for cfg in hub.config["feeds"]]
    for f in hub.feeds:
        if f.disabled:
            log.info("%s disabled: %s", f.id, f.disabled)
    app["tasks"] = [asyncio.create_task(hub.poll_loop(f, session)) for f in hub.feeds if not f.disabled]


async def on_cleanup(app):
    for t in app.get("tasks", []):
        t.cancel()
    await app["session"].close()


def make_app(config_path: Path = DEFAULT_CONFIG, data_dir: Path = DEFAULT_DATA):
    app = web.Application()
    app["hub"] = Hub(json.loads(config_path.read_text()))
    app["data_dir"] = data_dir
    app.router.add_get("/", index_handler)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/api/vehicles", vehicles_handler)
    app.router.add_get("/api/status", status_handler)
    app.router.add_get(f"/data/{narn.FILENAME}", track_handler)
    app.router.add_static("/", WEB)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def main(argv=None):
    ap = argparse.ArgumentParser(prog="train-tracker", description="Live US passenger-train map server")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__} (a Project Moon Pi project)")
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to reach it from other devices")
    ap.add_argument("--port", type=int, default=7500)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="feed definitions (default: bundled feeds.json)")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA,
                    help="downloads and .env (default: ~/.train-tracker)")
    sub = ap.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the server (default)")
    sub.add_parser("fetch-track", help="re-download NARN passenger track geometry")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.command == "fetch-track":
        narn.fetch(args.data_dir / narn.FILENAME)
        return
    log.info("US Train Tracker %s: a Project Moon Pi project", __version__)
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(args.data_dir / ".env")
    try:
        web.run_app(make_app(args.config, args.data_dir), host=args.host, port=args.port)
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        sys.exit(f"port {args.port} is already in use: stop the other server or pick another with --port")


if __name__ == "__main__":
    main()
