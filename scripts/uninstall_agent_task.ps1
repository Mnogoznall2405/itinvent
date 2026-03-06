param(
    [string]$TaskName = "IT-Invent Agent"
)

$ErrorActionPreference = "Stop"

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $existing) {
    Write-Host "Scheduled task '$TaskName' does not exist."
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Scheduled task '$TaskName' removed successfully."
