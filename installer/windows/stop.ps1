# Stop Train Tracker: shuts down the background service. The map stops updating until it's started again.
# -Quiet: no message afterwards (used by the installer and uninstaller).
# Designed and Created by Project Moon Pi.
param([switch]$Quiet)
$AppDir = $PSScriptRoot
$cfg = Get-Content (Join-Path $AppDir 'settings.json') -Raw | ConvertFrom-Json
$port = $cfg.port
$pidFile = Join-Path $AppDir 'train-tracker.pid'

function Stop-IfPython($id) {
    $p = Get-Process -Id $id -ErrorAction SilentlyContinue
    if ($p -and $p.ProcessName -like 'python*') { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
}
if (Test-Path $pidFile) {
    Stop-IfPython ([int](Get-Content $pidFile))
    Remove-Item $pidFile -ErrorAction SilentlyContinue
}
# also whatever Python program is serving the map on our port (started some other way)
Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-IfPython $_.OwningProcess }

$still = $true
for ($i = 0; $i -lt 20; $i++) {
    try { $null = Invoke-WebRequest "http://127.0.0.1:$port/api/info" -UseBasicParsing -TimeoutSec 1 }
    catch { $still = $false; break }
    Start-Sleep -Milliseconds 500
}
if (-not $Quiet) {
    $shell = New-Object -ComObject WScript.Shell
    if ($still) { $null = $shell.Popup("Train Tracker is still running: something else may be using port $port.", 0, 'Train Tracker', 48) }
    else { $null = $shell.Popup('Train Tracker has stopped.', 4, 'Train Tracker', 64) }
}
