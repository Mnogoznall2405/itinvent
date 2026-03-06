# SCAN Agent + Server: Windows / GPO Deployment

## 1. Scan Server (Windows Server)

1. Установить зависимости:
```powershell
cd C:\Project\Image_scan
.\.venv\Scripts\python.exe -m pip install -r scan_server\requirements.txt
```

2. Запустить как сервис:

Скрипт использует `nssm`, если он установлен, иначе автоматически переключается на `sc.exe`.

```powershell
.\scripts\iis\install_scan_service.ps1 `
  -ServiceName "itinvent-scan-backend" `
  -ProjectRoot "C:\Project\Image_scan" `
  -Port 8011
```

Для `sc.exe` режим важно запускать PowerShell от имени администратора.

```powershell
Get-Service itinvent-scan-backend
```

Если служба не создалась, проверьте права и повторите запуск в elevated PowerShell.

```powershell
Start-Process powershell -Verb RunAs
```

И затем снова:

```powershell
.\scripts\iis\install_scan_service.ps1 `
  -ServiceName "itinvent-scan-backend" `
  -ProjectRoot "C:\Project\Image_scan" `
  -Port 8011
```

3. Проверить health:
```powershell
Invoke-WebRequest http://127.0.0.1:8011/health
```

## 2. IIS routing

В `WEB-itinvent/frontend/public/web.config` уже добавлено правило:

- `^api/v1/scan/(.*)` -> `http://127.0.0.1:8011/api/v1/scan/{R:1}`

Важно: правило должно стоять выше общего `^api/(.*)`.

## 3. Агент через GPO

Раздайте на ПК:

- `scan_agent/agent.py`
- Python runtime (или собранный exe, если упаковываете отдельно)

Рекомендуемый путь:

- `C:\Program Files\IT-Invent\ScanAgent\agent.py`

### Переменные окружения (Machine scope)

- `SCAN_AGENT_SERVER_BASE=https://hubit.zsgp.ru/api/v1/scan`
- `SCAN_AGENT_API_KEY=itinvent_agent_secure_token_v1`
- `SCAN_AGENT_POLL_INTERVAL_SEC=60`
- `SCAN_AGENT_SCAN_ON_START=1`

### Рекомендуемо: Windows Service (SYSTEM)

```powershell
.\scripts\install_scan_agent_service.ps1 `
  -ProjectRoot "C:\Project\Image_scan" `
  -AgentScript "scan_agent\agent.py"
```

### Альтернатива: задача планировщика (SYSTEM)

```powershell
.\scripts\install_scan_agent_task.ps1 `
  -TaskName "IT-Invent Scan Agent" `
  -PythonExe "C:\Python312\python.exe" `
  -ScriptPath "C:\Program Files\IT-Invent\ScanAgent\agent.py" `
  -RepeatMinutes 1
```

## 4. Проверки после раскатки

1. На ПК:
- логи: `%ProgramData%\IT-Invent\ScanAgent\scan_agent.log`
- state: `%ProgramData%\IT-Invent\ScanAgent\scan_agent_state.json`
- watchdog режим включен по умолчанию (`SCAN_AGENT_WATCHDOG_ENABLED=1`)

2. На сервере:
- `GET /api/v1/scan/agents` показывает online/offline.
- `Scan Center` отображает очереди и инциденты.
