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
    s.stops["KEL"] = {"name": "Kelso-Longview", "lat": 46.14, "lon": -122.91, "station": "KEL"}
    return s


def test_amtrak_enriched_from_static():
    f = GtfsRtFeed(cfg(id="amtrak", agency="Amtrak", mode="intercity", static={"url": "x"}),
                   {"amtrak": amtrak_static()})
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


def trip_update_bytes(trip_id, route_id, stops, vehicle_id=None, start_date=None):
    """stops: [(stop_id, arrival_time, arrival_delay or None)]"""
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    tu = msg.entity.add(id="t1").trip_update
    tu.trip.trip_id, tu.trip.route_id = trip_id, route_id
    if start_date:
        tu.trip.start_date = start_date
    if vehicle_id:
        tu.vehicle.id = vehicle_id
    for sid, t, d in stops:
        u = tu.stop_time_update.add(stop_id=sid)
        u.arrival.time = t
        if d is not None:
            u.arrival.delay = d
    return msg.SerializeToString()


def test_next_stop_and_delay_from_trip_updates():
    now = int(time.time())
    f = GtfsRtFeed(cfg(id="lirr", trip_updates_url="http://tu"), {})
    tu = trip_update_bytes("GO1_26_718", "6", [("A", now - 600, 30), ("B", now + 300, 240), ("C", now + 900, 300)])
    [v] = f.parse(feed_bytes(("7081", "6", "GO1_26_718", 40.7, -73.5, {})), tu)
    assert (v.next_stop, v.next_time, v.delay) == ("B", now + 300, 240)


def test_delay_worked_out_from_the_timetable_when_the_feed_only_has_times():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    s = StaticGtfs()
    s.tz = "America/New_York"
    s.routes["3"] = {"name": "Harlem", "color": None}
    s.trips["99"] = {"route_id": "3", "train": "123", "headsign": "Grand Central"}
    s.stops["112"] = {"name": "White Plains", "lat": 41.03, "lon": -73.76, "station": "112"}
    s.times["99"] = {"112": (10 * 3600, 10 * 3600)}          # due 10:00
    day = datetime(2026, 10, 29, tzinfo=ZoneInfo("America/New_York"))
    predicted = int(day.replace(hour=10, minute=7).timestamp())   # 7 minutes late
    f = GtfsRtFeed(cfg(id="mnr", static={"url": "x"}), {"mnr": s})
    tu = trip_update_bytes("99", "3", [("112", predicted, None)], start_date="20261029")
    f.parse(feed_bytes(), tu)
    from train_tracker import realtime
    assert realtime.progress(f.trips["99"], s, now=predicted - 60) == {
        "next_stop": "White Plains", "next_time": predicted, "delay": 420}


def test_route_ids_filter_keeps_only_rail_and_drops_unrouted():
    f = GtfsRtFeed(cfg(id="rtd", route_ids=["A", "117N"]), {})
    body = feed_bytes(("bus", "15L", "1", 39.7, -105.0, {}), ("a", "A", "2", 39.8, -104.8, {}),
                      ("none", "", "3", 39.7, -105.0, {}))
    assert [v.key for v in f.parse(body)] == ["rtd:a"]


def alert_bytes(*alerts):
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    for i, (route, text, end) in enumerate(alerts):
        a = msg.entity.add(id=f"a{i}").alert
        a.header_text.translation.add(text=text, language="en")
        if route:
            a.informed_entity.add(route_id=route)
        else:
            a.informed_entity.add(agency_id="1")
        if end:
            a.active_period.add(start=1, end=end)
    return msg.SerializeToString()


def test_alerts_keep_rail_routes_and_drop_buses_and_expired():
    f = GtfsRtFeed(cfg(id="mbta", route_prefix="CR-", alerts_url="http://al"), {})
    al = alert_bytes(("CR-Worcester", "Worcester Line delays", None), ("111", "Bus 111 detour", None),
                     ("CR-Lowell", "Old news", 1000), (None, "Agency-wide notice", None))
    f.parse(feed_bytes(), None, al)
    assert [a["header"] for a in f.alerts] == ["Worcester Line delays"]   # agency-wide dropped: feed has buses too
    g = GtfsRtFeed(cfg(id="septa", alerts_url="http://al"), {})
    g.parse(feed_bytes(), None, alert_bytes((None, "Agency-wide notice", None)))
    assert [a["header"] for a in g.alerts] == ["Agency-wide notice"]


def test_failed_extra_fetch_keeps_last_trip_updates():
    now = int(time.time())
    f = GtfsRtFeed(cfg(id="mbta", trip_updates_url="http://tu"), {})
    f.parse(feed_bytes(), trip_update_bytes("T", "CR-X", [("S", now + 60, 0)]))
    f.parse(feed_bytes())            # trip-update fetch failed this round
    assert "T" in f.trips


def test_alert_headline_taken_from_description_when_it_repeats_it():
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    a = msg.entity.add(id="x").alert
    a.header_text.translation.add(text="DELAY NOTIFICATION: TRAIN 521 IS LATE")
    a.description_text.translation.add(text="Delay Notification: Train 521 is late due to a signal outage.")
    from train_tracker import realtime
    out = realtime.parse_alert(msg.entity[0])
    assert out["header"] == "Delay Notification: Train 521 is late"
    assert out["description"] == "due to a signal outage."


def test_alert_with_only_a_description_gets_its_first_sentence_as_headline():
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    a = msg.entity.add(id="x").alert
    a.description_text.translation.add(text="Train 5 is 2 hours late. Speed restrictions near Reno.", language="en-US")
    from train_tracker import realtime
    out = realtime.parse_alert(msg.entity[0])
    assert (out["header"], out["description"]) == ("Train 5 is 2 hours late.", "Speed restrictions near Reno.")
