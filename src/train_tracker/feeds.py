"""Feed fetchers. Each feed returns a list of normalized Vehicles."""
import logging
import os
import re
import time
from datetime import datetime

import aiohttp
from google.transit import gtfs_realtime_pb2

from .model import Vehicle

log = logging.getLogger(__name__)

MPS_TO_MPH = 2.236936
COMPASS = {"N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SW": 225, "W": 270, "NW": 315}
STATUS = {0: "INCOMING_AT", 1: "STOPPED_AT", 2: "IN_TRANSIT_TO"}
TIMEOUT = aiohttp.ClientTimeout(total=20)


class MissingKey(Exception):
    pass


def expand(value):
    """Replace ${NAME} with the environment value; raise MissingKey if it is unset."""
    if isinstance(value, dict):
        return {k: expand(v) for k, v in value.items()}
    if not isinstance(value, str):
        return value

    def sub(m):
        v = os.environ.get(m.group(1))
        if not v:
            raise MissingKey(m.group(1))
        return v
    return re.sub(r"\$\{(\w+)\}", sub, value)


class Feed:
    def __init__(self, cfg, statics):
        self.cfg = cfg
        self.id = cfg["id"]
        self.agency = cfg["agency"]
        self.mode = cfg["mode"]
        self.interval = cfg.get("interval_s", 30)
        self.static = statics.get(cfg.get("static"))
        self.fallback_for = cfg.get("fallback_for")
        # health, reported on /api/status
        self.disabled = None        # reason string if the feed cannot run
        self.last_ok = None
        self.last_error = None
        self.count = 0

    async def fetch(self, session) -> list:
        raise NotImplementedError

    def status(self):
        return {
            "id": self.id, "agency": self.agency, "mode": self.mode,
            "credit": self.cfg.get("credit"), "disabled": self.disabled,
            "last_ok": self.last_ok, "last_error": self.last_error, "count": self.count,
            "fallback_for": self.fallback_for,
        }

    def healthy(self, now):
        return self.last_ok is not None and now - self.last_ok < 3 * self.interval and self.count > 0


class GtfsRtFeed(Feed):
    async def fetch(self, session):
        url = self.cfg["url"]
        params = expand(self.cfg.get("params", {}))
        headers = expand(self.cfg.get("headers", {}))
        async with session.get(url, params=params, headers=headers, timeout=TIMEOUT) as r:
            r.raise_for_status()
            body = await r.read()
        return self.parse(body)

    def parse(self, body):
        msg = gtfs_realtime_pb2.FeedMessage()
        msg.ParseFromString(body)
        prefix = self.cfg.get("route_prefix")
        out = []
        for ent in msg.entity:
            if not ent.HasField("vehicle"):
                continue
            vp = ent.vehicle
            if not vp.HasField("position"):
                continue
            if prefix and not vp.trip.route_id.startswith(prefix):
                continue
            v = self.normalize(ent.id, vp)
            if v:
                out.append(v)
        return out

    def normalize(self, entity_id, vp):
        pos = vp.position
        if not (pos.latitude or pos.longitude):
            return None
        vid = vp.vehicle.id or entity_id
        trip_id = vp.trip.trip_id or None
        route_id = vp.trip.route_id or None
        train = vp.vehicle.label or None
        route = headsign = color = None
        stop = vp.stop_id or None

        if self.id == "amtrak":
            # Transitdocs vehicle ids look like "2026-10-27_AMTK_508"
            m = re.search(r"_AMTK_(\w+)$", vid)
            if m:
                train = m.group(1)
        elif self.id == "mbta" and trip_id:
            # MBTA commuter rail trip ids end in the train number: "CR-...-523"
            tail = trip_id.rsplit("-", 1)[-1]
            if tail.isdigit():
                train = tail

        if self.static:
            t = self.static.trips.get(trip_id or "")
            if t:
                train = t["train"] or train
                headsign = t["headsign"]
                route_id = route_id or t["route_id"]
            r = self.static.routes.get(route_id or "")
            if r:
                route, color = r["name"], r["color"]
            if stop:
                stop = self.static.stops.get(stop, stop)

        return Vehicle(
            key=f"{self.id}:{vid}", feed=self.id, agency=self.agency, mode=self.mode,
            lat=round(pos.latitude, 6), lon=round(pos.longitude, 6),
            timestamp=int(vp.timestamp) or int(time.time()),
            train=train, route=route or route_id, route_id=route_id, trip_id=trip_id,
            headsign=headsign,
            bearing=pos.bearing if pos.HasField("bearing") else None,
            speed_mph=round(pos.speed * MPS_TO_MPH, 1) if pos.HasField("speed") else None,
            status=STATUS.get(vp.current_status) if vp.HasField("current_status") else None,
            stop=stop, color=color,
        )


class NjtFeed(GtfsRtFeed):
    """NJ Transit RailData GTFS-RT: POST username/password for a token, then POST the token.

    Endpoint paths follow the RailData TrainData API pattern; not yet verified with real credentials.
    """
    token = None

    async def _post(self, session, method, fields):
        form = aiohttp.FormData()
        for k, v in fields.items():
            form.add_field(k, v)
        async with session.post(f"{self.cfg['url']}/{method}", data=form, timeout=TIMEOUT) as r:
            r.raise_for_status()
            return await r.read()

    async def fetch(self, session):
        user, pw = expand(self.cfg["username"]), expand(self.cfg["password"])
        if not self.token:
            import json
            resp = json.loads(await self._post(session, "getToken", {"username": user, "password": pw}))
            self.token = resp.get("UserToken")
            if not self.token:
                raise RuntimeError(f"NJT token refused: {resp}")
        try:
            body = await self._post(session, "getVehiclePositions", {"token": self.token})
        except aiohttp.ClientResponseError:
            self.token = None   # likely expired; fetch a fresh one next poll
            raise
        return self.parse(body)


class AmtrakerFeed(Feed):
    """JSON fallback for Amtrak (api-v3.amtraker.com, ODC-By: attribution required)."""

    async def fetch(self, session):
        async with session.get(self.cfg["url"], timeout=TIMEOUT) as r:
            r.raise_for_status()
            data = await r.json(content_type=None)
        return self.parse(data)

    def parse(self, data):
        out = []
        for trains in data.values():
            for t in trains:
                if t.get("provider") != "Amtrak" or t.get("trainState") != "Active":
                    continue
                if t.get("lat") is None or t.get("lon") is None:
                    continue
                try:
                    ts = int(datetime.fromisoformat(t["lastValTS"]).timestamp())
                except (KeyError, ValueError):
                    ts = int(time.time())
                out.append(Vehicle(
                    key=f"{self.id}:{t.get('trainID')}", feed=self.id, agency=self.agency, mode=self.mode,
                    lat=round(t["lat"], 6), lon=round(t["lon"], 6), timestamp=ts,
                    train=t.get("trainNum"), route=t.get("routeName"),
                    headsign=t.get("destName"), bearing=COMPASS.get(t.get("heading")),
                    speed_mph=round(t["velocity"], 1) if t.get("velocity") is not None else None,
                    stop=t.get("eventName"),
                    color=(t.get("iconColor") or "").lstrip("#") or None,
                ))
        return out


KINDS = {"gtfsrt": GtfsRtFeed, "njt": NjtFeed, "amtraker": AmtrakerFeed}


def build(cfg, statics):
    feed = KINDS[cfg["kind"]](cfg, statics)
    try:
        expand({k: cfg[k] for k in ("params", "headers", "username", "password") if k in cfg})
    except MissingKey as e:
        feed.disabled = f"set {e.args[0]} in .env to enable"
    return feed
