# Let phones and tablets on your home network reach Train Tracker (or stop letting them).
#   firewall.ps1 -Allow   adds an inbound rule for its port, on Private (home) and Domain networks only
#   firewall.ps1          removes the rule
# Changing the firewall needs admin rights, so Windows asks once ("allow this app to make changes?").
# Designed and Created by Project Moon Pi.
param([switch]$Allow, [int]$Port = 7500)
$name = 'US Train Tracker (phones on your network)'

$have = [bool](Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue)
if ($Allow -eq $have) { return $true }      # already as wanted

$cmd = if ($Allow) {
    "New-NetFirewallRule -DisplayName '$name' -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -Profile Private,Domain | Out-Null"
} else {
    "Remove-NetFirewallRule -DisplayName '$name'"
}
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole('Administrators')
try {
    if ($admin) {
        Invoke-Expression $cmd
    } else {
        $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cmd))
        Start-Process powershell.exe -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList "-NoProfile -EncodedCommand $encoded"
    }
} catch {
    return $false    # the admin prompt was declined
}
return ([bool](Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue) -eq [bool]$Allow)
