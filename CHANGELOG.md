# Changelog

All notable changes to this project are listed here. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-27

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
