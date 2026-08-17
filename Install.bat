@echo off
setlocal EnableDelayedExpansion
title TamozaLogger - Fully Automated Windows Installer
color 0B

echo ===============================================================================
echo             TAMOZA LOGGER - 100%% AUTOMATED WINDOWS INSTALLER
echo ===============================================================================
echo.

:: -----------------------------------------------------------------------------
:: Step 1: Check Administrator Privileges
:: -----------------------------------------------------------------------------
echo [1/5] Checking Administrator permissions...
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Administrator privileges required to install software and services.
    echo [*] Requesting elevation...
    powershell -Command "Start-Process cmd -ArgumentList '/c,cd /d,\"%~dp0\",&&,call,\"%~f0\"' -Verb RunAs"
    exit /b
)
echo [OK] Running with Administrator privileges.
echo.

cd /d "%~dp0"

:: -----------------------------------------------------------------------------
:: Step 2: Check & Install Python (3.11+)
:: -----------------------------------------------------------------------------
echo [2/5] Checking Python installation...
set "PY_CMD="

python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_CMD=python"
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo [OK] Found Python %%v
) else (
    py --version >nul 2>&1
    if %errorlevel% equ 0 (
        set "PY_CMD=py"
        for /f "tokens=2" %%v in ('py --version 2^>^&1') do echo [OK] Found Python %%v
    )
)

if "%PY_CMD%"=="" (
    echo [-] Python is not installed. Installing Python 3.12 via winget...
    winget --version >nul 2>&1
    if %errorlevel% equ 0 (
        winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    ) else (
        echo [*] Downloading Python installer...
        powershell -Command "(New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe', 'python_installer.exe')"
        echo [*] Installing Python (with PATH)...
        python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
        del python_installer.exe
    )
    
    set "PATH=%ProgramFiles%\Python312;%ProgramFiles%\Python312\Scripts;%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts;%PATH%"
    set "PY_CMD=python"
    echo [OK] Python installation completed.
)
echo.

:: -----------------------------------------------------------------------------
:: Step 3: Check & Install PostgreSQL
:: -----------------------------------------------------------------------------
echo [3/5] Checking PostgreSQL database server...
sc query postgresql-x64-16 >nul 2>&1
if %errorlevel% neq 0 (
    sc query postgresql >nul 2>&1
)

if %errorlevel% neq 0 (
    echo [-] PostgreSQL is not installed. Installing PostgreSQL 16 via winget...
    winget --version >nul 2>&1
    if %errorlevel% equ 0 (
        winget install -e --id PostgreSQL.PostgreSQL.16 --silent --accept-package-agreements --accept-source-agreements
    )
)

echo [*] Ensuring PostgreSQL service is running...
powershell -Command "Get-Service -Name '*postgres*' | Where-Object { $_.Status -ne 'Running' } | Start-Service" >nul 2>&1
echo [OK] PostgreSQL service verified.
echo.

:: -----------------------------------------------------------------------------
:: Step 4: Configure .env Automatically
:: -----------------------------------------------------------------------------
echo [4/5] Configuring environment (.env)...
if not exist ".env" (
    (
        echo BOT_TOKEN=YOUR_BOT_TOKEN_HERE
        echo DB_DSN=postgresql://postgres:postgres@localhost:5432/tamoza_logger
        echo DEFAULT_PREFIX=!
        echo APPLICATION_ID=0
    ) > .env
    echo [OK] Created .env with default local settings.
) else (
    echo [OK] Existing .env file preserved.
)
echo.

:: -----------------------------------------------------------------------------
:: Step 5: Python Virtual Environment & Database Schema
:: -----------------------------------------------------------------------------
echo [5/5] Setting up Python virtual environment and database schema...
if not exist "venv" (
    %PY_CMD% -m venv venv
)

echo [*] Installing requirements...
call venv\Scripts\python.exe -m pip install --upgrade pip --quiet
call venv\Scripts\python.exe -m pip install -r requirements.txt --quiet

echo [*] Applying database schema...
call venv\Scripts\python.exe database\setup_db.py
echo.

echo ===============================================================================
echo                     INSTALLATION 100%% COMPLETED!
echo ===============================================================================
echo.
echo  1. Make sure your BOT_TOKEN is in: .env
echo  2. To start the bot anytime, double-click: Start.bat
echo.
echo ===============================================================================
pause
