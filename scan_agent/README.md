# IT-Invent Scan Agent

Агент сканирует только пользовательские папки:

- `C:\Users\*\Desktop`
- `C:\Users\*\Documents`
- `C:\Users\*\Downloads`

## Функции

- Хэширование файлов и локальный кэш, чтобы не пересканировать одно и то же.
- Локальный поиск паттернов по тексту.
- Watchdog (реакция в реальном времени на создание/изменение файлов).
- Для PDF:
  - если текст читаемый: локальный анализ;
  - если скан/кракозябры: отправка только первых 3 страниц.
- Polling задач (`ping`, `scan_now`) и heartbeat.

## Запуск

```powershell
pip install -r scan_agent/requirements.txt
python scan_agent/agent.py --once
```

Запуск постоянного режима:

```powershell
python scan_agent/agent.py
```

## Переменные окружения

- `SCAN_AGENT_SERVER_BASE` (default `https://hubit.zsgp.ru/api/v1/scan`)
- `SCAN_AGENT_API_KEY` (default `itinvent_agent_secure_token_v1`)
- `SCAN_AGENT_POLL_INTERVAL_SEC` (default `60`)
- `SCAN_AGENT_HTTP_TIMEOUT_SEC` (default `20`)
- `SCAN_AGENT_MAX_FILE_MB` (default `50`)
- `SCAN_AGENT_SCAN_ON_START` (`1|0`, default `1`)
- `SCAN_AGENT_WATCHDOG_ENABLED` (`1|0`, default `1`)
- `SCAN_AGENT_WATCHDOG_BATCH_SIZE` (default `200`)
- `SCAN_AGENT_ROOTS_REFRESH_SEC` (default `300`)
- `SCAN_AGENT_BRANCH` (optional)

## Установка как Windows Service

```powershell
.\scripts\install_scan_agent_service.ps1 -ProjectRoot "C:\Project\Image_scan"
```
