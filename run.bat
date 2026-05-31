@echo off
REM Thin launcher for run.ps1.
REM Using -ExecutionPolicy Bypass lets the PowerShell script run without
REM changing system settings and without needing to "unblock" downloaded files.
title WhisperType
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"
if errorlevel 1 (
    echo.
    echo WhisperType exited with an error. See the messages above.
    pause
)
