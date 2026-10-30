<p align="center"><img src="src/train_tracker/web/img/moon-pi-logo.png" alt="Project Moon Pi" width="140"></p>

# US Train Tracker

**Designed and Created by Project Moon Pi**

Live Amtrak and commuter-rail positions on a map of US passenger track, in your browser.

**New here? Follow the [Installation Guide](docs/INSTALL.md)** ([printable PDF](docs/US-Train-Tracker-Install-Guide.pdf)):
step by step for Mac, Windows, Raspberry Pi, iPhone and Android, no programming needed.

## How it works

US Train Tracker is two parts:

1. **A server** that runs on a computer you own: a Mac, a Windows PC, a Linux box or a Raspberry Pi. It collects
   live positions, arrival predictions and service alerts from Amtrak and the commuter railroads every 20–60
   seconds, plus each railroad's schedule and the FRA rail map, and keeps one up-to-date picture of every train.
2. **A map in your web browser.** Open it on the same computer, or on any phone, tablet or computer on the same
   Wi-Fi. The server pushes each change to the map as it happens, so trains move without reloading.

```
 railroad feeds, schedules, alerts ─►  server on your Mac / PC / Pi (port 7500)  ─►  browser on the computer,
 FRA rail map                      ─►  (Python)                                   ─►  phones and tablets on your Wi-Fi
```

**Phones and tablets** show the map, and it can sit on the home screen like an app, but they can't run the
server: that needs a computer at home. A Raspberry Pi left on makes the map available all the time. Nothing is
shared beyond your own network unless you set up remote access (the guide covers a safe way).

## What you need

| | |
|---|---|
| **Server computer** | macOS 11 or newer, Windows 10 or 11, Linux, or a Raspberry Pi 4 or 5 (3B+ works, more slowly) |
| **Python** | 3.10 or newer from [python.org](https://www.python.org/downloads/) (3.12+ recommended; 3.10 is out of security support) |
| **Memory** | about 150–200 MB while running |
| **Disk** | about 200 MB (app ~40 MB, downloaded maps and schedules ~140 MB) |
| **Internet** | always on while running: ~140 MB on first start, then about 130 MB an hour |
| **To view the map** | a current Safari, Chrome, Edge or Firefox; iPhone/iPad on iOS 15+, or Android with current Chrome |

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
* **Click a train** for its route, destination, next stop with its predicted time, and how late it's running,
  plus any service alerts about it. **Follow** keeps the map on the train as it moves; **Share** copies a link
  that opens straight to it.
* **Stations** from every railroad's schedule: click one for its next trains, live from the railroad's
  predictions (Penn Station-style shared stations show each railroad's board). Search finds stations too.
* **Trails** show where each train has been over the last 15 minutes.
* **Colour trains by lateness** (Map layers): green on time, amber 5–15 minutes late, red over 15.
* **Service alerts** in the panel, from each railroad that publishes them.
* **Copy link to this view** (Map layers) shares the map as you see it (`#map=zoom/lat/lon`).

## Install and run

**The easy way (Mac or Windows):** download **Source code (zip)** from the [latest release](../../releases/latest),
unzip it and double-click **Install Train Tracker** (`.command` on a Mac, `.bat` on Windows). The installer:

* installs it for you (Mac: `~/Library/Application Support/Train Tracker`; Windows: `%LOCALAPPDATA%\TrainTracker`),
* asks whether phones on your Wi-Fi may open the map, and whether it should start when you log in,
* sets it up as a **background service** (a LaunchAgent on macOS, a hidden process on Windows), and
* puts two icons on your Desktop (and in Applications or the Start menu): **Start Train Tracker** starts the
  service and opens the map; **Stop Train Tracker** shuts it down. **Uninstall Train Tracker** is next to them.

Run the installer again to update or to change your answers. With phones allowed, the map's panel shows the
address and a QR code to scan. Details, the Raspberry Pi setup and troubleshooting are in the
[Installation Guide](docs/INSTALL.md).

**From the command line** (Python 3.10 or newer):

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
| `--allow-remote-settings` | off | let other devices change API keys on the settings page |
| `--open` | off | open the map in your browser once it's running |
| `--log-file` | | write messages to a file instead of the terminal (the background service uses this) |
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

**Easiest:** open **API keys…** in the map panel (or <http://127.0.0.1:7500/settings.html>). Each agency has a
card with its signup link; paste the key, press **Test** to check it with the agency, then **Save**. The feed
starts straight away, no restart needed, and **Remove key** turns it off again. Saved keys are shown only by their
last four characters.

Keys are saved in `~/.train-tracker/.env` (readable only by you). You can also edit that file by hand using
[.env.example](.env.example) as a template, then restart `train-tracker`. Keys are personal: keep `.env` out of git
(it is already in `.gitignore`).

Keys can only be changed from the computer running `train-tracker`. If you run it on another machine (say a
Raspberry Pi with `--host 0.0.0.0`) and want to add keys from your phone, start it with `--allow-remote-settings`;
anyone who can reach the page on your network can then change the keys.

## How it works

```
feeds.json ──► feeds.py        one poll loop per feed (20–60 s): GTFS-RT protobuf, Amtraker JSON, NJT token flow
                  ▼
               realtime.py     trip updates (next stop, predicted time, delay) and service alerts
               gtfs_static.py  each railroad's schedule: names, stations, timetables (rail only, cached)
                  ▼
               model.py        Vehicle: key, agency, lat/lon, train, route, bearing, speed_mph, next stop, delay …
                  ▼
               app.py          cache ─► WebSocket /ws (snapshot with trails and alerts, then upsert/remove diffs)
                                        GET /api/vehicles, /api/status, /api/alerts, /api/stations,
                                            /api/station/<feed>/<station id>
                  ▼
               web/            MapLibre map: NARN track + trains, agency filters, feed health, search
```

* **Amtrak**: Transitdocs GTFS-RT (positions, predictions and alerts in one feed), enriched from Amtrak's
  static GTFS.
* **Amtraker fallback**: only polled while the Transitdocs feed is down or empty.
* **Commuter rail, no key**: MBTA (filtered to `CR-` routes), LIRR, Metro-North, SEPTA, MARC, VRE, RTD
  Denver (A, B, G and N lines) and CapMetro Rail (Austin). **With keys**: Metra, Caltrain (511.org), Metrolink
  and NJ Transit.
* **Schedules**: each railroad's GTFS is downloaded in the background (refreshed daily, rail routes only, parsed
  copy cached in the data folder) for stop names, stations and the timetable. Where a feed gives predicted
  times but not delays (MBTA, Metro-North), lateness is worked out against the timetable.
* Positions older than 10 minutes (`stale_after_s`) are dropped. Freight is out of scope.

### Adding a feed

Add an entry to [feeds.json](src/train_tracker/feeds.json) (`kind: "gtfsrt"`, `url`, optional `params`/`headers`
with `${ENV_VAR}` placeholders, `trip_updates_url` and `alerts_url` when the railroad publishes those separately,
`static: {"url": ...}` for its schedule, `route_prefix` or `route_ids` to pick the rail routes out of a feed shared
with buses) and a colour in `AGENCY_COLORS` in
[web/app.js](src/train_tracker/web/app.js). Transitland and the Mobility Database list GTFS-RT URLs.

## Development

```
.venv/bin/pytest -q
```

CI runs the tests and a build on Python 3.10–3.13 for every push and pull request.

### Installation Guide

[docs/INSTALL.md](docs/INSTALL.md) is the guide; after editing it, rebuild the printable copy with
`python3 tools/make_guide_pdf.py` (needs reportlab, Pillow and the DejaVu fonts). Releases attach the PDF.

### Releasing

1. Write the changes under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md) and commit.
2. `.venv/bin/python tools/release.py 0.2.0`: bumps the version, dates the changelog, runs the tests, commits and tags.
3. `git push && git push origin v0.2.0`: the Release workflow checks the tag matches the version, builds the
   wheel and source archive, and publishes a GitHub Release with the changelog entry as its notes.

## Known gaps

* NJ Transit endpoints (`/api/GTFSRT/getToken`, `/getVehiclePositions`) follow the RailData API pattern but
  are untested with real credentials; Metra, Caltrain and Metrolink are also untested without keys.
* Metra's schedule needs its API key and NJ Transit's needs an account login, so neither is loaded yet; their
  trains show without station names or boards.
* SEPTA's predictions give only how late a train is, not stop-by-stop times, so SEPTA station boards are empty.
* VRE runs at rush hour only; its feeds are empty the rest of the day. Sounder, South Shore, Tri-Rail, SunRail,
  Brightline and others don't publish an open live feed (Sounder needs a Puget Sound OneBusAway key).
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
* MARC: [Maryland Transit Administration](https://www.mta.maryland.gov/developer-resources) GTFS-RT
* VRE: [Virginia Railway Express](https://www.vre.org/about/developer-resources/) GTFS-RT
* RTD commuter rail: [RTD Denver](https://www.rtd-denver.com/open-records/open-spatial-information/real-time-feeds) GTFS-RT
* CapMetro Rail: [Capital Metro](https://www.capmetro.org/metrolabs) GTFS-RT via [data.texas.gov](https://data.texas.gov)
* Metra, Caltrain ([511.org](https://511.org/open-data)), Metrolink and NJ Transit: their GTFS-RT feeds, with your own keys

**Data and reference**

* Track geometry: FRA [North American Rail Network](https://geodata.bts.gov/datasets/usdot::north-american-rail-network-lines/about) lines, public domain
* Schedules, routes and stations: each railroad's published GTFS (Amtrak, MBTA, MTA LIRR and Metro-North,
  SEPTA, Caltrain via Trillium, Metrolink, MARC, VRE, RTD, CapMetro), under each agency's data terms
* NJ Transit RailData endpoints: [jtarrio/raildata](https://github.com/jtarrio/raildata) (Apache-2.0), used as reference

**Code, map and fonts**

* [MapLibre GL JS](https://maplibre.org) 4.7.1, BSD-3-Clause
* Basemap tiles: © [OpenFreeMap](https://openfreemap.org), © [OpenMapTiles](https://openmaptiles.org), map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL)
* Noto Sans (via the OpenFreeMap glyphs), SIL Open Font License 1.1
* [aiohttp](https://github.com/aio-libs/aiohttp), Apache-2.0
* [gtfs-realtime-bindings](https://github.com/MobilityData/gtfs-realtime-bindings), Apache-2.0
* [protobuf](https://github.com/protocolbuffers/protobuf), BSD-3-Clause
* [certifi](https://github.com/certifi/python-certifi) (Mozilla's CA certificates), MPL-2.0
* [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) by Kazuhiko Arase, MIT (the "Open on your phone" QR code)
* Printable guide: [reportlab](https://www.reportlab.com/opensource/) (BSD) and [DejaVu Sans](https://dejavu-fonts.github.io/) (Bitstream Vera / DejaVu licence)
* Development: [pytest](https://pytest.org) (MIT), [build](https://github.com/pypa/build) (MIT)

**Logo:** Project Moon Pi. The animated splash (lens flare, flickering lander engines, twinkling stars, metal
sheen) is ported from the Project Moon Pi M.O.S.S. dash; `tools/make_splash_fx.py` (needs numpy, scipy and
Pillow) maps the logo for it and only needs re-running if the logo changes.

Built with Claude Code (Anthropic).

## License

MIT; see [LICENSE](LICENSE). Data sources keep their own terms (see above).
The Project Moon Pi name and logo belong to Project Moon Pi and are not covered by the MIT license.
