"""Poll every feed, keep one normalized vehicle cache, push diffs to browsers over WebSocket."""
import argparse
import asyncio
import errno
import json
import logging
import mimetypes
import os
import sys
import time
from pathlib import Path

import aiohttp
from aiohttp import web

from . import __version__, narn, net, realtime, settings
from . import feeds as feedmod
from .gtfs_static import load_static

PKG = Path(__file__).resolve().parent
WEB = PKG / "web"
DEFAULT_CONFIG = PKG / "feeds.json"
DEFAULT_DATA = Path.home() / ".train-tracker"
CELL_MAX_AGE_S = 90 * 24 * 3600   # NARN is updated a few times a year
MAX_SKEW_S = 120
TRAIL_S = 15 * 60                  # how far back each train's trail goes
STATIC_REFRESH_S = 6 * 3600        # how often to check for new schedules
log = logging.getLogger("trains")
mimetypes.add_type("application/manifest+json", ".webmanifest")


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
        self.statics = {}       # feed id -> StaticGtfs, filled in the background
        self.session = None
        self.trails = {}        # key -> [[lon, lat, t], ...] over the last TRAIL_S
        self.stations_fc = None # GeoJSON of every railroad's stations, rebuilt when schedules load
        self.sent_alerts = {}   # feed id -> alerts last sent to browsers

    def all_alerts(self):
        return {f.id: f.alerts for f in self.feeds if f.alerts}

    async def send_alerts_if_changed(self, feed):
        if self.sent_alerts.get(feed.id, []) != feed.alerts:
            self.sent_alerts[feed.id] = feed.alerts
            await self.broadcast({"type": "alerts", "alerts": self.all_alerts()})

    def stations(self):
        if self.stations_fc is None:
            feats = []
            for f in self.feeds:
                st = f.static
                if not st or f.fallback_for:
                    continue
                for sid, s in st.stations.items():
                    feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
                                  "properties": {"feed": f.id, "id": sid, "name": s["name"], "agency": f.agency,
                                                 "routes": ", ".join(s["routes"][:6])}})
            self.stations_fc = {"type": "FeatureCollection", "features": feats}
        return self.stations_fc

    def station_board(self, feed_id, station_id, limit=12):
        """Upcoming trains at one station, from the railroad's live trip updates."""
        feed = self.by_id(feed_id)
        static = feed.static if feed else None
        if not static or station_id not in static.stations:
            return None
        now = time.time()
        live = {v["trip_id"]: v for v in self.vehicles.values() if v["feed"] == feed_id and v.get("trip_id")}
        rows = []
        for trip in feed.trips.values():
            for stop in trip["stops"]:
                if static.station_of(stop[0]) != station_id:
                    continue
                t = stop[1] or stop[2]
                if not t or t < now - 60:
                    break
                info = static.trips.get(trip["sched"] or trip["trip_id"], {})
                v = live.get(trip["trip_id"]) or live.get(trip["entity"]) or {}
                # where the train ends: the timetable's last stop (Metro-North only predicts the next few)
                planned = static.times.get(trip["sched"] or trip["trip_id"])
                last = max(planned, key=lambda s: planned[s][0] or planned[s][1] or 0) if planned else trip["stops"][-1][0]
                ends_here = static.station_of(last) == station_id
                rows.append({
                    "time": t, "delay": realtime.stop_delay(trip, stop, static, now), "ends_here": ends_here,
                    "train": v.get("train") or info.get("train"), "key": v.get("key"),
                    "route": static.routes.get(trip["route_id"] or info.get("route_id"), {}).get("name"),
                    "headsign": info.get("headsign") or (None if ends_here else static.stop_name(last)),
                })
                break
        rows.sort(key=lambda r: r["time"])
        st = static.stations[station_id]
        here = {sid for sid, s in static.stops.items() if s["station"] == station_id} | {station_id}
        alerts = [a for a in feed.alerts if here & set(a["stops"])]
        return {"feed": feed_id, "agency": feed.agency, "id": station_id, "name": st["name"],
                "routes": st["routes"], "trains": rows[:limit], "alerts": alerts,
                "live": bool(feed.trips), "t": int(now)}

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
            self.trails.pop(k, None)
        self.vehicles.update(fresh)
        for k, v in fresh.items():
            trail = self.trails.setdefault(k, [])
            point = [v["lon"], v["lat"], v["timestamp"]]
            if not trail or trail[-1][:2] != point[:2]:
                trail.append(point)
            while trail and trail[0][2] < now - TRAIL_S:
                trail.pop(0)
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
                    await self.send_alerts_if_changed(feed)
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
                        "feeds": hub.feed_status(), "alerts": hub.all_alerts(), "trails": hub.trails,
                        "t": int(time.time())})
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


async def info_handler(request):
    """Version, and the address phones on this network can use (when the server listens beyond this computer)."""
    return web.json_response({"version": __version__, "phone_url": request.app.get("phone_url")})


async def alerts_handler(request):
    return web.json_response(request.app["hub"].all_alerts())


async def stations_handler(request):
    resp = web.json_response(request.app["hub"].stations(), content_type="application/geo+json")
    resp.enable_compression()
    return resp


async def station_handler(request):
    board = request.app["hub"].station_board(request.match_info["feed"], request.match_info["id"])
    if board is None:
        raise web.HTTPNotFound(text="no such station (or its schedule hasn't loaded yet)")
    return web.json_response(board)


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
    session = aiohttp.ClientSession(headers={"User-Agent": f"train-tracker/{__version__}"},
                                    connector=aiohttp.TCPConnector(ssl=net.ssl_context()))
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
    hub.feeds = [feedmod.build(cfg, hub.statics) for cfg in hub.config["feeds"]]
    for f in hub.feeds:
        if f.disabled:
            log.info("%s disabled: %s", f.id, f.disabled)
        hub.start(f)
    hub.tasks["_schedules"] = asyncio.create_task(schedules_loop(hub, data_dir, session))


async def schedules_loop(hub, data_dir, session):
    """Load each railroad's schedule (stop names, stations, timetables) one at a time, without holding up
    the trains, and check for new ones every few hours."""
    while True:
        for cfg in hub.config["feeds"]:
            spec = cfg.get("static")
            if not spec:
                continue
            try:
                spec = {k: feedmod.expand(v) for k, v in spec.items()}
                spec.setdefault("rail_routes", cfg.get("route_ids", ()))
            except feedmod.MissingKey:
                continue    # this schedule needs the railroad's API key
            static = await load_static(cfg["id"], spec, data_dir, session)
            if static and hub.statics.get(cfg["id"]) is not static:
                hub.statics[cfg["id"]] = static
                hub.stations_fc = None
                await hub.broadcast({"type": "stations"})
        await asyncio.sleep(STATIC_REFRESH_S)


async def on_cleanup(app):
    for t in app["hub"].tasks.values():
        t.cancel()
    await app["session"].close()


def make_app(config_path: Path = DEFAULT_CONFIG, data_dir: Path = DEFAULT_DATA, allow_remote_settings=False,
             phone_url=None):
    app = web.Application()
    app["phone_url"] = phone_url
    app["hub"] = Hub(json.loads(config_path.read_text()))
    app["data_dir"] = data_dir
    app["cell_locks"] = {}
    app["allow_remote_settings"] = allow_remote_settings
    settings.add_routes(app)
    app.router.add_get("/", index_handler)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/api/vehicles", vehicles_handler)
    app.router.add_get("/api/status", status_handler)
    app.router.add_get("/api/info", info_handler)
    app.router.add_get("/api/alerts", alerts_handler)
    app.router.add_get("/api/stations", stations_handler)
    app.router.add_get("/api/station/{feed}/{id}", station_handler)
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
    ap.add_argument("--open", action="store_true", help="open the map in your web browser once it's running")
    ap.add_argument("--log-file", type=Path, help="write messages to this file (for running in the background)")
    ap.add_argument("--allow-remote-settings", action="store_true",
                    help="let other devices change API keys on the settings page (default: this computer only)")
    sub = ap.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the server (default)")
    sub.add_parser("fetch-track", help="re-download NARN passenger track geometry")
    args = ap.parse_args(argv)

    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    if args.log_file:
        from logging.handlers import RotatingFileHandler
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(args.log_file, maxBytes=2_000_000, backupCount=1, encoding="utf-8")
        logging.basicConfig(level=logging.INFO, format=fmt, handlers=[handler])
        logging.getLogger("aiohttp.access").setLevel(logging.WARNING)   # one line per page request is noise here
    else:
        logging.basicConfig(level=logging.INFO, format=fmt)
    if args.command == "fetch-track":
        narn.fetch(args.data_dir / narn.FILENAME)
        return
    log.info("US Train Tracker %s - Designed and Created by Project Moon Pi", __version__)
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(args.data_dir / ".env")
    phone_url = None
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        ip = net.lan_address() if args.host in ("0.0.0.0", "::", "") else args.host
        if ip:
            phone_url = f"http://{ip}:{args.port}"
            log.info("On a phone or tablet on this network, open %s", phone_url)
    app = make_app(args.config, args.data_dir, args.allow_remote_settings, phone_url)
    if args.open:
        async def open_browser(app):
            import webbrowser
            asyncio.get_running_loop().call_later(1.0, webbrowser.open, f"http://127.0.0.1:{args.port}")
        app.on_startup.append(open_browser)
    try:
        web.run_app(app, host=args.host, port=args.port)
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        sys.exit(f"port {args.port} is already in use: stop the other server or pick another with --port")


if __name__ == "__main__":
    main()
