# Agent Pilot Guide

## 1) Install MSI on one pilot PC

Run with admin rights:

```powershell
msiexec /i "C:\Path\IT-Invent Agent-win64.msi" /qn /norestart /l*v "C:\Temp\itinvent_agent_install.log"
```

Expected binary path:

- `C:\Program Files\IT-Invent\Agent\ITInventAgent.exe`

## 2) Set runtime configuration (pilot)

```powershell
$env:ITINV_AGENT_SERVER_URL = "https://hubit.zsgp.ru/api/v1/inventory"
$env:ITINV_AGENT_API_KEY = "itinvent_agent_secure_token_v1"
$env:ITINV_AGENT_INTERVAL_SEC = "3600"

# Unified scan sidecar in the same agent process
$env:ITINV_SCAN_ENABLED = "1"
$env:SCAN_AGENT_SERVER_BASE = "https://hubit.zsgp.ru/api/v1/scan"
$env:SCAN_AGENT_API_KEY = "itinvent_agent_secure_token_v1"
$env:SCAN_AGENT_POLL_INTERVAL_SEC = "60"
$env:SCAN_AGENT_WATCHDOG_ENABLED = "1"
```

## 3) Validate connectivity

```powershell
& "C:\Program Files\IT-Invent\Agent\ITInventAgent.exe" --check
```

Exit code `0` means config + endpoint are reachable.

## 4) Send one test report

```powershell
& "C:\Program Files\IT-Invent\Agent\ITInventAgent.exe" --once
```

## 5) Verify logs

All runs write to:

- `C:\ProgramData\IT-Invent\Logs\itinvent_agent.log`

Check for:

- startup config line
- inventory collection line
- successful send status

## 6) Verify UI data

Open `/computers` and confirm:

- `current_user` is the active console user (not `SYSTEM` when someone is logged in)
- virtual/empty physical disks are not shown
- container/service mount points are not shown
- monitor serial uses EDID when available, otherwise WMI fallback

Open `/scan-center` and confirm:

- agent appears in list
- `scan_now` and `ping` buttons work
- incidents appear for matching test files

## 7) Register autostart task (after pilot)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_agent_task.ps1
```

Remove task:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall_agent_task.ps1
```
