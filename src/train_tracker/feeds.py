"""Feed fetchers. Each feed returns a list of normalized Vehicles."""
import asyncio
import logging
import os
import re
import time
from datetime import datetime

import aiohttp
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from . import realtime
from .gtfs_static import clean_train
from .model import Vehicle

log = logging.getLogger(__name__)

MPS_TO_MPH = 2.236936
COMPASS = {"N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SW": 225, "W": 270, "NW": 315}
STATUS = {0: "INCOMING_AT", 1: "STOPPED_AT", 2: "IN_TRANSIT_TO"}
TIMEOUT = aiohttp.ClientTimeout(total=20)
ALERTS_EVERY_S = 300


class MissingKey(Exception):
    pass


def expand(value, env=None):
    """Replace ${NAME} with the environment value; raise MissingKey if it is unset."""
    env = os.environ if env is None else env
    if isinstance(value, dict):
        return {k: expand(v, env) for k, v in value.items()}
    if not isinstance(value, str):
        return value

    def sub(m):
        v = env.get(m.group(1))
        if not v:
            raise MissingKey(m.group(1))
        return v
    return re.sub(r"\$\{(\w+)\}", sub, value)


def describe_error(agency, e) -> str:
    """A short, plain-English reason a feed fetch failed."""
    if isinstance(e, MissingKey):
        return f"Fill in {e.args[0]} first."
    if isinstance(e, aiohttp.ClientResponseError):
        if e.status in (401, 403):
            return f"{agency} turned this key down (HTTP {e.status}). Check it was copied in full."
        return f"{agency} answered with an error (HTTP {e.status})."
    if isinstance(e, asyncio.TimeoutError):
        return f"No answer from {agency} within 20 seconds."
    if isinstance(e, aiohttp.ClientError):
        return f"Couldn't reach {agency} ({type(e).__name__})."
    if isinstance(e, DecodeError):
        return f"{agency} answered, but not with train data."
    return f"{type(e).__name__}: {e}"


class Feed:
    def __init__(self, cfg, statics):
        self.cfg = cfg
        self.id = cfg["id"]
        self.agency = cfg["agency"]
        self.mode = cfg["mode"]
        self.interval = cfg.get("interval_s", 30)
        self.statics = statics      # shared, filled in the background as each railroad's schedule loads
        self.fallback_for = cfg.get("fallback_for")
        self.trips = {}             # trip_id -> realtime.trip_state, from the latest trip updates
        self.alerts = []            # active service alerts (realtime.parse_alert)
        self.alerts_at = 0
        self.env = None             # environment for ${KEY} placeholders (None: os.environ)
        # health, reported on /api/status
        self.disabled = None        # reason string if the feed cannot run
        self.last_ok = None
        self.last_error = None
        self.count = 0

    @property
    def static(self):
        return self.statics.get(self.id) if self.cfg.get("static") else None

    def wants_route(self, route_id):
        """Whether a route belongs on this map (feeds shared with buses or subways name their rail routes;
        a vehicle with no route in such a feed is left out)."""
        prefix, ids = self.cfg.get("route_prefix"), self.cfg.get("route_ids")
        if prefix and not (route_id or "").startswith(prefix):
            return False
        return not ids or route_id in ids

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
    async def get(self, session, url):
        params = expand(self.cfg.get("params", {}), self.env)
        headers = expand(self.cfg.get("headers", {}), self.env)
        async with session.get(url, params=params, headers=headers, timeout=TIMEOUT) as r:
            r.raise_for_status()
            return await r.read()

    async def extra(self, session, key):
        """A feed's separate trip-update or alert feed; a failure there only costs that extra, not the trains."""
        try:
            return await self.get(session, self.cfg[key])
        except Exception as e:
            log.info("%s %s: %s", self.id, key, describe_error(self.agency, e))
            return None

    async def fetch(self, session):
        body = await self.get(session, self.cfg["url"])
        tu = await self.extra(session, "trip_updates_url") if self.cfg.get("trip_updates_url") else None
        alerts = None
        if self.cfg.get("alerts_url") and time.time() - self.alerts_at > ALERTS_EVERY_S:
            alerts = await self.extra(session, "alerts_url")
        return self.parse(body, tu, alerts)

    def parse(self, body, tu_body=None, alerts_body=None):
        """Vehicles from `body`. Trip updates and alerts come from `body` too, unless the railroad publishes
        them separately (trip_updates_url, alerts_url); when such a fetch fails, the last good copy is kept."""
        def read(b):
            m = gtfs_realtime_pb2.FeedMessage()
            m.ParseFromString(b)
            return m
        main = read(body)
        tu_msg = read(tu_body) if tu_body else (None if self.cfg.get("trip_updates_url") else main)
        al_msg = read(alerts_body) if alerts_body else (None if self.cfg.get("alerts_url") else main)

        if tu_msg is not None:
            trips = {}
            for ent in tu_msg.entity:
                if ent.HasField("trip_update"):
                    if self.wants_route(ent.trip_update.trip.route_id or None):
                        t = realtime.trip_state(ent.trip_update, ent.id)
                        if self.static:   # Metro-North's trip ids aren't the timetable's; its entity ids are train numbers
                            t["sched"] = self.static.trip_for(t["trip_id"], ent.id)
                        if t["trip_id"]:
                            trips[t["trip_id"]] = t
            self.trips = trips
        if al_msg is not None:
            alerts = [realtime.parse_alert(ent) for ent in al_msg.entity if ent.HasField("alert")]
            self.alerts = [a for a in alerts if a and self.alert_is_ours(a)]
            self.alerts_at = time.time()
        by_vehicle = {t["vehicle_id"]: t for t in self.trips.values() if t["vehicle_id"]}
        by_entity = {t["entity"]: t for t in self.trips.values() if t["entity"]}

        out = []
        for ent in main.entity:
            if not ent.HasField("vehicle"):
                continue
            vp = ent.vehicle
            if not vp.HasField("position"):
                continue
            if not self.wants_route(vp.trip.route_id or None):
                continue
            v = self.normalize(ent.id, vp)
            if v:
                trip = (self.trips.get(v.trip_id or "") or by_vehicle.get(vp.vehicle.id)
                        or by_entity.get(v.trip_id or ""))
                if trip:
                    if self.static and not trip["sched"]:
                        trip["sched"] = self.static.trip_for(trip["trip_id"], v.train)
                    for k, val in realtime.progress(trip, self.static).items():
                        setattr(v, k, val)
                out.append(v)
        return out

    def alert_is_ours(self, a):
        """Keep alerts about this railroad's trains, not the buses or subway sharing the feed."""
        static = self.static
        mixed = bool(self.cfg.get("route_prefix") or self.cfg.get("route_ids"))
        if any(self.wants_route(r) and (not static or not static.routes or r in static.routes) for r in a["routes"]):
            return True
        if static and any(s in static.stops for s in a["stops"]):
            return True
        if any(t in self.trips or static and t in static.trips for t in a["trips"]):
            return True
        return a["agency_wide"] and not mixed

    def normalize(self, entity_id, vp):
        pos = vp.position
        if not (pos.latitude or pos.longitude):
            return None
        vid = vp.vehicle.id or entity_id
        trip_id = vp.trip.trip_id or None
        route_id = vp.trip.route_id or None
        train = vp.vehicle.label or None    # usually the train number; some feeds put car numbers here
        route = headsign = color = cars = None
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
        elif self.id == "septa":
            # SEPTA labels list the car numbers ("333,332,135,136"); trip ids start with line + train ("WAR416_")
            if train and "," in train:
                cars = len(train.split(","))
            m = re.match(r"[A-Z]+(\d+)_", trip_id or "")
            train = m.group(1) if m else None
        elif self.id == "lirr":
            # LIRR labels are car numbers; trip ids carry the train number ("GO202_26_718_2")
            m = re.match(r"GO\d+_\d+_(\d+)", trip_id or "")
            train = m.group(1) if m else None

        train = clean_train(train) if self.cfg.get("train_labels", True) else None
        if self.static:
            t = self.static.trips.get(self.static.trip_for(trip_id, train) or "")
            if t:
                train = train or t["train"]
                headsign = t["headsign"]
                route_id = route_id or t["route_id"]
            r = self.static.routes.get(route_id or "")
            if r:
                route, color = r["name"], r["color"]
            if stop:
                stop = self.static.stop_name(stop)

        return Vehicle(
            key=f"{self.id}:{vid}", feed=self.id, agency=self.agency, mode=self.mode,
            lat=round(pos.latitude, 6), lon=round(pos.longitude, 6),
            timestamp=int(vp.timestamp) or int(time.time()),
            train=train, route=route or route_id, route_id=route_id, trip_id=trip_id,
            headsign=headsign,
            bearing=pos.bearing if pos.HasField("bearing") else None,
            speed_mph=round(pos.speed * MPS_TO_MPH, 1) if pos.HasField("speed") else None,
            status=STATUS.get(vp.current_status) if vp.HasField("current_status") else None,
            stop=stop, color=color, cars=cars,
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
        user, pw = expand(self.cfg["username"], self.env), expand(self.cfg["password"], self.env)
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
