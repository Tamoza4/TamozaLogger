@echo off
setlocal EnableDelayedExpansion
title TamozaLogger - One-Click Installer
color 0B

echo ===============================================================================
echo                TAMOZA LOGGER - AUTOMATED WINDOWS INSTALLER
echo ===============================================================================
echo.

:: -----------------------------------------------------------------------------
:: Step 1: Check Administrator Privileges
:: -----------------------------------------------------------------------------
echo [1/6] Checking Administrator permissions...
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
echo [2/6] Checking Python installation...
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
    
    :: Refresh Environment PATH
    set "PATH=%ProgramFiles%\Python312;%ProgramFiles%\Python312\Scripts;%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts;%PATH%"
    set "PY_CMD=python"
    echo [OK] Python installation completed.
)
echo.

:: -----------------------------------------------------------------------------
:: Step 3: Check & Install PostgreSQL
:: -----------------------------------------------------------------------------
echo [3/6] Checking PostgreSQL database server...
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

:: Start PostgreSQL service if stopped
echo [*] Ensuring PostgreSQL service is running...
powershell -Command "Get-Service -Name '*postgres*' | Where-Object { $_.Status -ne 'Running' } | Start-Service" >nul 2>&1
echo [OK] PostgreSQL service verified.
echo.

:: -----------------------------------------------------------------------------
:: Step 4: Setup Python Virtual Environment (venv) & Dependencies
:: -----------------------------------------------------------------------------
echo [4/6] Setting up Python virtual environment...
if not exist "venv" (
    echo [*] Creating virtual environment 'venv'...
    %PY_CMD% -m venv venv
)

echo [*] Upgrading pip...
call venv\Scripts\python.exe -m pip install --upgrade pip --quiet

echo [*] Installing requirements from requirements.txt...
call venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
echo [OK] All Python dependencies installed successfully.
echo.

:: -----------------------------------------------------------------------------
:: Step 5: Setup .env Configuration
:: -----------------------------------------------------------------------------
echo [5/6] Checking configuration (.env)...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [!] Created .env file from .env.example.
    ) else (
        (
            echo BOT_TOKEN=YOUR_BOT_TOKEN_HERE
            echo DB_DSN=postgresql://postgres:postgres@localhost:5432/tamoza_logger
            echo DEFAULT_PREFIX=!
            echo APPLICATION_ID=0
        ) > .env
        echo [!] Created default .env file.
    )
    echo [*] Please edit .env with your Discord BOT_TOKEN and database password.
) else (
    echo [OK] .env file exists.
)
echo.

:: -----------------------------------------------------------------------------
:: Step 6: Initialize PostgreSQL Database & Apply Schema
:: -----------------------------------------------------------------------------
echo [6/6] Initializing PostgreSQL database & schema...
call venv\Scripts\python.exe database\setup_db.py
if %errorlevel% neq 0 (
    echo [!] Note: If database setup failed, please check your DB_DSN credentials in .env.
)
echo.

:: -----------------------------------------------------------------------------
:: Create Start.bat helper
:: -----------------------------------------------------------------------------
(
    echo @echo off
    echo title TamozaLogger
    echo color 0A
    echo cd /d "%%~dp0"
    echo echo ===============================================================================
    echo echo                           STARTING TAMOZA LOGGER
    echo echo ===============================================================================
    echo echo.
    echo if not exist "venv\Scripts\python.exe" (
    echo     echo [ERROR] Virtual environment not found. Please run Install.bat first.
    echo     pause
    echo     exit /b 1
    echo ^)
    echo call venv\Scripts\python.exe bot.py
    echo if %%errorlevel%% neq 0 (
    echo     echo.
    echo     echo [!] Bot exited with error code %%errorlevel%%.
    echo     pause
    echo ^)
) > Start.bat

echo ===============================================================================
echo                           INSTALLATION COMPLETED!
echo ===============================================================================
echo.
echo  1. Make sure your BOT_TOKEN and DB_DSN are configured in: .env
echo  2. To start the bot anytime, simply double-click: Start.bat
echo.
echo ===============================================================================
pause
