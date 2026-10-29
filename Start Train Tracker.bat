@echo off
rem US Train Tracker for Windows. Double-click to start; close this window to stop.
rem The first start sets it up in this folder (about a minute); it needs Python 3.10 or newer from python.org.
rem Designed and Created by Project Moon Pi.
setlocal
cd /d "%~dp0"
title US Train Tracker

if exist ".venv\Scripts\train-tracker.exe" if exist ".venv\installed.txt" goto run

set "PY="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 && set "PY=python"
if not defined PY (
  echo US Train Tracker needs Python 3.10 or newer.
  echo Install it from https://www.python.org/downloads/ - tick "Add python.exe to PATH" in the installer -
  echo then double-click Start Train Tracker again.
  start "" https://www.python.org/downloads/
  pause
  exit /b 1
)
echo Setting up US Train Tracker (first start or after an update)...
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv || goto failed
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet . || goto failed
echo installed> ".venv\installed.txt"

:run
echo Starting US Train Tracker. The map opens in your browser; close this window to stop it.
".venv\Scripts\train-tracker.exe" --open %*
pause
exit /b 0

:failed
echo Setup failed: see the messages above.
pause
exit /b 1
