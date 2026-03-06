# Публикация WEB-itinvent через IIS (React + FastAPI)

## 1. Что ставим на сервер
- IIS
- `URL Rewrite` (IIS extension)
- `Application Request Routing (ARR)` и включенный Proxy
- Python 3.12+
- Node.js 20+ (нужен только на этапе сборки frontend)
- `NSSM` (для запуска backend как Windows service)

## 2. Какие файлы нужны
Рекомендуемый вариант: копировать **весь корень проекта**.

Минимально для запуска web:
- `WEB-itinvent/frontend/dist/*` (после сборки)
- `WEB-itinvent/backend/*`
- `WEB-itinvent/backend/.env`
- `WEB-itinvent/backend/.env.example` (шаблон)
- `local_store.py`
- `data/local_store.db`
- `.env` (корневой, если используются LLM/email функции, читающие root env)
- `templates/`, `transfer_acts/` (если используются акты/документы)

## 3. Backend: установка зависимостей
```powershell
cd C:\Project\Image_scan
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r WEB-itinvent\backend\requirements.txt
```

## 4. Frontend: сборка и публикация в IIS-папку
Перед сборкой задайте базовый путь фронта:
- если сайт в корне домена: `VITE_BASE_PATH=/`
- если сайт в виртуальной папке (например `/itinvent`): `VITE_BASE_PATH=/itinvent/`

Пример (`WEB-itinvent/frontend/.env.production`):
```env
VITE_BASE_PATH=/itinvent/
```

Используйте скрипт:
```powershell
.\scripts\iis\publish_frontend_iis.ps1 `
  -ProjectRoot "C:\Project\Image_scan" `
  -IisSitePath "C:\inetpub\wwwroot\itinvent"
```

`web.config` для SPA + `/api` proxy уже добавлен в:
- `WEB-itinvent/frontend/public/web.config`

Он автоматически попадает в `dist` при `npm run build`.

## 5. Backend как Windows service
Используйте скрипт:
```powershell
.\scripts\iis\install_backend_service.ps1 `
  -ServiceName "itinvent-backend" `
  -ProjectRoot "C:\Project\Image_scan" `
  -BackendPort 8001
```

## 6. Настройка IIS сайта
- Physical path сайта: `C:\inetpub\wwwroot\itinvent`
- Hostname/Binding: ваш домен
- HTTPS сертификат: привязать к сайту

Важно: в ARR должен быть включен Proxy (`Server Proxy Settings` -> `Enable proxy`).

## 7. Проверка после публикации
- `https://your-domain/` открывает frontend
- (если виртуальная папка) `https://your-domain/itinvent/` открывает frontend
- `https://your-domain/api/v1/auth/me` отвечает backend (401 без токена — это нормально)
- Вход в веб-интерфейс работает, API уходит через `/api/*`

## 8. Частые ошибки
- `502` на `/api/*`: не запущена служба `itinvent-backend` или ARR Proxy выключен
- `404` на роуты React: не попал `web.config` в `dist`
- пустая страница с заголовком сайта: чаще всего неверный `VITE_BASE_PATH` или приложение развернуто в виртуальной папке без `basename`
- Ошибки БД/SMTP/LLM: проверьте `WEB-itinvent/backend/.env` и корневой `.env`
