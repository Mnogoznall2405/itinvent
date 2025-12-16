@echo off
title View Bot Logs
echo ========================================
echo   IT Inventory Bot Logs
echo ========================================
echo.

cd /d "%~dp0"

if not exist "bot.log" (
    echo No log file found. Start the bot first to generate logs.
    echo.
    pause
    exit /b 1
)

echo Displaying last 50 lines of bot.log:
echo ========================================
powershell.exe Get-Content bot.log -Tail 50
echo ========================================
echo.
echo Log file location: %cd%\bot.log
echo.
pause