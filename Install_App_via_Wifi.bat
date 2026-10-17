@echo off
title AirMic - Install APK Over Wi-Fi
cd /d "%~dp0"

echo ========================================================
echo        AirMic - Install APK Over Local Wi-Fi
echo ========================================================
echo.

set "PYTHON_CMD="
where python >nul 2>&1 && set "PYTHON_CMD=python"
if "%PYTHON_CMD%"=="" where py >nul 2>&1 && set "PYTHON_CMD=py"
if "%PYTHON_CMD%"=="" if exist "%LOCALAPPDATA%\Python\bin\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Python\bin\python.exe"

if not exist "AirMic.apk" (
    if exist "apk\AirMic.apk" (
        copy /y "apk\AirMic.apk" "AirMic.apk" >nul
    ) else (
        echo [ERROR] AirMic.apk not found.
        pause
        exit /b 1
    )
)

echo Starting local Wi-Fi Web Server on Port 8080...
echo.

:: Detect primary LAN IP using Python
for /f "delims=" %%I in ('"%PYTHON_CMD%" -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0]); s.close()" 2^>nul') do set "MY_IP=%%I"
if "%MY_IP%"=="" set "MY_IP=192.168.0.103"

echo ========================================================
echo  📲 OPEN THIS LINK IN YOUR PHONE'S BROWSER (CHROME):
echo.
echo     http://%MY_IP%:8080/AirMic.apk
echo.
echo  (Make sure your phone is connected to the same Wi-Fi!)
echo ========================================================
echo.
echo Press Ctrl+C in this window when download is finished.
echo.

"%PYTHON_CMD%" -m http.server 8080
pause
