param(
    [string]$ServiceName = "itinvent-backend",
    [string]$ProjectRoot = "C:\Project\Image_scan",
    [string]$PythonExe = "",
    [int]$BackendPort = 8001
)

$ErrorActionPreference = "Stop"

function Resolve-PythonPath {
    param(
        [string]$ProjectRoot,
        [string]$PythonExe
    )

    if ($PythonExe -and (Test-Path $PythonExe)) {
        return $PythonExe
    }

    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    $cmdPython = Get-Command python -ErrorAction SilentlyContinue
    if ($cmdPython) {
        return $cmdPython.Source
    }

    throw "Python was not found. Use -PythonExe or create .venv in project root."
}

function Resolve-NssmPath {
    $cmd = Get-Command nssm -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "NSSM was not found in PATH. Install NSSM first."
    }
    return $cmd.Source
}

$pythonPath = Resolve-PythonPath -ProjectRoot $ProjectRoot -PythonExe $PythonExe
$nssmPath = Resolve-NssmPath
$backendMain = Join-Path $ProjectRoot "WEB-itinvent\backend\main.py"
$logsDir = Join-Path $ProjectRoot "logs"

if (-not (Test-Path $backendMain)) {
    throw "Backend entry file not found: $backendMain"
}

Write-Host "Python: $pythonPath"
Write-Host "NSSM:   $nssmPath"
Write-Host "Svc:    $ServiceName"

New-Item -ItemType Directory -Force $logsDir | Out-Null

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Service exists. Updating configuration..."
    & $nssmPath set $ServiceName Application $pythonPath | Out-Null
    & $nssmPath set $ServiceName AppParameters $backendMain | Out-Null
    & $nssmPath set $ServiceName AppDirectory $ProjectRoot | Out-Null
}
else {
    Write-Host "Installing service..."
    & $nssmPath install $ServiceName $pythonPath $backendMain | Out-Null
    & $nssmPath set $ServiceName AppDirectory $ProjectRoot | Out-Null
}

& $nssmPath set $ServiceName AppStdout (Join-Path $logsDir "backend-service.out.log") | Out-Null
& $nssmPath set $ServiceName AppStderr (Join-Path $logsDir "backend-service.err.log") | Out-Null
& $nssmPath set $ServiceName AppRotateFiles 1 | Out-Null
& $nssmPath set $ServiceName AppRotateOnline 1 | Out-Null
& $nssmPath set $ServiceName AppRotateBytes 10485760 | Out-Null
& $nssmPath set $ServiceName AppEnvironmentExtra "BACKEND_PORT=$BackendPort" | Out-Null

Start-Service -Name $ServiceName
Write-Host "Service started: $ServiceName (port $BackendPort)"
