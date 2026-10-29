"""Static GTFS (schedules) for each railroad: route names, train numbers, stop names, stations and timetables.

Only rail is kept (route_type 2, the extended rail types 100-117, or routes the feed names as rail, since
CapMetro files its MetroRail as a tram), so agencies that publish buses and rail in
one file (MBTA, RTD, CapMetro) stay small in memory. A parsed copy is cached next to the zip, so a restart
doesn't parse the timetable again.
"""
import csv
import io
import logging
import pickle
import re
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp

log = logging.getLogger(__name__)

MAX_AGE_S = 24 * 3600
CACHE_VERSION = 4


def is_rail(route_type: str) -> bool:
    try:
        t = int(route_type)
    except (TypeError, ValueError):
        return False
    return t == 2 or 100 <= t <= 117


def secs(hms: str):
    """GTFS 'H:MM:SS' (hours can pass 24) -> seconds after the service day's noon-minus-12h, or None."""
    try:
        h, m, s = hms.strip().split(":")
        return int(h) * 3600 + int(m) * 60 + int(s)
    except (AttributeError, ValueError):
        return None


def clean_train(label):
    """A public train number from a label: "Train 412" -> "412"; labels that are really names -> None."""
    label = re.sub(r"^train\s*", "", (label or "").strip(), flags=re.I)
    return label if label and len(label) <= 8 and " " not in label else None


class StaticGtfs:
    def __init__(self):
        self.tz = "America/New_York"
        self.routes = {}      # route_id -> {"name", "color"}
        self.trips = {}       # trip_id -> {"route_id", "train", "headsign"}
        self.stops = {}       # stop_id -> {"name", "lat", "lon", "station"}  (station: the parent station's id)
        self.times = {}       # trip_id -> {stop_id: (arrival secs, departure secs)}
        self.stations = {}    # station id -> {"name", "lat", "lon", "routes": [route names]}
        self.by_train = {}    # train number -> a trip_id running it (for feeds whose trip ids aren't the timetable's)

    def trip_for(self, trip_id, train=None):
        """The timetable's trip_id for a live train: its own trip_id, or one with the same train number."""
        if trip_id in self.trips:
            return trip_id
        return self.by_train.get(train) if train else None

    def stop_name(self, stop_id):
        s = self.stops.get(stop_id)
        return s["name"] if s else stop_id

    def station_of(self, stop_id):
        s = self.stops.get(stop_id)
        return s["station"] if s else stop_id

    def scheduled(self, trip_id, stop_id, service_date=None, near=None):
        """Scheduled unix time at a stop, or None. service_date 'YYYYMMDD'; without it, the service day
        (today or yesterday, local) that puts the time nearest `near` is used."""
        t = self.times.get(trip_id, {}).get(stop_id)
        if not t:
            return None
        s = t[0] if t[0] is not None else t[1]
        if s is None:
            return None
        tz = ZoneInfo(self.tz)
        if service_date:
            days = [datetime.strptime(service_date, "%Y%m%d").date()]
        else:
            today = datetime.fromtimestamp(near or time.time(), tz).date()
            days = [today, today - timedelta(days=1)]
        # a GTFS service day's times count from noon minus 12 h (which is midnight except on DST change days)
        cands = [datetime(d.year, d.month, d.day, 12, tzinfo=tz).timestamp() - 43200 + s for d in days]
        return min(cands, key=lambda c: abs(c - (near or time.time())))

    def load(self, zpath: Path, inner=None, rail_routes=()):
        with zipfile.ZipFile(zpath) as outer:
            z = zipfile.ZipFile(io.BytesIO(outer.read(inner))) if inner else outer
            names = set(z.namelist())

            def rows(name):
                if name not in names:
                    return []
                return csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8-sig"))

            for r in rows("agency.txt"):
                self.tz = (r.get("agency_timezone") or self.tz).strip()
                break
            for r in rows("routes.txt"):
                if not is_rail(r.get("route_type")) and r["route_id"] not in rail_routes:
                    continue
                self.routes[r["route_id"]] = {
                    "name": (r.get("route_long_name") or r.get("route_short_name") or r["route_id"]).strip(),
                    "color": (r.get("route_color") or "").strip() or None,
                }
            for r in rows("trips.txt"):
                if r.get("route_id") not in self.routes:
                    continue
                self.trips[r["trip_id"]] = {
                    "route_id": r["route_id"],
                    "train": clean_train(r.get("trip_short_name")),
                    "headsign": (r.get("trip_headsign") or "").strip() or None,
                }
            for tid, t in self.trips.items():
                if t["train"]:
                    self.by_train.setdefault(t["train"], tid)
            for r in rows("stop_times.txt"):
                tid = r.get("trip_id")
                if tid in self.trips:
                    self.times.setdefault(tid, {})[r["stop_id"]] = (secs(r.get("arrival_time")),
                                                                    secs(r.get("departure_time")))
            for r in rows("stops.txt"):
                try:
                    lat, lon = float(r["stop_lat"]), float(r["stop_lon"])
                except (KeyError, ValueError):
                    lat = lon = None
                self.stops[r["stop_id"]] = {"name": (r.get("stop_name") or r["stop_id"]).strip(), "lat": lat,
                                            "lon": lon, "station": (r.get("parent_station") or "").strip() or r["stop_id"]}

        # stations: every stop a rail trip calls at, folded into its parent station
        served = {}
        for tid, stops in self.times.items():
            route = self.routes[self.trips[tid]["route_id"]]["name"]
            for sid in stops:
                served.setdefault(self.station_of(sid), set()).add(route)
        for st, routes in served.items():
            s = self.stops.get(st)
            if s and s["lat"] is not None:
                self.stations[st] = {"name": s["name"], "lat": s["lat"], "lon": s["lon"], "routes": sorted(routes)}
        # keep only the stops rail uses (bus-heavy files have tens of thousands)
        keep = {sid for stops in self.times.values() for sid in stops} | set(self.stations)
        self.stops = {k: v for k, v in self.stops.items() if k in keep}
        log.info("static GTFS %s: %d rail routes, %d trips, %d stations",
                 zpath.name, len(self.routes), len(self.trips), len(self.stations))
        return self


def _parse_cached(zpath: Path, inner, rail_routes):
    cache = zpath.with_suffix(".parsed")
    stamp = (CACHE_VERSION, zpath.stat().st_mtime, inner, tuple(rail_routes))
    try:
        with cache.open("rb") as f:
            saved_stamp, state = pickle.load(f)
        if saved_stamp == stamp:
            g = StaticGtfs()
            g.__dict__.update(state)
            return g
    except Exception:
        pass
    g = StaticGtfs().load(zpath, inner, rail_routes)
    tmp = cache.with_suffix(".part")
    with tmp.open("wb") as f:
        pickle.dump((stamp, g.__dict__), f)
    tmp.replace(cache)
    return g


async def load_static(name: str, spec: dict, data_dir: Path, session: aiohttp.ClientSession):
    """Download one railroad's GTFS zip if missing or over a day old, then parse it (in a thread).

    spec: {"url": ..., "inner": optional zip-inside-the-zip, "rail_routes": route ids to keep whatever their type}. A failed download falls back to the copy on
    disk. Returns None when there's no copy at all.
    """
    import asyncio
    path = data_dir / f"{name}_gtfs.zip"
    if not path.exists() or time.time() - path.stat().st_mtime > MAX_AGE_S:
        try:
            async with session.get(spec["url"], timeout=aiohttp.ClientTimeout(total=300)) as r:
                r.raise_for_status()
                tmp = path.with_suffix(".part")
                tmp.write_bytes(await r.read())
                tmp.replace(path)
                log.info("downloaded %s", path.name)
        except Exception as e:
            log.warning("could not refresh %s schedule: %s", name, e)
    if not path.exists():
        return None
    try:
        return await asyncio.to_thread(_parse_cached, path, spec.get("inner"), spec.get("rail_routes", ()))
    except Exception as e:
        log.warning("could not read %s schedule: %s", name, e)
        return None
