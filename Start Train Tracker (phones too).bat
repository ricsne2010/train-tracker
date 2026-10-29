@echo off
rem Like "Start Train Tracker", but phones and tablets on the same Wi-Fi can open the map too.
rem Windows may ask whether to allow Python on your network: allow it on Private networks.
rem The map panel shows the address and a QR code to scan ("Open on your phone").
call "%~dp0Start Train Tracker.bat" --host 0.0.0.0 %*
