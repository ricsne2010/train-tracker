#!/bin/bash
# Stop Train Tracker: shuts down the background service. The map stops updating until it's started again.
. "$(dirname "$0")/common.sh"
launchctl kill SIGTERM "$DOMAIN/$LABEL" >/dev/null 2>&1
for _ in $(seq 1 20); do up || break; sleep 0.5; done
if up; then
  alert "Train Tracker is still running" "Something else is using port $PORT, or it didn't stop. Try again, or restart the Mac."
else
  notify "Train Tracker has stopped."
fi
