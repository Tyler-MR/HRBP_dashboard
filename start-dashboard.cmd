@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start-dashboard.ps1" -OpenBrowser
if errorlevel 1 (
    echo.
    echo Dashboard startup failed. Check the logs in runtime-logs.
    pause
)
endlocal
