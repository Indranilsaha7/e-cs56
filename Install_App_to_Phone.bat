@echo off
title AirMic - Install App to Phone via USB
cd /d "%~dp0"

echo ========================================================
echo        AirMic - Install Android App to Phone
echo ========================================================
echo.

set ADB_CMD=adb
if exist "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" (
    set "ADB_CMD=%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
)

echo Checking for connected Android phone...
"%ADB_CMD%" devices
echo.

if not exist "apk\AirMic.apk" (
    echo [ERROR] apk\AirMic.apk not found. Please compile the app first.
    pause
    exit /b 1
)

echo Installing apk\AirMic.apk onto connected phone...
"%ADB_CMD%" install -r "apk\AirMic.apk"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================================
    echo  [SUCCESS] AirMic successfully installed on your phone!
    echo ========================================================
) else (
    echo.
    echo [FAILED] Make sure your phone is connected via USB with:
    echo   1. USB Debugging enabled in Developer Options.
    echo   2. Authorize USB Debugging prompt allowed on your phone screen.
)

echo.
pause
