# Start Train Tracker: starts the background service if it isn't running, then opens the map.
# -NoBrowser: start it without opening the map (used at log-in).
# Designed and Created by Project Moon Pi.
param([switch]$NoBrowser)
$AppDir = $PSScriptRoot
$cfg = Get-Content (Join-Path $AppDir 'settings.json') -Raw | ConvertFrom-Json
$port = $cfg.port
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

function Test-Up {
    try { $null = Invoke-WebRequest "http://127.0.0.1:$port/api/info" -UseBasicParsing -TimeoutSec 2; return $true }
    catch { return $false }
}

if (-not (Test-Up)) {
    $log = Join-Path $AppDir 'train-tracker.log'
    $argv = @('-m', 'train_tracker', '--port', "$port", '--log-file', "`"$log`"")
    if ($cfg.phones) { $argv += @('--host', '0.0.0.0') }
    $p = Start-Process -FilePath (Join-Path $AppDir 'venv\Scripts\pythonw.exe') -ArgumentList $argv `
        -WorkingDirectory $AppDir -PassThru
    Set-Content -Path (Join-Path $AppDir 'train-tracker.pid') -Value $p.Id

    $note = New-Object System.Windows.Forms.NotifyIcon
    $note.Icon = New-Object System.Drawing.Icon (Join-Path $AppDir 'start.ico')
    $note.Visible = $true
    $note.ShowBalloonTip(8000, 'Train Tracker', 'Starting... The very first start takes a minute or two while it downloads maps and schedules.', 'Info')
    for ($i = 0; $i -lt 240; $i++) {
        if ((Test-Up) -or $p.HasExited) { break }
        Start-Sleep -Seconds 1
    }
    $note.Dispose()
    if (-not (Test-Up)) {
        [System.Windows.Forms.MessageBox]::Show("Train Tracker didn't start. Its messages are in $log", 'Train Tracker', 'OK', 'Error') | Out-Null
        exit 1
    }
}
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$port" }
