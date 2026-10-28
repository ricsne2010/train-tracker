<p align="center"><img src="src/train_tracker/web/img/moon-pi-logo.png" alt="Project Moon Pi" width="140"></p>

# US Train Tracker

**Designed and Created by Project Moon Pi**

Live Amtrak and commuter-rail positions on a map of US passenger track, in your browser.

## On the map

* **Zoomed out:** coloured arrows (or dots when a train's direction isn't known yet) across the country.
* **Middle zooms:** a small top-down train (locomotive and cars) pointing the way it's going.
* **Zoomed in:** each train drawn to scale, car by car, bending with the real track; the track shows
  ballast, ties and rails, with double and triple track where NARN records it. Trains run on the
  right-hand track for their direction and glide along the track between updates at their reported speed.
  Car counts are live for SEPTA and typical for each service elsewhere.
* **Freight and other track:** from city-level zoom, freight main lines, industrial track, sidings and yards
  appear under the passenger network (fetched by area from NARN and cached in `~/.train-tracker/narn_cells/`).
  Abandoned, removed and out-of-service lines and rail-trails are left out.
* **Map layers** (in the panel): switch each kind of line on or off (Amtrak and intercity, commuter, transit and
  tourist; freight main lines, industrial track, passing sidings, yards) and hide any railroad's track from the
  list of railroads in view. Choices are remembered in the browser; **Show everything** resets them.
* **Click any track** for its type, owner, subdivision, yard name and number of tracks.

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

Amtrak, MBTA, LIRR, Metro-North and SEPTA need no key. Four agencies hand out free developer keys:

| Agency | Where to sign up | What you get | Setting |
|---|---|---|---|
| Metra (Chicago) | [metra.com/developers](https://metra.com/developers): accept the licence, fill in the form | API token | `METRA_API_TOKEN` |
| Caltrain (Bay Area) | [511.org/open-data/token](https://511.org/open-data/token): enter your email | 511 API key | `API_511_KEY` |
| Metrolink (Los Angeles) | [GTFS-RT access page](https://metrolinktrains.com/about/gtfs/gtfs-rt-access/): enter your email | API key by email | `METROLINK_API_KEY` |
| NJ Transit | [developer.njtransit.com/registration](https://developer.njtransit.com/registration/): register for RailData | username and password | `NJT_USERNAME`, `NJT_PASSWORD` |

Copy [.env.example](.env.example) to `~/.train-tracker/.env` (or `.env` in the folder you start from), paste in the
keys you have and restart `train-tracker`. Until then those agencies show in the panel as switched off, with the
setting they need. Keys are personal: keep `.env` out of git (it is already in `.gitignore`).

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
* Freight track is shown, but not freight trains: railroads don't publish live freight positions.

## Credits

**Live data feeds** (each under its provider's terms of use):

* Amtrak positions: [Transitdocs](https://transitdocs.com) GTFS-Realtime feed
* Amtrak fallback: [Amtraker API](https://amtraker.com) by Piero Maddaleni, ODC-By 1.0
* MBTA Commuter Rail: [MBTA V3/GTFS-RT](https://www.mbta.com/developers), MBTA Developer license
* LIRR and Metro-North: [MTA GTFS-RT feeds](https://new.mta.info/developers), MTA data terms
* SEPTA Regional Rail: [SEPTA GTFS-RT](https://www3.septa.org/developer/)
* Metra, Caltrain ([511.org](https://511.org/open-data)), Metrolink and NJ Transit: their GTFS-RT feeds, with your own keys

**Data and reference**

* Track geometry: FRA [North American Rail Network](https://geodata.bts.gov/datasets/usdot::north-american-rail-network-lines/about) lines, public domain
* Amtrak schedule, routes and stations: [Amtrak GTFS](https://content.amtrak.com/content/gtfs/GTFS.zip)
* NJ Transit RailData endpoints: [jtarrio/raildata](https://github.com/jtarrio/raildata) (Apache-2.0), used as reference

**Code, map and fonts**

* [MapLibre GL JS](https://maplibre.org) 4.7.1, BSD-3-Clause
* Basemap tiles: © [OpenFreeMap](https://openfreemap.org), © [OpenMapTiles](https://openmaptiles.org), map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL)
* Noto Sans (via the OpenFreeMap glyphs), SIL Open Font License 1.1
* [aiohttp](https://github.com/aio-libs/aiohttp), Apache-2.0
* [gtfs-realtime-bindings](https://github.com/MobilityData/gtfs-realtime-bindings), Apache-2.0
* [protobuf](https://github.com/protocolbuffers/protobuf), BSD-3-Clause
* Development: [pytest](https://pytest.org) (MIT), [build](https://github.com/pypa/build) (MIT)

**Logo:** Project Moon Pi.

Built with Claude Code (Anthropic).

## License

MIT; see [LICENSE](LICENSE). Data sources keep their own terms (see above).
The Project Moon Pi name and logo belong to Project Moon Pi and are not covered by the MIT license.
