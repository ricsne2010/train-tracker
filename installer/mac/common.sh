# Shared by the Train Tracker apps on macOS (copied into each app when installed).
LABEL=com.projectmoonpi.train-tracker
APPDIR="$HOME/Library/Application Support/Train Tracker"
APPS="$HOME/Applications/Train Tracker"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/Train Tracker.log"
DOMAIN="gui/$(id -u)"
PORT=7500
[ -f "$APPDIR/settings.sh" ] && . "$APPDIR/settings.sh"

up() { curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/api/info"; }
notify() { osascript -e "display notification \"$1\" with title \"Train Tracker\"" >/dev/null 2>&1; }
alert() { osascript -e "display alert \"$1\" message \"$2\"" >/dev/null 2>&1; }
