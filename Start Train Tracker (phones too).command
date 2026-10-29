#!/bin/bash
# Like "Start Train Tracker", but phones and tablets on the same Wi-Fi can open the map too.
# The map's panel shows the address and a QR code to scan ("Open on your phone").
cd "$(dirname "$0")" || exit 1
exec "./Start Train Tracker.command" --host 0.0.0.0 "$@"
