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
- Trains that have not departed yet (future-stamped positions at their origin) are hidden.
- `train-tracker` command: `--port` (default 7500), `--host`, `--data-dir`, `--config`, `fetch-track`.
