@echo off
setlocal

rem Always work from the folder containing this script.
cd /d "%~dp0"

echo Current directory: %CD%
dir runlogs
echo.

for /f "usebackq tokens=* delims=" %%T in ("backtest\tickers.txt") do (
    set "ticker=%%T"
    call :process "%%T"
)

exit /b

:process
set "ticker=%~1"

rem Skip blank lines
if "%ticker%"=="" exit /b

rem Skip comment lines starting with #
if "%ticker:~0,1%"=="#" exit /b

rem Skip this ticker when its run4 log was modified today.
forfiles /p "%CD%\runlogs" /m "%ticker%-run4.log" /d 0 /c "cmd /c exit 0" >nul 2>&1
if not errorlevel 1 (
    echo Skipping %ticker% - runlogs\%ticker%-run4.log already exists from today.
    exit /b
)

echo Running %ticker%...
echo "Running %ticker%..." >> "runlogs\\%ticker%-run4.log"
call run1.bat 5 %ticker% 4

exit /b
