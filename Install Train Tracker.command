#!/bin/bash
# Install US Train Tracker on this Mac. Double-click to run; run it again later to update.
#
# It installs the program in ~/Library/Application Support/Train Tracker, sets it up as a background service,
# and puts Start Train Tracker and Stop Train Tracker on your Desktop and in Applications › Train Tracker.
# Needs Python 3.10 or newer from python.org. Designed and Created by Project Moon Pi.
#
# For unattended installs, answer the questions ahead: TT_PHONES=yes|no TT_AUTOSTART=yes|no TT_OPEN=no
SRC="$(cd "$(dirname "$0")" && pwd)"
. "$SRC/installer/mac/common.sh"
set -e

ask() {   # ask "question" "no-button" "yes-button" -> prints yes or no
  local b
  b=$(osascript -e "button returned of (display dialog \"$1\" buttons {\"$2\", \"$3\"} default button \"$3\" with title \"Install Train Tracker\")" 2>/dev/null) || b=""
  [ "$b" = "$3" ] && echo yes || echo no
}

find_python() {
  for p in python3.14 python3.13 python3.12 python3.11 python3.10 \
           /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /opt/homebrew/bin/python3 \
           /usr/local/bin/python3 python3; do
    if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
      command -v "$p"; return 0
    fi
  done
  return 1
}

echo "US Train Tracker installer - Designed and Created by Project Moon Pi"
PY=$(find_python) || {
  echo "Train Tracker needs Python 3.10 or newer: install it from https://www.python.org/downloads/ and run this again."
  osascript -e 'display dialog "Train Tracker needs Python 3.10 or newer.\n\nClick Download to get it from python.org, install it, then double-click Install Train Tracker again." buttons {"Cancel", "Download"} default button "Download" with title "Install Train Tracker"' \
    -e 'if button returned of result is "Download" then open location "https://www.python.org/downloads/"' >/dev/null 2>&1 || true
  exit 1
}

PHONES=${TT_PHONES:-$(ask "Should phones and tablets on your Wi-Fi be able to open the train map?\n\nThey'll find the address and a QR code in the map's panel." "This Mac only" "Phones too")}
AUTOSTART=${TT_AUTOSTART:-$(ask "Start Train Tracker by itself whenever you log in?\n\nOtherwise, use the Start Train Tracker icon when you want it." "No" "Yes")}

# an update: stop the running service first
launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true

echo "Installing with $("$PY" --version) into $APPDIR (about a minute)…"
mkdir -p "$APPDIR" "$APPS" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
[ -x "$APPDIR/venv/bin/python" ] || "$PY" -m venv "$APPDIR/venv"
"$APPDIR/venv/bin/python" -m pip install --quiet --upgrade pip
"$APPDIR/venv/bin/python" -m pip install --quiet --upgrade "$SRC"
VERSION=$("$APPDIR/venv/bin/python" -c 'import train_tracker; print(train_tracker.__version__)')
printf 'PORT=%s\nPHONES=%s\nAUTOSTART=%s\n' "$PORT" "$PHONES" "$AUTOSTART" > "$APPDIR/settings.sh"

# the background service (a LaunchAgent: runs as you, only while you're logged in)
HOSTARGS=""
[ "$PHONES" = yes ] && HOSTARGS="<string>--host</string><string>0.0.0.0</string>"
RUNATLOAD=false
[ "$AUTOSTART" = yes ] && RUNATLOAD=true
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$APPDIR/venv/bin/train-tracker</string>
    <string>--port</string><string>$PORT</string>
    <string>--log-file</string><string>$LOG</string>
    $HOSTARGS
  </array>
  <key>WorkingDirectory</key><string>$APPDIR</string>
  <key>RunAtLoad</key><$RUNATLOAD/>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
PLIST

# the apps: Start, Stop and Uninstall, each a tiny app wrapping its script
make_app() {   # make_app "Name" script icon id
  local app="$APPS/$1.app"
  rm -rf "$app"
  mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
  cp "$SRC/installer/mac/$2" "$app/Contents/MacOS/run"
  cp "$SRC/installer/mac/common.sh" "$app/Contents/MacOS/common.sh"
  chmod +x "$app/Contents/MacOS/run"
  cp "$SRC/installer/icons/$3.icns" "$app/Contents/Resources/icon.icns"
  cat > "$app/Contents/Info.plist" <<INFO
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$1</string>
  <key>CFBundleDisplayName</key><string>$1</string>
  <key>CFBundleIdentifier</key><string>$LABEL.$4</string>
  <key>CFBundleExecutable</key><string>run</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>NSHumanReadableCopyright</key><string>Designed and Created by Project Moon Pi</string>
  <key>LSUIElement</key><true/>
</dict>
</plist>
INFO
  touch "$app"
}
make_app "Start Train Tracker" start.sh start start
make_app "Stop Train Tracker" stop.sh stop stop
make_app "Uninstall Train Tracker" uninstall.sh app uninstall
# files from a downloaded zip carry macOS's "downloaded" flag; apps built here shouldn't
xattr -dr com.apple.quarantine "$APPS" 2>/dev/null || true
ln -sfn "$APPS/Start Train Tracker.app" "$HOME/Desktop/Start Train Tracker"
ln -sfn "$APPS/Stop Train Tracker.app" "$HOME/Desktop/Stop Train Tracker"

launchctl bootstrap "$DOMAIN" "$PLIST"
echo "Installed US Train Tracker $VERSION. Starting it…"
if [ "${TT_OPEN:-yes}" = no ]; then
  "$APPS/Start Train Tracker.app/Contents/MacOS/run" --no-browser
else
  "$APPS/Start Train Tracker.app/Contents/MacOS/run"
fi
echo "Done. Use Start Train Tracker and Stop Train Tracker on your Desktop (also in Applications › Train Tracker)."
[ -n "$TT_PHONES" ] || osascript -e 'display dialog "Train Tracker is installed and running.\n\nUse Start Train Tracker and Stop Train Tracker on your Desktop (also in your Applications folder, under Train Tracker).\n\nYou can delete the downloaded folder now." buttons {"OK"} default button "OK" with title "Install Train Tracker"' >/dev/null 2>&1 || true
