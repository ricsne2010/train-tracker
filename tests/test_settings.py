import asyncio
import os
import time

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from google.transit import gtfs_realtime_pb2

from train_tracker import feeds as feedmod, settings
from train_tracker.app import Hub


def test_write_env_updates_in_place_and_removes(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# my keys\nMETRA_API_TOKEN=old\nOTHER=keep\n")
    settings.write_env(env, {"METRA_API_TOKEN": "new", "API_511_KEY": "abc"})
    assert env.read_text() == "# my keys\nMETRA_API_TOKEN=new\nOTHER=keep\nAPI_511_KEY=abc\n"
    settings.write_env(env, {"METRA_API_TOKEN": ""})
    assert env.read_text() == "# my keys\nOTHER=keep\nAPI_511_KEY=abc\n"
    assert oct(env.stat().st_mode & 0o777) == "0o600"


def test_key_vars_and_masking():
    cfg = {"params": {"api_token": "${METRA_API_TOKEN}"}, "headers": {"Authorization": "Bearer ${METRA_API_TOKEN}"}}
    assert settings.key_vars(cfg) == ["METRA_API_TOKEN"]
    assert settings.key_vars({"username": "${NJT_USERNAME}", "password": "${NJT_PASSWORD}"}) == ["NJT_USERNAME", "NJT_PASSWORD"]
    assert settings.shown("METRA_API_TOKEN", "abcdefgh12345678") == "…5678"
    assert settings.shown("METRA_API_TOKEN", "short") == "saved"
    assert settings.shown("NJT_PASSWORD", "hunter2hunter2hunter2") == "saved"
    assert settings.shown("NJT_USERNAME", "rich") == "rich"


def vehicles_pb(n):
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    for i in range(n):
        v = msg.entity.add(id=f"e{i}").vehicle
        v.vehicle.id = f"v{i}"
        v.position.latitude, v.position.longitude = 41.88, -87.63
        v.timestamp = int(time.time())
    return msg.SerializeToString()


def run_with_agency(tmp_path, monkeypatch, scenario, allow_remote=False):
    """Run `scenario(client, hub)` against our settings routes and a fake agency that wants key GOODKEY123456."""
    monkeypatch.delenv("TEST_KEY", raising=False)

    async def agency(request):
        if request.query.get("key") != "GOODKEY123456":
            return web.Response(status=401, text="bad key")
        return web.Response(body=vehicles_pb(3), content_type="application/x-protobuf")

    async def go():
        fake = web.Application()
        fake.router.add_get("/feed", agency)
        async with TestServer(fake) as agency_srv:
            cfg = {"stale_after_s": 600, "feeds": [{
                "id": "testrail", "agency": "Test Rail", "kind": "gtfsrt", "mode": "commuter",
                "url": str(agency_srv.make_url("/feed")), "params": {"key": "${TEST_KEY}"},
                "interval_s": 3600, "signup": "https://example.org", "key_labels": {"TEST_KEY": "API key"}}]}
            hub = Hub(cfg)
            hub.feeds = [feedmod.build(c, {}) for c in cfg["feeds"]]
            session = aiohttp.ClientSession()
            app = web.Application()
            app["hub"], app["data_dir"], app["allow_remote_settings"] = hub, tmp_path, allow_remote
            app["session"] = hub.session = session
            settings.add_routes(app)
            try:
                async with TestClient(TestServer(app)) as client:
                    return await scenario(client, hub)
            finally:
                for t in hub.tasks.values():
                    t.cancel()
                await session.close()
    return asyncio.run(go())


def test_page_lists_keyed_feed_and_tests_keys_without_saving(tmp_path, monkeypatch):
    async def scenario(client, hub):
        page = await (await client.get("/api/settings")).json()
        assert page["editable"] is True
        [feed] = page["feeds"]
        assert feed["keys"] == [{"var": "TEST_KEY", "label": "API key", "secret": True, "saved": None}]
        assert feed["status"]["disabled"]

        bad = await (await client.post("/api/settings/test", json={"feed": "testrail", "values": {"TEST_KEY": "nope"}})).json()
        assert bad["ok"] is False and "turned this key down (HTTP 401)" in bad["message"]
        good = await (await client.post("/api/settings/test", json={"feed": "testrail", "values": {"TEST_KEY": "GOODKEY123456"}})).json()
        assert good == {"ok": True, "count": 3, "message": "The key works: 3 trains running right now."}
        assert "TEST_KEY" not in os.environ and not (tmp_path / ".env").exists()   # testing never saves
    run_with_agency(tmp_path, monkeypatch, scenario)


def test_save_writes_env_and_starts_feed(tmp_path, monkeypatch):
    async def scenario(client, hub):
        r = await client.post("/api/settings", json={"values": {"TEST_KEY": "GOODKEY123456"}})
        assert r.status == 200
        page = await r.json()
        assert page["feeds"][0]["keys"][0]["saved"] == "…3456"
        assert "TEST_KEY=GOODKEY123456" in (tmp_path / ".env").read_text()
        await asyncio.sleep(0.5)   # first poll
        assert hub.by_id("testrail").disabled is None
        assert len([v for v in hub.vehicles.values() if v["feed"] == "testrail"]) == 3

        await client.post("/api/settings", json={"values": {"TEST_KEY": ""}})
        assert hub.by_id("testrail").disabled and not hub.vehicles
        assert "TEST_KEY" not in (tmp_path / ".env").read_text()
    try:
        run_with_agency(tmp_path, monkeypatch, scenario)
    finally:
        os.environ.pop("TEST_KEY", None)


def test_rejects_other_sites_unknown_settings_and_bad_values(tmp_path, monkeypatch):
    async def scenario(client, hub):
        r = await client.post("/api/settings", json={"values": {"TEST_KEY": "x"}},
                              headers={"Origin": "https://evil.example"})
        assert r.status == 403
        r = await client.post("/api/settings", data="TEST_KEY=x")   # a plain form post
        assert r.status == 415
        r = await client.post("/api/settings", json={"values": {"PATH": "/tmp"}})
        assert r.status == 400
        r = await client.post("/api/settings", json={"values": {"TEST_KEY": "two words"}})
        assert r.status == 400
        assert not (tmp_path / ".env").exists()
    run_with_agency(tmp_path, monkeypatch, scenario)


def test_other_devices_read_only_unless_allowed():
    class Req:
        headers, host = {}, "pi.local:7500"
        def __init__(self, remote, allow):
            self.remote, self.app = remote, {"allow_remote_settings": allow}
    assert settings.editable(Req("127.0.0.1", False)) == (True, None)
    assert settings.editable(Req("::1", False)) == (True, None)
    ok, reason = settings.editable(Req("192.168.1.20", False))
    assert not ok and "--allow-remote-settings" in reason
    assert settings.editable(Req("192.168.1.20", True)) == (True, None)
