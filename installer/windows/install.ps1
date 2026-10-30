# Install US Train Tracker on this PC (run by "Install Train Tracker.bat"; run it again later to update).
#
# Installs the program in %LOCALAPPDATA%\TrainTracker and puts Start Train Tracker and Stop Train Tracker on
# the Desktop and in the Start menu. Needs Python 3.10 or newer from python.org.
# Designed and Created by Project Moon Pi.
#
# For unattended installs, answer the questions ahead: TT_PHONES=yes|no TT_AUTOSTART=yes|no TT_OPEN=no
$ErrorActionPreference = 'Stop'
$Src = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$AppDir = Join-Path $env:LOCALAPPDATA 'TrainTracker'
$Port = 7500
Add-Type -AssemblyName System.Windows.Forms

function Ask($preset, $text) {
    if ($preset) { return $preset -eq 'yes' }
    return [System.Windows.Forms.MessageBox]::Show($text, 'Install Train Tracker', 'YesNo', 'Question') -eq 'Yes'
}

function Run($exe, $argv, $what) {
    & $exe @argv
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" }
}

Write-Host 'US Train Tracker installer - Designed and Created by Project Moon Pi'

# Python 3.10 or newer: the "py" launcher from python.org, or python on the PATH
$check = @('-c', 'import sys; sys.exit(sys.version_info < (3, 10))')
$py = $null
foreach ($c in @(@{exe = 'py'; pre = @('-3')}, @{exe = 'python'; pre = @()})) {
    if (-not (Get-Command $c.exe -ErrorAction SilentlyContinue)) { continue }
    $argv = $c.pre + $check
    try { & $c.exe @argv 2>$null } catch { continue }    # e.g. the Microsoft Store's "python" placeholder
    if ($LASTEXITCODE -eq 0) { $py = $c; break }
}
if (-not $py) {
    Write-Host 'Train Tracker needs Python 3.10 or newer from https://www.python.org/downloads/'
    $go = [System.Windows.Forms.MessageBox]::Show(
        "Train Tracker needs Python 3.10 or newer.`n`nClick OK to open python.org. In the installer, tick `"Add python.exe to PATH`", then run Install Train Tracker again.",
        'Install Train Tracker', 'OKCancel', 'Information')
    if ($go -eq 'OK') { Start-Process 'https://www.python.org/downloads/' }
    exit 1
}

$phones = Ask $env:TT_PHONES "Should phones and tablets on your Wi-Fi be able to open the train map?`n`nThey'll find the address and a QR code in the map's panel. If the firewall needs opening for them, Windows asks for permission once (click Yes)."
$autostart = Ask $env:TT_AUTOSTART "Start Train Tracker by itself whenever you sign in to Windows?`n`nOtherwise, use the Start Train Tracker icon when you want it."

# an update: stop the running service first
if (Test-Path (Join-Path $AppDir 'stop.ps1')) { & (Join-Path $AppDir 'stop.ps1') -Quiet }

Write-Host "Installing into $AppDir (about a minute)..."
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
$venvPy = Join-Path $AppDir 'venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) { Run $py.exe ($py.pre + @('-m', 'venv', (Join-Path $AppDir 'venv'))) 'Setting up Python' }
Run $venvPy @('-m', 'pip', 'install', '--quiet', '--upgrade', 'pip') 'Updating pip'
Run $venvPy @('-m', 'pip', 'install', '--quiet', '--upgrade', $Src) 'Installing Train Tracker'
$version = & $venvPy -c 'import train_tracker; print(train_tracker.__version__)'

foreach ($f in 'start.ps1', 'stop.ps1', 'uninstall.ps1', 'firewall.ps1') { Copy-Item (Join-Path $PSScriptRoot $f) $AppDir -Force }
foreach ($f in 'start.ico', 'stop.ico', 'app.ico') { Copy-Item (Join-Path $Src "installer\icons\$f") $AppDir -Force }
Get-ChildItem $AppDir -File | Unblock-File      # drop the "downloaded from the internet" mark on our own copies
@{ port = $Port; phones = $phones; autostart = $autostart; version = "$version" } | ConvertTo-Json |
    Set-Content (Join-Path $AppDir 'settings.json')

# shortcuts: Desktop and Start menu, plus the Startup folder when it should start at sign-in
$shell = New-Object -ComObject WScript.Shell
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
function New-Shortcut($path, $script, $icon, $desc, $extra = '') {
    $s = $shell.CreateShortcut($path)
    $s.TargetPath = $powershell
    $s.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$(Join-Path $AppDir $script)`" $extra"
    $s.IconLocation = "$(Join-Path $AppDir $icon),0"
    $s.WorkingDirectory = $AppDir
    $s.Description = $desc
    $s.WindowStyle = 7
    $s.Save()
}
$desktop = [Environment]::GetFolderPath('Desktop')
$menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'Train Tracker'
New-Item -ItemType Directory -Force -Path $menu | Out-Null
foreach ($dir in $desktop, $menu) {
    New-Shortcut (Join-Path $dir 'Start Train Tracker.lnk') 'start.ps1' 'start.ico' 'Start US Train Tracker and open the map'
    New-Shortcut (Join-Path $dir 'Stop Train Tracker.lnk') 'stop.ps1' 'stop.ico' 'Stop US Train Tracker'
}
New-Shortcut (Join-Path $menu 'Uninstall Train Tracker.lnk') 'uninstall.ps1' 'app.ico' 'Remove US Train Tracker from this PC'
$startupLink = Join-Path ([Environment]::GetFolderPath('Startup')) 'Train Tracker.lnk'
if ($autostart) { New-Shortcut $startupLink 'start.ps1' 'start.ico' 'Start US Train Tracker at sign-in' '-NoBrowser' }
else { Remove-Item $startupLink -ErrorAction SilentlyContinue }

# phones: make sure the firewall lets them in on home networks (Windows asks for permission only if needed)
$fw = Join-Path $AppDir 'firewall.ps1'
$networkNote = ''
if ($phones) {
    $pythonw = & $venvPy -c "import os, sys; print(os.path.join(sys.base_prefix, 'pythonw.exe'))"   # the program that listens
    Write-Host 'Checking that phones on your home network can reach Train Tracker...'
    $state = & $fw -Allow -Port $Port -Program $pythonw
    $public = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue | Where-Object NetworkCategory -eq 'Public').Count
    if ($state -eq 'Declined') {
        $networkNote = "Windows didn't allow the firewall change, so phones can't reach the map yet. Run the installer again and click Yes when Windows asks."
    } elseif ($public -and $state -ne 'AllowedPublic') {
        $networkNote = "This PC's network is set to Public, where Windows keeps other devices out. For phones to reach the map, set your home Wi-Fi to Private: Settings > Network & Internet > (your connection) > Private."
    }
} else {
    & $fw -Port $Port
}
if ($networkNote) { Write-Host $networkNote }

Write-Host "Installed US Train Tracker $version. Starting it..."
if ($env:TT_OPEN -eq 'no') { & (Join-Path $AppDir 'start.ps1') -NoBrowser } else { & (Join-Path $AppDir 'start.ps1') }
Write-Host 'Done. Use Start Train Tracker and Stop Train Tracker on your Desktop (also in the Start menu).'
if (-not $env:TT_PHONES) {
    [System.Windows.Forms.MessageBox]::Show(
        "Train Tracker is installed and running.`n`nUse Start Train Tracker and Stop Train Tracker on your Desktop (also in the Start menu, under Train Tracker).`n`nYou can delete the downloaded folder now." + $(if ($networkNote) { "`n`n$networkNote" } else { '' }),
        'Install Train Tracker', 'OK', 'Information') | Out-Null
}
