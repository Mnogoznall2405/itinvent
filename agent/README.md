# IT-Invent Agent Workspace

Основные файлы агента вынесены в `agent/`.

## Сборка MSI

Новый путь:

```powershell
python agent/setup.py bdist_msi
```

Совместимость сохранена:

```powershell
python setup.py bdist_msi
```

(корневой `setup.py` проксирует в `agent/setup.py`)

## Полезные директории

- `agent/setup.py` — сборка MSI
- `agent/src/itinvent_agent/agent.py` — код агента
- `agent/scripts/` — скрипты установки/удаления задачи планировщика
- `agent/docs/` — инструкции по пилоту и GPO

## Режимы запуска агента

```powershell
python agent.py --check
python agent.py --once
```

`agent.py` теперь единый: в одном процессе работает инвентаризация (`/api/v1/inventory`) и scan-контур (`/api/v1/scan/*`).
Outlook-данные собираются через файловый scan (`SYSTEM`) с приоритетом `email профиля -> имя файла`; если прямого совпадения нет, используется fallback по изменению размера.
Скрипт `agent/scripts/install_agent_task.ps1` создает одну задачу:
- `IT-Invent Agent` (SYSTEM, startup + repeat)

## Параметры окружения

- `ITINV_AGENT_SERVER_URL`
- `ITINV_AGENT_API_KEY`
- `ITINV_AGENT_ALLOW_DEFAULT_KEY` (`1|0`, по умолчанию `1`)
- `ITINV_RUN_CMD_TIMEOUT_SEC` (по умолчанию `20`)
- `ITINV_AGENT_INTERVAL_SEC` (full snapshot)
- `ITINV_AGENT_HEARTBEAT_SEC`
- `ITINV_AGENT_HEARTBEAT_JITTER_SEC`
- `ITINV_OUTLOOK_REFRESH_SEC` (по умолчанию `300`)
- `ITINV_INVENTORY_QUEUE_BATCH` (по умолчанию `50`)
- `ITINV_INVENTORY_QUEUE_MAX_ITEMS` (по умолчанию `1000`)
- `ITINV_INVENTORY_QUEUE_MAX_AGE_DAYS` (по умолчанию `14`)
- `ITINV_INVENTORY_QUEUE_MAX_TOTAL_MB` (по умолчанию `256`)
- `ITINV_AGENT_CA_BUNDLE` (опционально)
- `ITINV_SCAN_ENABLED` (`1|0`, по умолчанию `1`)
- `ITINV_REBOOT_REMINDER_ENABLED` (`1|0`, по умолчанию `1`)
- `ITINV_REBOOT_REMINDER_DAYS` (по умолчанию `7`)
- `ITINV_REBOOT_REMINDER_INTERVAL_HOURS` (по умолчанию `24`)
- `ITINV_REBOOT_REMINDER_TIMEOUT_SEC` (по умолчанию `120`)
- `ITINV_REBOOT_REMINDER_WORK_START_HOUR` (по умолчанию `9`)
- `ITINV_REBOOT_REMINDER_WORK_END_HOUR` (по умолчанию `18`, полуинтервал `start <= hour < end`)
- `ITINV_REBOOT_REMINDER_WEEKDAYS_ONLY` (`1|0`, по умолчанию `1` — только Пн–Пт)
- `ITINV_AGENT_ENV_FILE` (опционально, абсолютный путь к `.env` для агента)

Для строгого обновления Outlook каждые 5 минут используйте:

- `ITINV_AGENT_HEARTBEAT_SEC=300`
- `ITINV_AGENT_HEARTBEAT_JITTER_SEC=0`
- `ITINV_OUTLOOK_REFRESH_SEC=300`

### Источники переменных для агента

Агент загружает переменные в таком порядке приоритета:

1. уже заданные системные переменные окружения;
2. файл из `ITINV_AGENT_ENV_FILE` (если задан);
3. `.env` рядом с `ITInventAgent.exe` (режим установленного MSI);
4. локальные `.env` рядом со скриптом/в корне проекта (dev-запуск).

Для установленного агента (Scheduled Task от `SYSTEM`) рекомендуется хранить конфиг в:

- `C:\Program Files\IT-Invent\Agent\.env`

Параметры scan-контура (в этом же процессе):

- `SCAN_AGENT_SERVER_BASE`
- `SCAN_AGENT_API_KEY`
- `SCAN_AGENT_POLL_INTERVAL_SEC`
- `SCAN_AGENT_MAX_FILE_MB`
- `SCAN_AGENT_SCAN_ON_START`
- `SCAN_AGENT_WATCHDOG_ENABLED`
- `SCAN_AGENT_OUTBOX_MAX_ITEMS` (по умолчанию `5000`)
- `SCAN_AGENT_OUTBOX_MAX_AGE_DAYS` (по умолчанию `14`)
- `SCAN_AGENT_OUTBOX_MAX_TOTAL_MB` (по умолчанию `512`)

Server-side key-ring для ротации без простоя:

- `ITINV_AGENT_API_KEYS` (backend inventory, CSV)
- `SCAN_SERVER_API_KEYS` (scan server, CSV)

### Runbook ротации ключей

1. Добавить новый ключ в `ITINV_AGENT_API_KEYS` и `SCAN_SERVER_API_KEYS` на серверах.
2. Обновить `ITINV_AGENT_API_KEY` и `SCAN_AGENT_API_KEY` на агентах.
3. Проверить heartbeat/inventory/ingest без ошибок auth.
4. Удалить старый ключ из key-ring.
