param(
    [string]$TaskName = "IT-Invent Agent",
    [string]$ExecutablePath = "C:\Program Files\IT-Invent\Agent\ITInventAgent.exe",
    [int]$RepeatMinutes = 60
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -Path $ExecutablePath)) {
    throw "Executable not found: $ExecutablePath"
}

if ($RepeatMinutes -lt 1) {
    throw "RepeatMinutes must be >= 1"
}

$workDir = Split-Path -Path $ExecutablePath -Parent
$action = New-ScheduledTaskAction -Execute $ExecutablePath -WorkingDirectory $workDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.RepetitionInterval = (New-TimeSpan -Minutes $RepeatMinutes)
$trigger.RepetitionDuration = (New-TimeSpan -Days 3650)

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
Write-Host "Scheduled task '$TaskName' registered successfully."
