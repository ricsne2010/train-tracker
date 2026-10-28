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
