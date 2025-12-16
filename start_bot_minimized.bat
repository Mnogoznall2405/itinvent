@echo off
REM Start IT-invent Bot minimized to system tray
REM Запуск бота IT-invent в свернутом виде

cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    exit /b 1
)

REM Check if bot module exists
if not exist "bot\main.py" (
    echo ERROR: bot\main.py not found in current directory
    exit /b 1
)

REM Start the bot minimized
if exist "%temp%\start_bot_temp.vbs" del "%temp%\start_bot_temp.vbs"
echo CreateObject("Wscript.Shell").Run "cmd /c cd /d %CD% && python -m bot.main", 0, False > "%temp%\start_bot_temp.vbs"
start /min wscript.exe "%temp%\start_bot_temp.vbs"

echo Bot started in background
echo Бот запущен в фоновом режиме
echo Check bot.log for output
echo Проверьте bot.log для вывода
timeout /t 2 /nobreak >nul
