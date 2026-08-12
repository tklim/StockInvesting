rem This is for updating to github and publish to production
@echo off
setlocal EnableExtensions

rem Refresh the historical buy-and-hold dashboard, then publish all report HTML
rem and exactly the external PNGs referenced by those reports. Historical
rem buy-and-hold charts are inline SVG in its HTML, so no PNGs are generated.
rem Run from any directory: backtest\g.bat
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%"
python dashboard_by_historical_buyhold.py
set "BUILD_EXIT_CODE=%ERRORLEVEL%"
popd

if not "%BUILD_EXIT_CODE%"=="0" (
    echo.
    echo Historical buy-and-hold dashboard refresh failed. Nothing was synchronized.
    exit /b %BUILD_EXIT_CODE%
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%sync_reports_to_github.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Report sync stopped. Review the error above; nothing was pushed after a failed validation.
)
exit /b %EXIT_CODE%
