# Развёртывание IT-Invent Agent через GPO

Агент вынесен в папку `agent/`.

- Основная сборка: `python agent/setup.py bdist_msi`
- Совместимый старый путь: `python setup.py bdist_msi`

## 1. Подготовка MSI

1. Соберите MSI.
2. Скопируйте файл в сетевую шару по UNC, например:
   - `\\FILESRV\packages\IT-Invent Agent-1.1.0-win64.msi`
3. Дайте `Domain Computers` права чтения на шару и NTFS.

## 2. Установка MSI через GPO

`Computer Configuration -> Policies -> Software Settings -> Software installation`

1. `New -> Package...`
2. Укажите UNC путь к MSI.
3. Режим: `Assigned`.

Рекомендуется включить:

`Computer Configuration -> Policies -> Administrative Templates -> System -> Logon -> Always wait for the network at computer startup and logon = Enabled`

## 3. Автозапуск агента (SYSTEM)

Рекомендуемый путь: Group Policy Preferences Scheduled Task.

`Computer Configuration -> Preferences -> Control Panel Settings -> Scheduled Tasks`

Параметры задачи:

- Name: `IT-Invent Agent`
- User: `NT AUTHORITY\SYSTEM`
- Run with highest privileges: `On`
- Trigger: `At startup`, repeat every `1 hour` indefinitely
- Program: `C:\Program Files\IT-Invent\Agent\ITInventAgent.exe`
- Start in: `C:\Program Files\IT-Invent\Agent`

## 4. HTTPS и конфиг

По умолчанию агент настроен на HTTPS endpoint. При необходимости задайте через GPO Environment Variables:

- `ITINV_AGENT_SERVER_URL`
- `ITINV_AGENT_API_KEY`
- `ITINV_AGENT_INTERVAL_SEC`
- `ITINV_AGENT_HEARTBEAT_SEC`
- `ITINV_AGENT_HEARTBEAT_JITTER_SEC`
- `ITINV_AGENT_CA_BUNDLE` (если нужен кастомный trust bundle)

## 5. Проверка на клиенте

```powershell
Test-Path "C:\Program Files\IT-Invent\Agent\ITInventAgent.exe"
Get-ScheduledTask -TaskName "IT-Invent Agent"
Get-Content "C:\ProgramData\IT-Invent\Logs\itinvent_agent.log" -Tail 80
```

Проверка в UI:

- `/computers` показывает статус `online/stale/offline`
- корректный `Last seen` и `Возраст`
