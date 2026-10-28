"""Static GTFS lookups (route names, train numbers, stop names) used to enrich realtime positions."""
import csv
import io
import logging
import time
import zipfile
from pathlib import Path

import aiohttp

log = logging.getLogger(__name__)

SOURCES = {
    "amtrak": "https://content.amtrak.com/content/gtfs/GTFS.zip",
}
MAX_AGE_S = 24 * 3600


class StaticGtfs:
    def __init__(self):
        self.routes = {}   # route_id -> {"name", "color"}
        self.trips = {}    # trip_id -> {"route_id", "train", "headsign"}
        self.stops = {}    # stop_id -> name

    def load(self, path: Path):
        with zipfile.ZipFile(path) as z:
            def rows(name):
                if name not in z.namelist():
                    return []
                return csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8-sig"))
            for r in rows("routes.txt"):
                self.routes[r["route_id"]] = {
                    "name": r.get("route_long_name") or r.get("route_short_name") or r["route_id"],
                    "color": (r.get("route_color") or "").strip() or None,
                }
            for r in rows("trips.txt"):
                self.trips[r["trip_id"]] = {
                    "route_id": r.get("route_id"),
                    "train": (r.get("trip_short_name") or "").strip() or None,
                    "headsign": (r.get("trip_headsign") or "").strip() or None,
                }
            for r in rows("stops.txt"):
                self.stops[r["stop_id"]] = r.get("stop_name") or r["stop_id"]
        log.info("static GTFS %s: %d routes, %d trips, %d stops",
                 path.name, len(self.routes), len(self.trips), len(self.stops))


async def load_static(name: str, data_dir: Path, session: aiohttp.ClientSession) -> StaticGtfs:
    """Download the named GTFS zip if missing or older than a day, then parse it.

    A failed download falls back to whatever copy is already on disk.
    """
    path = data_dir / f"{name}_gtfs.zip"
    if not path.exists() or time.time() - path.stat().st_mtime > MAX_AGE_S:
        try:
            async with session.get(SOURCES[name], timeout=aiohttp.ClientTimeout(total=120)) as r:
                r.raise_for_status()
                tmp = path.with_suffix(".part")
                tmp.write_bytes(await r.read())
                tmp.replace(path)
                log.info("downloaded %s", path.name)
        except Exception as e:
            log.warning("could not refresh %s GTFS: %s", name, e)
    gtfs = StaticGtfs()
    if path.exists():
        gtfs.load(path)
    return gtfs
