param(
    [string]$ServiceName = "itinvent-scan-backend",
    [string]$ProjectRoot = "C:\Project\Image_scan",
    [string]$PythonExe = "",
    [int]$Port = 8011
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

$pythonPath = Resolve-PythonPath -ProjectRoot $ProjectRoot -PythonExe $PythonExe
$nssmPath = Resolve-NssmPath
$logsDir = Join-Path $ProjectRoot "logs"

New-Item -ItemType Directory -Force $logsDir | Out-Null

$args = "-m uvicorn scan_server.app:app --host 127.0.0.1 --port $Port"
$commandLine = "`"$pythonPath`" -m uvicorn scan_server.app:app --host 127.0.0.1 --port $Port --app-dir `"$ProjectRoot`""

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

    & $nssmPath set $ServiceName AppStdout (Join-Path $logsDir "scan-service.out.log") | Out-Null
    & $nssmPath set $ServiceName AppStderr (Join-Path $logsDir "scan-service.err.log") | Out-Null
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
        & sc.exe create $ServiceName binPath= $commandLine start= auto obj= LocalSystem DisplayName= "IT-Invent Scan Backend" | Out-Null
    }
    & sc.exe description $ServiceName "IT-Invent Scan Backend service" | Out-Null
}

Start-Service -Name $ServiceName
Write-Host "Service started: $ServiceName (127.0.0.1:$Port)"
