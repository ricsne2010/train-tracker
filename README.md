<p align="center"><img src="src/train_tracker/web/img/moon-pi-logo.png" alt="Project Moon Pi" width="140"></p>

# US Train Tracker

*A Project Moon Pi project.*

Live Amtrak and commuter-rail positions on a map of US passenger track, in your browser.

## On the map

* **Zoomed out:** coloured arrows (or dots when a train's direction isn't known yet) across the country.
* **Middle zooms:** a small top-down train (locomotive and cars) pointing the way it's going.
* **Zoomed in:** each train drawn to scale, car by car, bending with the real track; the track shows
  ballast, ties and rails, with double and triple track where NARN records it. Trains run on the
  right-hand track for their direction and glide along the track between updates at their reported speed.
  Car counts are live for SEPTA and typical for each service elsewhere.

## Install and run

Needs Python 3.10 or newer.

**From a release:** download the `.whl` file from the [Releases](../../releases) page, then:

```
python3 -m venv ~/train-tracker-venv
~/train-tracker-venv/bin/pip install train_tracker-*.whl
~/train-tracker-venv/bin/train-tracker
```

**From source:**

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/train-tracker
```

Then open <http://127.0.0.1:7500>. The first start takes about a minute while it downloads the
FRA track map (~4 MB) and Amtrak's schedule into `~/.train-tracker/`.

| Option | Default | |
|---|---|---|
| `--port` | `7500` | |
| `--host` | `127.0.0.1` | `0.0.0.0` to open it from a phone or another computer on your network |
| `--data-dir` | `~/.train-tracker` | downloads and `.env` |
| `--config` | bundled `feeds.json` | your own feed list |
| `fetch-track` | | re-download the NARN track map |
| `--version` | | |

### API keys (optional)

MBTA, LIRR, Metro-North, SEPTA and Amtrak need no key. For Metra, Caltrain, Metrolink and NJ Transit,
copy [.env.example](.env.example) to `~/.train-tracker/.env` (or `.env` in the folder you run from) and fill in
the keys you have. Feeds without a key are listed in the app as disabled.

## How it works

```
feeds.json ──► feeds.py        one poll loop per feed (20–60 s): GTFS-RT protobuf, Amtraker JSON, NJT token flow
                  ▼
               model.py        Vehicle: key, agency, lat/lon, train, route, bearing, speed_mph, stop …
                  ▼
               app.py          cache ─► WebSocket /ws (snapshot on connect, then upsert/remove diffs)
                                        GET /api/vehicles, /api/status
                  ▼
               web/            MapLibre map: NARN track + trains, agency filters, feed health, search
```

* **Amtrak**: Transitdocs GTFS-RT, enriched with route, train number, destination and station names
  from Amtrak's static GTFS (refreshed daily).
* **Amtraker fallback**: only polled while the Transitdocs feed is down or empty.
* **Commuter rail**: MBTA (filtered to `CR-` routes), LIRR, Metro-North, SEPTA; Metra, Caltrain (511.org),
  Metrolink and NJ Transit with keys.
* Positions older than 10 minutes (`stale_after_s`) are dropped. Freight is out of scope.

### Adding a feed

Add an entry to [feeds.json](src/train_tracker/feeds.json) (`kind: "gtfsrt"`, `url`, optional `params`/`headers`
with `${ENV_VAR}` placeholders, `route_prefix` to filter a multimodal feed) and a colour in `AGENCY_COLORS` in
[web/app.js](src/train_tracker/web/app.js). Transitland and the Mobility Database list GTFS-RT URLs.

## Development

```
.venv/bin/pytest -q
```

CI runs the tests and a build on Python 3.10–3.13 for every push and pull request.

### Releasing

1. Write the changes under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md) and commit.
2. `.venv/bin/python tools/release.py 0.2.0`: bumps the version, dates the changelog, runs the tests, commits and tags.
3. `git push && git push origin v0.2.0`: the Release workflow checks the tag matches the version, builds the
   wheel and source archive, and publishes a GitHub Release with the changelog entry as its notes.

## Known gaps

* NJ Transit endpoints (`/api/GTFSRT/getToken`, `/getVehiclePositions`) follow the RailData API pattern but
  are untested with real credentials; Metra, Caltrain and Metrolink are also untested without keys.
* Only Amtrak has static GTFS loaded, so commuter stops show raw stop IDs.
* NARN stores one centreline per route, so the track a train is on is inferred (right-hand running), not known.
* Car counts are typical for each service except SEPTA, whose feed lists the cars.

## Data and credits

* Amtrak positions via [Transitdocs](https://transitdocs.com); schedule from Amtrak GTFS.
* [Amtraker API](https://amtraker.com), ODC-By 1.0.
* MBTA, MTA (LIRR, Metro-North), SEPTA, Metra, 511.org (Caltrain), Metrolink, NJ Transit.
* Track: FRA North American Rail Network (public domain).
* Basemap © [OpenFreeMap](https://openfreemap.org), © OpenStreetMap contributors.

## License

MIT; see [LICENSE](LICENSE). Data sources keep their own terms (see above).
The Project Moon Pi name and logo belong to Project Moon Pi and are not covered by the MIT license.
