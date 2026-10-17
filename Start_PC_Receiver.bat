@echo off
title AirMic PC Receiver
cd /d "%~dp0"

if exist "AirMic_Receiver.exe" (
    echo Starting AirMic Native Receiver (Ultra-Lightweight, 0ms latency)...
    AirMic_Receiver.exe
) else (
    echo AirMic_Receiver.exe not found, falling back to Python receiver...
    cd pc_receiver
    call run_pc_mic.bat
)
