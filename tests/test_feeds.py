import time

from google.transit import gtfs_realtime_pb2

from train_tracker.feeds import AmtrakerFeed, GtfsRtFeed, build
from train_tracker.gtfs_static import StaticGtfs


def cfg(**kw):
    base = {"id": "test", "agency": "Test", "kind": "gtfsrt", "mode": "commuter", "url": "http://x"}
    base.update(kw)
    return base


def feed_bytes(*vehicles):
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    for i, (vid, route_id, trip_id, lat, lon, extra) in enumerate(vehicles):
        e = msg.entity.add(id=f"e{i}")
        v = e.vehicle
        v.vehicle.id = vid
        v.trip.route_id = route_id
        v.trip.trip_id = trip_id
        v.position.latitude, v.position.longitude = lat, lon
        v.timestamp = int(time.time())
        for k, val in extra.items():
            if k in ("bearing", "speed"):
                setattr(v.position, k, val)
            else:
                setattr(v, k, val)
    msg.entity.add(id="alert-only")   # entities without a vehicle are skipped
    return msg.SerializeToString()


def amtrak_static():
    s = StaticGtfs()
    s.routes["60"] = {"name": "Amtrak Cascades", "color": "CAE4F1"}
    s.trips["304454"] = {"route_id": "60", "train": "511", "headsign": "Portland"}
    s.stops["KEL"] = "Kelso-Longview"
    return s


def test_amtrak_enriched_from_static():
    f = GtfsRtFeed(cfg(id="amtrak", agency="Amtrak", mode="intercity"), {})
    f.static = amtrak_static()
    body = feed_bytes(("2026-10-27_AMTK_511", "60", "304454", 46.25, -122.89,
                       {"bearing": 225, "speed": 29.14, "stop_id": "KEL", "current_status": 2}))
    [v] = f.parse(body)
    assert v.key == "amtrak:2026-10-27_AMTK_511"
    assert (v.train, v.route, v.headsign, v.stop) == ("511", "Amtrak Cascades", "Portland", "Kelso-Longview")
    assert v.speed_mph == 65.2
    assert v.bearing == 225
    assert v.status == "IN_TRANSIT_TO"


def test_amtrak_train_number_from_vehicle_id_without_static():
    f = GtfsRtFeed(cfg(id="amtrak"), {})
    [v] = f.parse(feed_bytes(("2026-10-27_AMTK_508", "60", "unknown", 47.6, -122.3, {})))
    assert v.train == "508"
    assert v.bearing is None and v.speed_mph is None


def test_route_prefix_filters_and_mbta_train_number():
    f = GtfsRtFeed(cfg(id="mbta", route_prefix="CR-"), {})
    body = feed_bytes(("bus1", "111", "78266528", 42.37, -71.06, {}),
                      ("cr1", "CR-Worcester", "CR-Weekday-Fall-25-523", 42.35, -71.2, {}))
    [v] = f.parse(body)
    assert v.key == "mbta:cr1"
    assert v.train == "523"


def test_zero_position_dropped():
    f = GtfsRtFeed(cfg(), {})
    assert f.parse(feed_bytes(("v", "r", "t", 0.0, 0.0, {}))) == []


def test_missing_key_disables_feed(monkeypatch):
    monkeypatch.delenv("TEST_KEY", raising=False)
    f = build(cfg(params={"api_key": "${TEST_KEY}"}), {})
    assert f.disabled == "set TEST_KEY in .env to enable"
    monkeypatch.setenv("TEST_KEY", "abc")
    assert build(cfg(params={"api_key": "${TEST_KEY}"}), {}).disabled is None


def test_amtraker_keeps_active_amtrak_only():
    f = AmtrakerFeed(cfg(id="amtraker", kind="amtraker", agency="Amtrak"), {})
    base = {"lat": 32.46, "lon": -111.21, "trainNum": "1", "trainID": "1-26", "routeName": "Sunset Limited",
            "heading": "NW", "velocity": 78.43, "eventName": "Maricopa", "destName": "Los Angeles Union",
            "lastValTS": "2026-10-27T23:05:39-07:00", "iconColor": "#c60b31"}
    data = {"1": [dict(base, provider="Amtrak", trainState="Active"),
                  dict(base, provider="Amtrak", trainState="Predeparture", trainID="1-27"),
                  dict(base, provider="Via", trainState="Active", trainID="V1")]}
    [v] = f.parse(data)
    assert (v.train, v.route, v.bearing, v.speed_mph, v.color) == ("1", "Sunset Limited", 315, 78.4, "c60b31")
    assert v.timestamp == 1793167539


def test_septa_train_number_and_car_count():
    f = GtfsRtFeed(cfg(id="septa"), {})
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    v = msg.entity.add(id="e").vehicle
    v.vehicle.id = v.vehicle.label = "333,332,135,136"
    v.trip.trip_id = "WAR416_20261019_SID189798"
    v.position.latitude, v.position.longitude = 40.0, -75.1
    [out] = f.parse(msg.SerializeToString())
    assert (out.train, out.cars) == ("416", 4)


def test_lirr_train_number_from_trip_id():
    f = GtfsRtFeed(cfg(id="lirr"), {})
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    v = msg.entity.add(id="e").vehicle
    v.vehicle.id, v.vehicle.label = "7544_718", "7544"
    v.trip.trip_id = "GO202_26_718_2"
    v.position.latitude, v.position.longitude = 40.7, -73.8
    [out] = f.parse(msg.SerializeToString())
    assert out.train == "718"
