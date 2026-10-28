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
