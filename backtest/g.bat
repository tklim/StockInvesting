@echo off
setlocal EnableExtensions

rem Publish the current dashboard HTML and exactly the PNGs it references.
rem Run from any directory: backtest\g.bat
set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%sync_reports_to_github.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Report sync stopped. Review the error above; nothing was pushed after a failed validation.
)
exit /b %EXIT_CODE%
