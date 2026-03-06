# IT-Invent Scan Server

Отдельный backend для контура сканирования документов.

## Запуск локально

```powershell
pip install -r scan_server/requirements.txt
python -m uvicorn scan_server.app:app --host 127.0.0.1 --port 8011
```

## Переменные окружения

- `SCAN_SERVER_HOST` (default `127.0.0.1`)
- `SCAN_SERVER_PORT` (default `8011`)
- `SCAN_SERVER_API_KEYS` (CSV key-ring, recommended)
- `SCAN_SERVER_API_KEY` (legacy single-key fallback)
- `SCAN_SERVER_DATA_DIR` (default `data/scan_server`)
- `SCAN_SERVER_DB_PATH` (default `data/scan_server/scan_server.db`)
- `SCAN_SERVER_ARCHIVE_DIR` (default `data/scan_server/archive`)
- `SCAN_RETENTION_DAYS` (default `90`)
- `SCAN_TASK_TTL_DAYS` (default `7`)
- `SCAN_TASK_ACK_TIMEOUT_SEC` (default `300`)

## Основные API

- `POST /api/v1/scan/heartbeat`
- `POST /api/v1/scan/ingest`
- `GET /api/v1/scan/tasks/poll`
- `POST /api/v1/scan/tasks/{task_id}/result`
- `POST /api/v1/scan/tasks`
- `GET /api/v1/scan/incidents`
- `POST /api/v1/scan/incidents/{id}/ack`
- `GET /api/v1/scan/dashboard`
- `GET /api/v1/scan/agents`
