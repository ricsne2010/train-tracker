#!/bin/bash
# US Train Tracker for macOS. Double-click to start; close this window to stop.
# The first start sets it up in this folder (about a minute); it needs Python 3.10 or newer from python.org.
# Designed and Created by Project Moon Pi.
cd "$(dirname "$0")" || exit 1

find_python() {
  for p in python3.14 python3.13 python3.12 python3.11 python3.10 \
           /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /opt/homebrew/bin/python3 \
           /usr/local/bin/python3 python3; do
    if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
      echo "$p"; return 0
    fi
  done
  return 1
}

needs_setup() {
  [ -x .venv/bin/train-tracker ] || return 0
  # a developer checkout (pip install -e) runs straight from src/: nothing to do
  case "$(.venv/bin/python -c 'import train_tracker; print(train_tracker.__file__)' 2>/dev/null)" in
    "$PWD/src/"*) return 1 ;;
  esac
  [ src/train_tracker/__init__.py -nt .venv/.installed ] || [ pyproject.toml -nt .venv/.installed ]
}

if needs_setup; then
  PY=$(find_python)
  if [ -z "$PY" ]; then
    echo "US Train Tracker needs Python 3.10 or newer."
    echo "Install it from https://www.python.org/downloads/ (the macOS installer), then double-click this again."
    osascript -e 'display dialog "US Train Tracker needs Python 3.10 or newer.\n\nClick Download to get it from python.org, install it, then double-click Start Train Tracker again." buttons {"Cancel", "Download"} default button "Download" with title "US Train Tracker"' \
      -e 'if button returned of result is "Download" then open location "https://www.python.org/downloads/"' >/dev/null 2>&1
    exit 1
  fi
  echo "Setting up US Train Tracker with $("$PY" --version) (first start or after an update)…"
  [ -x .venv/bin/python ] || "$PY" -m venv .venv || exit 1
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet . || { echo "Setup failed: see the messages above."; exit 1; }
  touch .venv/.installed
fi

echo "Starting US Train Tracker. The map opens in your browser; close this window to stop it."
exec .venv/bin/train-tracker --open "$@"
