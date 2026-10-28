"""Passenger-carrying NARN track lines (FRA North American Rail Network, public domain).

NARN has ~300k segments; only those with a PASSNGR code (Amtrak / commuter service) are kept,
with lightly simplified geometry so the browser can draw them all at once (~4 MB).
The server downloads this on first start; `train-tracker fetch-track` refreshes it.
"""
import json
import logging
import urllib.parse
import urllib.request
from pathlib import Path

LAYER = ("https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/"
         "NTAD_North_American_Rail_Network_Lines/FeatureServer/0/query")
FILENAME = "narn_passenger_v2.geojson"   # v2 adds track counts
PAGE = 2000
log = logging.getLogger(__name__)


def _query(offset):
    q = urllib.parse.urlencode({
        "where": "PASSNGR IS NOT NULL AND COUNTRY = 'US'",
        "outFields": "PASSNGR,RROWNER1,SUBDIV,TRACKS",
        "orderByFields": "OBJECTID",
        "resultOffset": offset,
        "resultRecordCount": PAGE,
        "maxAllowableOffset": 0.00003,  # ~3 m simplification: curves stay on the rails when zoomed in
        "geometryPrecision": 5,
        "outSR": 4326,
        "f": "geojson",
    })
    with urllib.request.urlopen(f"{LAYER}?{q}", timeout=120) as r:
        return json.load(r)


def fetch(out: Path) -> Path:
    """Download the passenger network to `out`, replacing it only once the download is complete."""
    features, offset = [], 0
    while True:
        got = _query(offset).get("features", [])
        for f in got:
            f.pop("id", None)
            p = f["properties"]
            f["properties"] = {"p": p.get("PASSNGR"), "o": p.get("RROWNER1"), "s": p.get("SUBDIV"),
                               "t": p.get("TRACKS") or 1}
        features += got
        log.info("NARN: %d segments", len(features))
        if len(got) < PAGE:
            break
        offset += PAGE
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part")
    tmp.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")))
    tmp.replace(out)
    log.info("wrote %s (%.1f MB)", out, out.stat().st_size / 1e6)
    return out
