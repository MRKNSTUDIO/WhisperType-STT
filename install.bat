@echo off
REM Thin launcher for install.ps1.
REM Using -ExecutionPolicy Bypass lets the PowerShell script run without
REM changing system settings and without needing to "unblock" downloaded files.
title WhisperType Installer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
    echo.
    echo The installer exited with an error. See the messages above.
    pause
)
