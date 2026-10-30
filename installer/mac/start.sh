#!/bin/bash
# Start Train Tracker: starts the background service if it isn't running, then opens the map.
# --no-browser: start it without opening the map.
. "$(dirname "$0")/common.sh"
if ! up; then
  launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1 || launchctl bootstrap "$DOMAIN" "$PLIST"
  launchctl kickstart "$DOMAIN/$LABEL"
  notify "Starting… The very first start takes a minute or two while it downloads maps and schedules."
  for _ in $(seq 1 240); do up && break; sleep 1; done
  if ! up; then
    alert "Train Tracker didn't start" "Its messages are in ~/Library/Logs/Train Tracker.log"
    exit 1
  fi
fi
[ "$1" = "--no-browser" ] || open "http://127.0.0.1:$PORT"
