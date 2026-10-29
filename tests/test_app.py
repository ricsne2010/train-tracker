import asyncio
import json
import time

import pytest

from train_tracker import __version__
from train_tracker.app import DEFAULT_CONFIG, Hub, main
from train_tracker.model import Vehicle


def vehicle(key, lat=40.0, age=0, feed="f"):
    return Vehicle(key=key, feed=feed, agency="A", mode="commuter", lat=lat, lon=-74.0,
                   timestamp=int(time.time()) - age)


class Recorder(Hub):
    def __init__(self):
        super().__init__({"stale_after_s": 600, "feeds": []})
        self.sent = []

    async def broadcast(self, msg):
        self.sent.append(msg)


def test_replace_feed_sends_only_changes():
    hub = Recorder()
    asyncio.run(hub.replace_feed("f", [vehicle("f:1"), vehicle("f:2")]))
    assert len(hub.sent[-1]["upsert"]) == 2

    asyncio.run(hub.replace_feed("f", [vehicle("f:1"), vehicle("f:3", lat=41)]))
    msg = hub.sent[-1]
    assert msg["remove"] == ["f:2"]
    assert [v["key"] for v in msg["upsert"]] == ["f:3"]   # f:1 unchanged, not resent
    assert set(hub.vehicles) == {"f:1", "f:3"}


def test_replace_feed_leaves_other_feeds_and_drops_stale():
    hub = Recorder()
    asyncio.run(hub.replace_feed("g", [vehicle("g:1", feed="g")]))
    asyncio.run(hub.replace_feed("f", [vehicle("f:1"), vehicle("f:old", age=601)]))
    assert set(hub.vehicles) == {"g:1", "f:1"}


def test_replace_feed_drops_trains_not_yet_departed():
    hub = Recorder()
    asyncio.run(hub.replace_feed("f", [vehicle("f:skew", age=-60), vehicle("f:later", age=-3600)]))
    assert set(hub.vehicles) == {"f:skew"}


def test_bundled_config_is_valid():
    cfg = json.loads(DEFAULT_CONFIG.read_text())
    ids = [f["id"] for f in cfg["feeds"]]
    assert len(ids) == len(set(ids))
    for f in cfg["feeds"]:
        assert f["kind"] in ("gtfsrt", "amtraker", "njt")
        if "fallback_for" in f:
            assert f["fallback_for"] in ids


def test_version_flag(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert __version__ in capsys.readouterr().out


def test_lines_handler_fetches_once_then_serves_cache(tmp_path, monkeypatch):
    from aiohttp import web
    from aiohttp.test_utils import make_mocked_request
    from train_tracker import narn
    from train_tracker.app import lines_handler

    calls = []

    async def fake_fetch(session, cx, cy):
        calls.append((cx, cy))
        return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"n": "M"},
                "geometry": {"type": "LineString", "coordinates": [[-104.9, 40.1], [-104.8, 40.2]]}}]}

    monkeypatch.setattr(narn, "fetch_cell", fake_fetch)
    app = web.Application()
    app["data_dir"], app["cell_locks"], app["session"] = tmp_path, {}, None

    def get(cx, cy):
        req = make_mocked_request("GET", f"/api/lines/{cx}/{cy}", match_info={"cx": str(cx), "cy": str(cy)}, app=app)
        return asyncio.run(lines_handler(req))

    first, second = get(-210, 80), get(-210, 80)
    assert calls == [(-210, 80)]
    assert json.loads(second.body)["features"][0]["properties"]["n"] == "M"
    assert (tmp_path / "narn_cells" / "-210_80.geojson").exists()
    with pytest.raises(web.HTTPBadRequest):
        get(10, 80)


def test_trails_follow_moves_and_go_with_the_train():
    hub = Recorder()
    asyncio.run(hub.replace_feed("f", [vehicle("f:1", lat=40.0)]))
    asyncio.run(hub.replace_feed("f", [vehicle("f:1", lat=40.0)]))      # didn't move: no new point
    asyncio.run(hub.replace_feed("f", [vehicle("f:1", lat=40.1)]))
    assert [p[1] for p in hub.trails["f:1"]] == [40.0, 40.1]
    asyncio.run(hub.replace_feed("f", []))
    assert "f:1" not in hub.trails


def test_station_board_lists_upcoming_trains_with_lateness():
    from train_tracker.feeds import GtfsRtFeed
    from train_tracker.gtfs_static import StaticGtfs
    s = StaticGtfs()
    s.routes["H"] = {"name": "Harlem", "color": None}
    s.trips["T1"] = {"route_id": "H", "train": "540", "headsign": "Grand Central"}
    s.stops["WP"] = {"name": "White Plains", "lat": 41.03, "lon": -73.76, "station": "WP"}
    s.stops["GC"] = {"name": "Grand Central", "lat": 40.75, "lon": -73.98, "station": "GC"}
    s.stations["WP"] = {"name": "White Plains", "lat": 41.03, "lon": -73.76, "routes": ["Harlem"]}
    now = int(time.time())
    feed = GtfsRtFeed({"id": "mnr", "agency": "Metro-North", "kind": "gtfsrt", "mode": "commuter", "url": "x",
                       "static": {"url": "x"}}, {"mnr": s})
    feed.trips = {"T1": {"trip_id": "T1", "entity": "540", "sched": None, "route_id": "H", "start_date": None,
                         "vehicle_id": None, "delay": None,
                         "stops": [("WP", now + 600, now + 630, 120), ("GC", now + 2400, None, 120)]},
                  "T0": {"trip_id": "T0", "entity": "1", "sched": None, "route_id": "H", "start_date": None,
                         "vehicle_id": None, "delay": None, "stops": [("WP", now - 900, now - 870, 0)]}}
    hub = Recorder()
    hub.feeds = [feed]
    board = hub.station_board("mnr", "WP")
    assert board["name"] == "White Plains"
    [row] = board["trains"]                       # the train that already left isn't listed
    assert (row["train"], row["headsign"], row["delay"], row["ends_here"]) == ("540", "Grand Central", 120, False)
    assert hub.station_board("mnr", "nowhere") is None
    assert hub.stations()["features"][0]["properties"]["name"] == "White Plains"
