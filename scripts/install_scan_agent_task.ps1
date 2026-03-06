param(
    [string]$TaskName = "IT-Invent Scan Agent",
    [string]$PythonExe = "C:\Python312\python.exe",
    [string]$ScriptPath = "C:\Program Files\IT-Invent\ScanAgent\agent.py",
    [int]$RepeatMinutes = 1
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -Path $PythonExe)) {
    throw "Python not found: $PythonExe"
}
if (-not (Test-Path -Path $ScriptPath)) {
    throw "Script not found: $ScriptPath"
}
if ($RepeatMinutes -lt 1) {
    throw "RepeatMinutes must be >= 1"
}

$workDir = Split-Path -Path $ScriptPath -Parent

$action = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ScriptPath`"" -WorkingDirectory $workDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.RepetitionInterval = (New-TimeSpan -Minutes $RepeatMinutes)
$trigger.RepetitionDuration = (New-TimeSpan -Days 3650)

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings

Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
Write-Host "Task '$TaskName' registered successfully."

