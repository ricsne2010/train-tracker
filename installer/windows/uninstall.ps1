# Uninstall Train Tracker: removes the service, the shortcuts and the program. Asks before deleting your data.
# Designed and Created by Project Moon Pi.
$AppDir = $PSScriptRoot
Add-Type -AssemblyName System.Windows.Forms
$unattended = [bool]$env:TT_UNATTENDED     # no questions; removes the program and keeps your data
if (-not $unattended) {
    $ok = [System.Windows.Forms.MessageBox]::Show('Remove Train Tracker from this PC?', 'Uninstall Train Tracker', 'OKCancel', 'Warning')
    if ($ok -ne 'OK') { exit 0 }
}
& (Join-Path $AppDir 'stop.ps1') -Quiet

$desktop = [Environment]::GetFolderPath('Desktop')
Remove-Item (Join-Path $desktop 'Start Train Tracker.lnk'), (Join-Path $desktop 'Stop Train Tracker.lnk') -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Startup')) 'Train Tracker.lnk') -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Programs')) 'Train Tracker') -Recurse -ErrorAction SilentlyContinue

if (-not $unattended) {
    $data = [System.Windows.Forms.MessageBox]::Show('Also delete the downloaded maps and schedules, and any API keys you saved?',
        'Uninstall Train Tracker', 'YesNo', 'Question')
    if ($data -eq 'Yes') { Remove-Item (Join-Path $env:USERPROFILE '.train-tracker') -Recurse -Force -ErrorAction SilentlyContinue }
}
Set-Location $env:TEMP      # Windows won't delete a folder that's in use
Remove-Item $AppDir -Recurse -Force -ErrorAction SilentlyContinue
if (-not $unattended) {
    [System.Windows.Forms.MessageBox]::Show('Train Tracker has been removed.', 'Uninstall Train Tracker', 'OK', 'Information') | Out-Null
}
