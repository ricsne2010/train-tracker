# Changelog

All notable changes to this project are listed here. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

- Installation Guide (docs/INSTALL.md and a printable PDF): Mac, Windows, Raspberry Pi, iPhone and Android,
  with machine requirements and how it works; the README now leads with both.
- Double-click launchers for Mac (`.command`) and Windows (`.bat`), plus "(phones too)" versions that let phones
  on the same Wi-Fi open the map; `--open` opens the browser once the server is up.
- "Open on your phone" in the panel: the address and a QR code, when the server listens on the network.
- Add to Home Screen: app icon and web app manifest, so the map opens full screen like an app on iPhone.
- Raspberry Pi service file (tools/train-tracker@.service) to start at power-on.
- Works with python.org's Python on macOS without its "Install Certificates" step (certificates from certifi).
- Separate prediction feeds are fetched once a minute, cutting data use to about 130 MB an hour.
- Next stop, predicted time and how late each train is running, from each railroad's trip updates (worked
  out against the timetable where the feed only gives times).
- Stations from every railroad's schedule; click one for its next trains. Search finds stations.
- Service alerts in the panel and in train and station popups.
- Follow a train, and share links to a train (`#train=`) or the current view (`#map=`).
- Trails: where each train has been over the last 15 minutes.
- Colour trains by lateness.
- New railroads: MARC, VRE, RTD Denver commuter rail and CapMetro Rail (Austin), no keys needed.
- Each railroad's schedule loads in the background (rail only, parsed copy cached), so start-up no longer waits.
- The map opens with the lower 48 fitted beside the panel (or above it on a phone) at any window size, and
  stays fitted while the window settles or is resized, until you move the map.
- A "More" prompt with a bobbing arrow at the bottom of the side panel and the API keys page while there's
  more to read below; click it to scroll down.

## [0.2.0] - 2026-10-28

- Freight and other active track (main lines, industrial track, sidings, yards) from NARN, loaded by area
  from city-level zoom and cached on disk.
- Map layers filters: turn each kind of passenger or freight line on or off, and hide individual railroads
  from the list of railroads in view; remembered between visits.
- Click any track for its type, owner, subdivision, yard and number of tracks.
- Track geometry is sent gzip-compressed.
- Metra key is also sent as a Bearer header; corrected the Metrolink signup link; API key steps in the README.
- API keys page (panel → API keys…): signup link per agency, Test a key against the live feed before saving,
  Save to start the feed without a restart, Remove to switch it off. Only changeable from the server's own
  computer unless started with `--allow-remote-settings`.
- Feed errors in the panel are in plain English (e.g. "Metra turned this key down (HTTP 401)").
- Brighter train colours, with Amtrak moved from blue to orange so its trains no longer blend into the
  blue Amtrak track; zoomed-out arrows and dots get a dark outline.
- Animated start-up logo: a lens flare runs along the red swoosh and bursts at its tip, the lander's engines
  flicker, the stars twinkle and light sweeps across the rings. The splash stays up until it has played
  (click to skip); still for anyone who has reduced motion turned on.

## [0.1.0] - 2026-10-28

First release.

- Live Amtrak positions from the Transitdocs GTFS-RT feed, with route, train number, destination and
  station names from Amtrak's static GTFS (refreshed daily).
- Amtraker API as an automatic fallback while the Transitdocs feed is down.
- Commuter rail: MBTA, LIRR, Metro-North and SEPTA (no key needed); Metra, Caltrain, Metrolink and
  NJ Transit when their API keys are set in `.env`.
- One normalized vehicle model, cached on the server and pushed to browsers over WebSocket.
- MapLibre map over FRA NARN passenger track, downloaded on first start.
- Agency filters, feed-health lights, search by train number or route, light and dark themes.
- Trains change with zoom: arrows, then a top-down train icon, then the full train drawn to scale car by
  car along the real track, gliding between updates. Detailed track (ballast, ties, rails, multiple tracks).
- SEPTA and LIRR train numbers from trip IDs; SEPTA trains drawn with their live car count.
- Designed and Created by Project Moon Pi: logo on the start-up splash, header, favicon, About section and README.
- Credits for every data feed, library, font and the basemap, in the README and the in-app About section.
- Trains that have not departed yet (future-stamped positions at their origin) are hidden.
- `train-tracker` command: `--port` (default 7500), `--host`, `--data-dir`, `--config`, `fetch-track`.
