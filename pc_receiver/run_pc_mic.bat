@echo off
title AirMic PC Receiver
cd /d "%~dp0"

echo ========================================================
echo               AirMic - PC Receiver Launcher
echo ========================================================
echo.

set "PYTHON_CMD="

:: 1. Check system path python
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=python"
)

:: 2. Check py launcher
if "%PYTHON_CMD%"=="" (
    where py >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set "PYTHON_CMD=py"
    )
)

:: 3. Check AppData Python paths
if "%PYTHON_CMD%"=="" (
    if exist "%LOCALAPPDATA%\Python\bin\python.exe" (
        set "PYTHON_CMD=%LOCALAPPDATA%\Python\bin\python.exe"
    )
)

if "%PYTHON_CMD%"=="" (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
        if exist "%%D\python.exe" set "PYTHON_CMD=%%D\python.exe"
    )
)

:: 4. If still not found, alert user
if "%PYTHON_CMD%"=="" (
    echo [ERROR] Python was not found on this computer.
    echo.
    echo Would you like to install Python automatically via winget?
    choice /M "Install Python now"
    if errorlevel 2 goto :manual_install
    winget install Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
    echo.
    echo Python installed. Please restart this launcher.
    pause
    exit /b 1

    :manual_install
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [1/2] Verifying Python dependencies...
"%PYTHON_CMD%" -m pip install -r requirements.txt --quiet

echo [2/2] Launching AirMic PC Receiver...
echo.
"%PYTHON_CMD%" app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo AirMic exited with code %ERRORLEVEL%.
    pause
)
