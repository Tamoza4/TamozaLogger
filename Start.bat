@echo off
title TamozaLogger
color 0A
cd /d "%~dp0"

echo ===============================================================================
echo                           STARTING TAMOZA LOGGER
echo ===============================================================================
echo.

if exist "venv\Scripts\python.exe" (
    call venv\Scripts\python.exe bot.py
) else (
    echo [*] Checking global Python installation...
    python bot.py
)

if %errorlevel% neq 0 (
    echo.
    echo [!] Bot exited with error code %errorlevel%.
    pause
)
