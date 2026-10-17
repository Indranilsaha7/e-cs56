@echo off
title AirMic - Windows Firewall Auto-Configurator
cd /d "%~dp0"

echo ========================================================
echo        AirMic - Windows Firewall Auto-Configurator
echo ========================================================
echo.
echo This script ensures Windows Firewall allows the AirMic PC
echo receiver to receive audio from your Android phone.
echo.

:: Check for Administrative privileges
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [REQUESTING ADMIN RIGHTS]
    powershell -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

echo [1/3] Adding inbound rule for UDP Audio Stream (Port 55555)...
netsh advfirewall firewall delete rule name="AirMic UDP Audio" >nul 2>&1
netsh advfirewall firewall add rule name="AirMic UDP Audio" dir=in action=allow protocol=UDP localport=55555 profile=any

echo [2/3] Adding inbound rule for TCP Audio Stream (Port 55555)...
netsh advfirewall firewall delete rule name="AirMic TCP Audio" >nul 2>&1
netsh advfirewall firewall add rule name="AirMic TCP Audio" dir=in action=allow protocol=TCP localport=55555 profile=any

echo [3/3] Adding inbound rule for UDP Auto-Discovery Beacon (Port 55554)...
netsh advfirewall firewall delete rule name="AirMic Discovery Beacon" >nul 2>&1
netsh advfirewall firewall add rule name="AirMic Discovery Beacon" dir=in action=allow protocol=UDP localport=55554 profile=any

echo.
echo ========================================================
echo   [SUCCESS] Windows Firewall successfully configured!
echo   AirMic can now receive audio from your phone freely.
echo ========================================================
echo.
pause
