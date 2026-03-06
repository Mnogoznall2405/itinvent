# Проект IT-Invent (Система инвентаризации и визуализации ИТ-инфраструктуры)

## 📌 Описание проекта
**IT-Invent** — это комплексное Fullstack веб-приложение для системного администрирования. Оно предназначено для инвентаризации оборудования (маршрутизаторы, коммутаторы, ПК), визуализации сетевых портов и розеток на поэтажных планах (интерактивные SVG-карты), управления доступом пользователей (на базе LDAP/Active Directory) и автоматического сбора аппаратной информации с конечных ПК пользователей.

---

## 🏗 Архитектура баз данных (Database Architecture)
Одна из главных особенностей проекта — гибридная система работы с данными:
1. **Внешние базы SQL Server (IT-Invent):**
   - Бэкенд динамически подключается к продакшен-базам данных MS SQL Server (через драйвер `pyodbc` / `SQL Server`).
   - Поддерживается **динамическое переключение** (Dynamic Database Switching) между региональными базами: `ITINVENT` (Чтение/Запись), `MSK-ITINVENT` (Москва, Чтение/Запись), `OBJ-ITINVENT` (Объекты, Чтение/Запись), `SPB-ITINVENT` (Питер, Чтение/Запись).
   - Подключение формируется в `backend/database/connection.py`, а эндпоинты для переключения живут в `backend/api/v1/database.py`. У каждого пользователя хранится выбор его активной БД в сессии.
2. **Локальная база данных (JSON/Abstract Local Storage):**
   - Расположена в папках `json_db/` и `data/` на стороне бэкенда.
   - Используется для хранения метаинформации, которая не лезет во внешний MS SQL: 
     - Пользовательские сессии, кэши JWT (`session_service.py`).
     - Сохраненные координаты SVG маркеров розеток.
     - Инвентаризация ПК от Python Агентов (`agent_inventory_cache.json`).
     - Настройки интерфейса пользователей (темы, UI-опции).
     - Локальные логи Картриджей, Трансферов и Работ (`cartridges.py`, `transfers.py`, `works.py`).

---

## 🖥 Frontend (Клиентская часть, Веб-интерфейс)
- **Путь:** `c:\Project\Image_scan\WEB-itinvent\frontend\`
- **Стек:** React 18, Vite, Material-UI (MUI), React Router DOM.
- **Особенности рендеринга:**
  - `react-window` и `react-virtualized-auto-sizer` для виртуализации огромных таблиц (оборудование, порты, розетки, аудит). 
  - Разделение функционала на изолированные вкладки: `EquipmentTab`, `SocketsTab`, `AuditTab`.
- **Основные страницы (Pages):**
  - `Networks.jsx` — Интерактивная карта (SVG) с умными `PinMarker.jsx` (Drag-n-Drop, кластеризация серый/синий цвет), просмотр портов коммутаторов по зданиям и этажам, аудит изменений.
  - `Computers.jsx` — Сводка ПК, собранная Агентами. Динамические плашки: здоровье дисков (NVMe/SATA бейджи), занятое место на логических дисках (LinearProgress), серийники материнских плат.
  - `Settings.jsx` — Настройки (рефакторинг на React.memo, изоляция тяжелых форм вроде создания LDAP пользователей).
  - `Dashboard.jsx`, `Database.jsx`, `Statistics.jsx`, `Search.jsx`, `Transfer.jsx`, `Work.jsx`.

---

## ⚙️ Backend (Серверная часть)
- **Путь:** `c:\Project\Image_scan\WEB-itinvent\backend\`
- **Стек:** Python 3.12+, FastAPI, Uvicorn, pyodbc (MS SQL), Pydantic.
- **Структура маршрутов (API routers):**
  - Всё API документировано (Swagger) и лежит в `api/v1/`.
  - `auth.py` — авторизация, выдача JWT, интеграция с `ad_sync_service.py` (LDAP).
  - `database.py` — эндпоинты смены рабочих MS SQL баз.
  - `equipment.py` / `networks.py` — выполнение SQL запросов к главной БД оборудования и портов (`queries.py`).
  - `inventory.py` — прием шифрованной (по API-KEY) телеметрии от Агентов компьютеров.
  - `json_operations.py` — работа с локальными файлами json/кэшем.

---

## 🤖 IT-Invent Agent (Автономный сборщик для ПК)
- **Путь:** `c:\Project\Image_scan\` (скрипт `agent.py`, `setup.py`).
- **Язык & Инструменты:** Python 3.12, сборщик `cx_Freeze`.
- **Принцип работы:** 
  - Системный агент для OS Windows. Ставится через `.msi` (сборка `bdist_msi`) и запускается Планировщиком (Task Scheduler) от системного аккаунта `SYSTEM`.
  - Скомпилирован с `base="Win32GUI"` во избежание ошибки создания консольного окна при запуске фоном.
  - **Сбор аппаратной части:** WMI парсинг (RAM, CPU, `Win32_BIOS` seial number).
  - **Сбор Дисков (PowerShell & WMI):** `Get-PhysicalDisk` используется для извлечения здоровья (Healthy), износа (Wear Out %) и температуры (SSD/NVMe). Парсинг PowerShell команд использует `errors='ignore'` для защиты от падений при декодировании кириллицы (cp866/1251). Логические тома (`Win32_LogicalDisk`) собирают размер и свободное место разделов.

---

## 📂 Структура директорий проекта
```text
c:\Project\Image_scan\
├── WEB-itinvent/
│   ├── backend/
│   │   ├── api/v1/         # Маршрутизаторы FastAPI (auth, equipment, inventory, networks)
│   │   ├── database/       # Подключение к MS SQL Server (connection.py)
│   │   ├── json_db/        # Локальное NoSQL хранилище (кэш, координаты маркеров, сессии)
│   │   ├── models/         # Pydantic модели данных для валидации (equipment.py, auth.py)
│   │   ├── services/       # Бизнес-логика (ad_sync_service.py, excel_export_service.py)
│   │   ├── .env            # Файл переменных окружения
│   │   ├── config.py       # Парсер конфигов (хост БД, JWT секреты)
│   │   └── main.py         # Точка входа сервера FastAPI
│   └── frontend/
│       ├── public/         # Статические файлы, Favicon, SVG Планы этажей
│       ├── src/
│       │   ├── api/        # Axios клиенты для вызова FastAPI бэкенда
│       │   ├── components/ # Переиспользуемые UI-компоненты (MainLayout, DeviceDialog, PinMarker)
│       │   ├── pages/      # Основные страницы приложения (Networks, Computers, Settings, Database)
│       │   ├── App.jsx     # Роутинг страниц (React Router DOM)
│       │   └── main.jsx    # Точка входа React
│       ├── index.html      # Шаблон SPA приложения
│       └── package.json    # Зависимости NPM и скрипты сборки
├── agent.py                # Код инвентаризационного агента ПК
├── setup.py                # Скрипт сборки cx_Freeze (msi)
└── LLM_PROJECT_CONTEXT.md  # Этот файл контекста проекта
```

## 🚀 Деплой и команды для запуска (Deployment & Scripts)
- **Frontend (Development & Production):**
  - Разработка: `npm run dev` (Поднимает Vite сервер на `localhost:5173`).
  - Сборка на прод: `npm run build` (Генерирует статичные транслированные ассеты JS/CSS в папку `dist`).
- **Backend (Development & Production):**
  - Запуск сервера: `python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload`
- **Создание MSI Агента (Windows Installer):**
  - `python setup.py bdist_msi` (Создает установщик `IT-Invent Agent-win64.msi` в папке `dist/`).

## 🗺 Потоки данных (Data Flows & Security)
1. **Интерактивная карта (Drag & Drop розеток):** 
   - На странице `Networks.jsx` маркеры (`PinMarker.jsx`) имеют координаты X, Y, привязанные к плану этажа. 
   - При перетаскивании маркера мышкой отправляется быстрый `PUT` запрос (эндпоинт `/api/v1/networks/sockets/{id}/coordinates`), который мгновенно записывает новые координаты маркера в локальную базу `json_db` на бэкенде. Мы не записываем координаты в MS SQL, чтобы уберечь главную базу от тысяч мелких I/O транзакций.
2. **Безопасность и Авторизация (JWT, AD):**
   - Пользователь логинится на вкладке `/login`. Бэкенд (`auth.py`) сверяет пользователя с локальной БД админов или запрашивает внешний Active Directory (LDAP через `ad_sync_service.py`).
   - При успехе возвращается `Access Token` (JWT), который сохраняется на клиенте (Local Storage) и прикрепляется к каждому запросу как `Bearer <token>`.
   - Выбор активной БД (Питер, Объекты, Тюмень) надежно фиксируется в сессии пользователя (`session_service.py`). Если пользователь закроет браузер и вернётся, приложение отдаст данные именно из той региональной БД, в которой он работал до этого.

---
## 💡 Технические соглашения для LLM
1. **Frontend:** Использовать Functional Components, React Hooks. Избегать монолитов. Компоненты UI брать из `@mui/material`.
2. **Backend:** Модель данных строгая (`BaseModel` из Pydantic), функции `async def`. При работе с внешними базами ВСЕГДА учитывать, что `db_id` может меняться в рантайме пользователя (`connection.py`).
3. **OS-Интеграция:** В Python-Агенте защищаться от пустых параметров `None` в WMI/PowerShell-ответах ОС.
