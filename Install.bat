@echo off
setlocal EnableDelayedExpansion
title TamozaLogger - Interactive Windows Installer
color 0B

echo ===============================================================================
echo                TAMOZA LOGGER - AUTOMATED WINDOWS INSTALLER
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
    ) else (
        echo [!] Please install PostgreSQL from https://www.postgresql.org/download/windows/
    )
)

echo [*] Ensuring PostgreSQL service is running...
powershell -Command "Get-Service -Name '*postgres*' | Where-Object { $_.Status -ne 'Running' } | Start-Service" >nul 2>&1
echo [OK] PostgreSQL service verified.
echo.

:: -----------------------------------------------------------------------------
:: Step 4: Interactive Configuration Wizard
:: -----------------------------------------------------------------------------
echo ===============================================================================
echo                INTERACTIVE CONFIGURATION WIZARD
echo ===============================================================================
echo Please enter your custom credentials below:
echo.

:prompt_token
set "BOT_TOKEN="
set /p "BOT_TOKEN=1. Enter your Discord Bot Token: "
if "%BOT_TOKEN%"=="" (
    echo [!] Bot Token cannot be empty.
    goto prompt_token
)

echo.
echo 2. PostgreSQL Database Settings (Press ENTER for defaults):
set "DB_HOST=localhost"
set /p "DB_HOST=   Database Host [default: localhost]: "

set "DB_PORT=5432"
set /p "DB_PORT=   Database Port [default: 5432]: "

set "DB_NAME=tamoza_logger"
set /p "DB_NAME=   Database Name [default: tamoza_logger]: "

set "DB_USER=postgres"
set /p "DB_USER=   Database Username [default: postgres]: "

:prompt_pass
set "DB_PASS="
set /p "DB_PASS=   Database Password for '%DB_USER%': "
if "%DB_PASS%"=="" (
    echo [!] Database password cannot be empty.
    goto prompt_pass
)

echo.
echo [*] Writing configuration to .env...
(
    echo # TamozaLogger — Environment Variables
    echo BOT_TOKEN=%BOT_TOKEN%
    echo DB_DSN=postgresql://%DB_USER%:%DB_PASS%@%DB_HOST%:%DB_PORT%/%DB_NAME%
    echo DEFAULT_PREFIX=!
    echo APPLICATION_ID=0
) > .env
echo [OK] .env file written successfully.
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
echo                           INSTALLATION COMPLETED!
echo ===============================================================================
echo.
echo  To start the bot anytime, simply double-click: Start.bat
echo.
echo ===============================================================================
pause
