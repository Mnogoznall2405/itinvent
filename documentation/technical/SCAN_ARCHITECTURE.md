# Scan Architecture (MVP)

## Цель

Добавить контур поиска чувствительных документов без влияния на текущий backend инвентаризации.

## Компоненты

1. `scan_agent/agent.py`
- Сканирует только:
  - `C:\Users\*\Desktop`
  - `C:\Users\*\Documents`
  - `C:\Users\*\Downloads`
- Watchdog отслеживает изменения в этих папках в реальном времени.
- Хэширует файлы и сохраняет state в `%ProgramData%\IT-Invent\ScanAgent\scan_agent_state.json`.
- Не пересканирует неизмененные/уже обработанные файлы.
- PDF:
  - текст читаемый -> локальный паттерн-анализ;
  - скан/кракозябры -> отправляет первые 3 страницы PDF.
- Polling задач: `ping`, `scan_now`.

2. `scan_server/app.py` (FastAPI, порт `127.0.0.1:8011`)
- API приема (`/ingest`, `/heartbeat`), очереди задач (`/tasks/poll`, `/tasks/{id}/result`), UI (`/incidents`, `/dashboard`, `/agents`).
- SQLite база: `data/scan_server/scan_server.db`.
- Worker обрабатывает задания последовательно и создает инциденты.

3. IIS reverse proxy
- `/api/v1/scan/*` -> `127.0.0.1:8011`
- `/api/*` -> `127.0.0.1:8001` (основной backend)

4. Frontend
- Страница `Scan Center` (`/scan-center`) с:
  - сводкой,
  - графиками (severity/филиалы/динамика),
  - статусами агентов/очередей,
  - инцидентами и ACK.

## Очередь оффлайн-команд

- Таблица `scan_tasks`.
- Статусы: `queued -> delivered -> acknowledged -> completed|failed|expired`.
- Если агент оффлайн: задачи остаются в `queued`.
- При poll доставляются по FIFO.
- TTL по умолчанию: 7 дней (`SCAN_TASK_TTL_DAYS`).
- Повторная доставка: backoff до 15 минут при отсутствии результата.

## Retention

- По умолчанию 90 дней (`SCAN_RETENTION_DAYS`).
- Worker раз в час чистит старые инциденты/задачи/артефакты.
