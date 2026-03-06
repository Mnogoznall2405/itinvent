param(
    [string]$ProjectRoot = "C:\Project\Image_scan",
    [string]$IisSitePath = "C:\inetpub\wwwroot\itinvent",
    [switch]$Mirror
)

$ErrorActionPreference = "Stop"

$frontendPath = Join-Path $ProjectRoot "WEB-itinvent\frontend"
$distPath = Join-Path $frontendPath "dist"

if (-not (Test-Path $frontendPath)) {
    throw "Frontend path not found: $frontendPath"
}

Write-Host "Build frontend in: $frontendPath"
Push-Location $frontendPath
try {
    npm ci
    npm run build
}
finally {
    Pop-Location
}

if (-not (Test-Path $distPath)) {
    throw "Build output not found: $distPath"
}

New-Item -ItemType Directory -Force $IisSitePath | Out-Null

Write-Host "Copy dist -> IIS site path: $IisSitePath"
if ($Mirror) {
    # Full mirror deploy: removes files missing in dist.
    robocopy $distPath $IisSitePath /MIR /R:2 /W:2 | Out-Null
} else {
    # Safe deploy: keep old hashed assets to avoid chunk 404 for cached clients.
    robocopy $distPath $IisSitePath /E /R:2 /W:2 | Out-Null
}

Write-Host "Frontend published to IIS path: $IisSitePath"
