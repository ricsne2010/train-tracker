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

from . import __version__, narn, settings
from . import feeds as feedmod
from .gtfs_static import load_static

PKG = Path(__file__).resolve().parent
WEB = PKG / "web"
DEFAULT_CONFIG = PKG / "feeds.json"
DEFAULT_DATA = Path.home() / ".train-tracker"
CELL_MAX_AGE_S = 90 * 24 * 3600   # NARN is updated a few times a year
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
        self.tasks = {}         # feed id -> poll task
        self.statics = {}
        self.session = None

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

    def start(self, feed):
        if not feed.disabled:
            self.tasks[feed.id] = asyncio.create_task(self.poll_loop(feed, self.session))

    async def reload_feed(self, feed_id):
        """Rebuild one feed from its config (e.g. after its API key changed) and restart its polling."""
        cfg = next(c for c in self.config["feeds"] if c["id"] == feed_id)
        task = self.tasks.pop(feed_id, None)
        if task:
            task.cancel()
        new = feedmod.build(cfg, self.statics)
        self.feeds = [new if f.id == feed_id else f for f in self.feeds]
        await self.replace_feed(feed_id, [])
        self.start(new)

    async def poll_loop(self, feed, session):
        if feed.fallback_for and self.by_id(feed.fallback_for):
            await asyncio.sleep(self.by_id(feed.fallback_for).interval * 3)   # give the primary a chance first
        while True:
            now = time.time()
            primary = self.by_id(feed.fallback_for) if feed.fallback_for else None
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
                    feed.last_error = feedmod.describe_error(feed.agency, e)[:300]
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
    await ws.send_json({"type": "snapshot", "version": __version__, "vehicles": list(hub.vehicles.values()),
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


def geojson_response(data: bytes, max_age: int):
    resp = web.Response(body=data, content_type="application/geo+json",
                        headers={"Cache-Control": f"max-age={max_age}"})
    resp.enable_compression()
    return resp


async def track_handler(request):
    path = request.app["data_dir"] / narn.FILENAME
    if not path.exists():
        raise web.HTTPServiceUnavailable(text="track geometry is still downloading")
    return geojson_response(path.read_bytes(), 3600)


async def lines_handler(request):
    """Freight and other track for one map cell, fetched from NARN once and cached on disk."""
    cx, cy = int(request.match_info["cx"]), int(request.match_info["cy"])
    if not (-360 <= cx < 0 and 0 <= cy < 180):   # western / northern hemisphere cells only
        raise web.HTTPBadRequest(text="cell outside North America")
    path = request.app["data_dir"] / "narn_cells" / f"{cx}_{cy}.geojson"
    locks = request.app["cell_locks"]
    async with locks.setdefault((cx, cy), asyncio.Lock()):
        if not path.exists() or time.time() - path.stat().st_mtime > CELL_MAX_AGE_S:
            try:
                fc = await narn.fetch_cell(request.app["session"], cx, cy)
            except Exception as e:
                log.warning("NARN cell %d,%d: %s", cx, cy, e)
                if not path.exists():
                    raise web.HTTPBadGateway(text="could not load track for this area")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".part")
                tmp.write_text(json.dumps(fc, separators=(",", ":")))
                tmp.replace(path)
    return geojson_response(path.read_bytes(), 86400)


async def on_startup(app):
    hub: Hub = app["hub"]
    data_dir: Path = app["data_dir"]
    session = aiohttp.ClientSession(headers={"User-Agent": f"train-tracker/{__version__}"})
    app["session"] = hub.session = session
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
    for cfg in hub.config["feeds"]:
        name = cfg.get("static")
        if name and name not in hub.statics:
            hub.statics[name] = await load_static(name, data_dir, session)
    hub.feeds = [feedmod.build(cfg, hub.statics) for cfg in hub.config["feeds"]]
    for f in hub.feeds:
        if f.disabled:
            log.info("%s disabled: %s", f.id, f.disabled)
        hub.start(f)


async def on_cleanup(app):
    for t in app["hub"].tasks.values():
        t.cancel()
    await app["session"].close()


def make_app(config_path: Path = DEFAULT_CONFIG, data_dir: Path = DEFAULT_DATA, allow_remote_settings=False):
    app = web.Application()
    app["hub"] = Hub(json.loads(config_path.read_text()))
    app["data_dir"] = data_dir
    app["cell_locks"] = {}
    app["allow_remote_settings"] = allow_remote_settings
    settings.add_routes(app)
    app.router.add_get("/", index_handler)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/api/vehicles", vehicles_handler)
    app.router.add_get("/api/status", status_handler)
    app.router.add_get(f"/data/{narn.FILENAME}", track_handler)
    app.router.add_get(r"/api/lines/{cx:-?\d+}/{cy:-?\d+}", lines_handler)
    app.router.add_static("/", WEB)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def main(argv=None):
    ap = argparse.ArgumentParser(prog="train-tracker", description="Live US passenger-train map server")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__} - Designed and Created by Project Moon Pi")
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to reach it from other devices")
    ap.add_argument("--port", type=int, default=7500)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="feed definitions (default: bundled feeds.json)")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA,
                    help="downloads and .env (default: ~/.train-tracker)")
    ap.add_argument("--allow-remote-settings", action="store_true",
                    help="let other devices change API keys on the settings page (default: this computer only)")
    sub = ap.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the server (default)")
    sub.add_parser("fetch-track", help="re-download NARN passenger track geometry")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.command == "fetch-track":
        narn.fetch(args.data_dir / narn.FILENAME)
        return
    log.info("US Train Tracker %s - Designed and Created by Project Moon Pi", __version__)
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(args.data_dir / ".env")
    try:
        web.run_app(make_app(args.config, args.data_dir, args.allow_remote_settings), host=args.host, port=args.port)
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        sys.exit(f"port {args.port} is already in use: stop the other server or pick another with --port")


if __name__ == "__main__":
    main()
