param(
    [string]$TaskName = "IT-Invent Agent",
    [string]$OutlookTaskName = "ITInventOutlookProbe"
)

$ErrorActionPreference = "Stop"

$mainTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $mainTask) {
    Write-Host "Scheduled task '$TaskName' does not exist."
} else {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Scheduled task '$TaskName' removed successfully."
}

$outlookTask = Get-ScheduledTask -TaskName $OutlookTaskName -ErrorAction SilentlyContinue
if ($null -eq $outlookTask) {
    Write-Host "Scheduled task '$OutlookTaskName' does not exist."
} else {
    Unregister-ScheduledTask -TaskName $OutlookTaskName -Confirm:$false
    Write-Host "Scheduled task '$OutlookTaskName' removed successfully."
}
