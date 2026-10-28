"""API keys page: which feeds need keys, saving them to <data-dir>/.env, and testing them live.

Keys can only be changed from the machine running the server (or from any device when started with
--allow-remote-settings), and only by pages served from this server.
"""
import ipaddress
import json
import logging
import os
import re

from aiohttp import web

from . import feeds as feedmod

log = logging.getLogger(__name__)
PLACEHOLDER = re.compile(r"\$\{(\w+)\}")
KEY_FIELDS = ("params", "headers", "username", "password")


def key_vars(cfg) -> list:
    """Environment variables a feed config needs, in the order they appear."""
    found = []
    for field in KEY_FIELDS:
        found += PLACEHOLDER.findall(json.dumps(cfg.get(field, "")))
    return list(dict.fromkeys(found))


def is_secret(var) -> bool:
    return not var.endswith("USERNAME")


def shown(var, value):
    """What the page may show of a saved value: usernames in full, keys only by their last 4 characters."""
    if not value:
        return None
    if not is_secret(var):
        return value
    return f"…{value[-4:]}" if len(value) >= 12 and "PASSWORD" not in var else "saved"


def write_env(path, updates: dict):
    """Set or remove VAR=value lines in a .env file, keeping every other line as it is."""
    lines = path.read_text().splitlines() if path.exists() else [
        "# train-tracker API keys (edit here or on the API keys page)"]
    out, done = [], set()
    for line in lines:
        m = re.match(r"\s*(\w+)\s*=", line)
        if m and m.group(1) in updates:
            var = m.group(1)
            if var not in done and updates[var]:
                out.append(f"{var}={updates[var]}")
            done.add(var)
        else:
            out.append(line)
    out += [f"{var}={val}" for var, val in updates.items() if var not in done and val]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_text("\n".join(out) + "\n")
    os.chmod(tmp, 0o600)   # keys are personal
    tmp.replace(path)


def editable(request):
    """(allowed, reason) for changing keys from this request."""
    origin = request.headers.get("Origin")
    if origin and origin.split("://", 1)[-1] != request.host:
        return False, "Keys can only be changed from this app's own page."
    try:
        local = ipaddress.ip_address((request.remote or "").split("%")[0]).is_loopback
    except ValueError:
        local = False
    if local or request.app.get("allow_remote_settings"):
        return True, None
    return False, ("Keys can only be changed on the computer running train-tracker. "
                   "Start it with --allow-remote-settings to allow other devices.")


def keyed_configs(hub):
    return [cfg for cfg in hub.config["feeds"] if key_vars(cfg)]


def page_state(request):
    hub = request.app["hub"]
    ok, reason = editable(request)
    out = []
    for cfg in keyed_configs(hub):
        labels = cfg.get("key_labels", {})
        feed = hub.by_id(cfg["id"])
        out.append({
            "id": cfg["id"], "agency": cfg["agency"],
            "signup": cfg.get("signup"), "help": cfg.get("signup_help"),
            "keys": [{"var": v, "label": labels.get(v, v), "secret": is_secret(v),
                      "saved": shown(v, os.environ.get(v))} for v in key_vars(cfg)],
            "status": feed.status() if feed else None,
        })
    return {"editable": ok, "reason": reason, "envfile": str(request.app["data_dir"] / ".env"), "feeds": out}


async def get_settings(request):
    return web.json_response(page_state(request))


async def _json_body(request):
    ok, reason = editable(request)
    if not ok:
        raise web.HTTPForbidden(text=reason)
    if request.content_type != "application/json":   # also keeps other websites from posting here
        raise web.HTTPUnsupportedMediaType(text="send JSON")
    try:
        return await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="bad JSON")


def _clean_values(hub, values, only_feed=None):
    allowed = {v for cfg in keyed_configs(hub) if only_feed in (None, cfg["id"]) for v in key_vars(cfg)}
    if not isinstance(values, dict) or set(values) - allowed:
        raise web.HTTPBadRequest(text="unknown setting")
    clean = {}
    for var, val in values.items():
        val = str(val).strip()
        if re.search(r"[\s\"'#]", val) or len(val) > 500:
            raise web.HTTPBadRequest(text=f"{var} has characters a key can't contain")
        clean[var] = val
    return clean


async def save_settings(request):
    """Save keys (an empty value removes one) and restart the affected feeds straight away."""
    hub = request.app["hub"]
    body = await _json_body(request)
    values = _clean_values(hub, body.get("values"))
    write_env(request.app["data_dir"] / ".env", values)
    for var, val in values.items():
        if val:
            os.environ[var] = val
        else:
            os.environ.pop(var, None)
    for cfg in keyed_configs(hub):
        if set(key_vars(cfg)) & set(values):
            await hub.reload_feed(cfg["id"])
            log.info("API keys page: %s keys updated", cfg["id"])
    return web.json_response(page_state(request))


async def test_settings(request):
    """Try one fetch with the values on the page (saved or not) without saving anything."""
    hub = request.app["hub"]
    body = await _json_body(request)
    cfg = next((c for c in keyed_configs(hub) if c["id"] == body.get("feed")), None)
    if not cfg:
        raise web.HTTPBadRequest(text="unknown feed")
    values = _clean_values(hub, body.get("values") or {}, cfg["id"])
    feed = feedmod.KINDS[cfg["kind"]](cfg, hub.statics)
    feed.env = {**os.environ, **{k: v for k, v in values.items() if v}}
    try:
        vehicles = await feed.fetch(request.app["session"])
    except Exception as e:
        return web.json_response({"ok": False, "message": feedmod.describe_error(feed.agency, e)})
    n = len(vehicles)
    msg = (f"The key works: {n} train{'s' if n != 1 else ''} running right now." if n
           else "The key works. No trains are running right now.")
    return web.json_response({"ok": True, "count": n, "message": msg})


def add_routes(app):
    app.router.add_get("/api/settings", get_settings)
    app.router.add_post("/api/settings", save_settings)
    app.router.add_post("/api/settings/test", test_settings)
