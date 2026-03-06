param(
    [string]$ServiceName = "itinvent-scan-agent",
    [string]$ProjectRoot = "C:\Project\Image_scan",
    [string]$PythonExe = "",
    [string]$AgentScript = "scan_agent\agent.py"
)

$ErrorActionPreference = "Stop"

function Normalize-InputPath {
    param([string]$Value)

    $text = [string]$Value
    if (-not $text) { return "" }

    $text = $text.Replace([char]0x201C, '"').Replace([char]0x201D, '"')
    $text = $text.Replace([char]0x00A0, ' ')
    $text = $text.Trim().Trim('"').Trim("'").Trim()
    return $text
}

function Resolve-PythonPath {
    param(
        [string]$ProjectRoot,
        [string]$PythonExe
    )

    $projectRootClean = Normalize-InputPath $ProjectRoot
    $pythonExeClean = Normalize-InputPath $PythonExe

    if ($pythonExeClean -and (Test-Path -LiteralPath $pythonExeClean)) {
        return $pythonExeClean
    }

    $venvPython = Join-Path $projectRootClean ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        return $venvPython
    }

    $cmdPython = Get-Command python -ErrorAction SilentlyContinue
    if ($cmdPython) {
        return $cmdPython.Source
    }

    throw "Python not found. Use -PythonExe or prepare .venv."
}

function Resolve-NssmPath {
    $cmd = Get-Command nssm -ErrorAction SilentlyContinue
    if (-not $cmd) {
        return $null
    }
    return $cmd.Source
}

$ProjectRoot = Normalize-InputPath $ProjectRoot
$PythonExe = Normalize-InputPath $PythonExe
$AgentScript = Normalize-InputPath $AgentScript

$pythonPath = Resolve-PythonPath -ProjectRoot $ProjectRoot -PythonExe $PythonExe
$nssmPath = Resolve-NssmPath
$logsDir = Join-Path $ProjectRoot "logs"
$scriptPath = Join-Path $ProjectRoot $AgentScript

if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "Agent script not found: $scriptPath"
}

New-Item -ItemType Directory -Force $logsDir | Out-Null

$args = "$scriptPath"
$commandLine = "`"$pythonPath`" `"$scriptPath`""

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($nssmPath) {
    if ($existing) {
        & $nssmPath set $ServiceName Application $pythonPath | Out-Null
        & $nssmPath set $ServiceName AppParameters $args | Out-Null
        & $nssmPath set $ServiceName AppDirectory $ProjectRoot | Out-Null
    }
    else {
        & $nssmPath install $ServiceName $pythonPath $args | Out-Null
        & $nssmPath set $ServiceName AppDirectory $ProjectRoot | Out-Null
    }

    & $nssmPath set $ServiceName ObjectName "LocalSystem" | Out-Null
    & $nssmPath set $ServiceName Start SERVICE_AUTO_START | Out-Null
    & $nssmPath set $ServiceName AppStdout (Join-Path $logsDir "scan-agent-service.out.log") | Out-Null
    & $nssmPath set $ServiceName AppStderr (Join-Path $logsDir "scan-agent-service.err.log") | Out-Null
    & $nssmPath set $ServiceName AppRotateFiles 1 | Out-Null
    & $nssmPath set $ServiceName AppRotateOnline 1 | Out-Null
    & $nssmPath set $ServiceName AppRotateBytes 10485760 | Out-Null
}
else {
    Write-Warning "NSSM not found in PATH. Falling back to sc.exe service installation."
    if ($existing) {
        try { Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue } catch {}
        & sc.exe config $ServiceName binPath= $commandLine start= auto obj= LocalSystem | Out-Null
    }
    else {
        & sc.exe create $ServiceName binPath= $commandLine start= auto obj= LocalSystem DisplayName= "IT-Invent Scan Agent" | Out-Null
    }
    & sc.exe description $ServiceName "IT-Invent Scan Agent service" | Out-Null
}

Start-Service -Name $ServiceName
Write-Host "Service started: $ServiceName"
