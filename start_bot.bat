@echo off
REM Start IT-invent Telegram Bot
REM Запуск бота IT-invent

cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo ОШИБКА: Python не установлен или не добавлен в PATH
    pause
    exit /b 1
)

REM Check if bot module exists
if not exist "bot\main.py" (
    echo ERROR: bot\main.py not found
    echo ОШИБКА: bot\main.py не найден
    pause
    exit /b 1
)

REM Check if .env file exists
if not exist ".env" (
    echo WARNING: .env file not found. Please configure it first.
    echo ВНИМАНИЕ: Файл .env не найден. Пожалуйста, настройте его сначала.
    pause
    exit /b 1
)

echo Starting IT-invent Bot...
echo Запуск бота IT-invent...
echo.

REM Start the bot
python -m bot.main

REM If bot exits, pause to see any error messages
if %errorlevel% neq 0 (
    echo.
    echo Bot exited with error code: %errorlevel%
    echo Бот завершился с ошибкой: %errorlevel%
    pause
)
