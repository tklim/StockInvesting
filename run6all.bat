@echo off
setlocal

rem Always work from the folder containing this script.
cd /d "%~dp0"

echo Current directory: %CD%
REM dir runlogs
echo.

rem Input format: TICKER [POPULATION]. Population defaults to 6. #-pop6
for /f "usebackq tokens=1,2" %%A in ("backtest\tickers.txt") do (
    call :process "%%A" "%%B"
)

exit /b

:process
set "ticker=%~1"
set "pop=%~2"

rem Skip blank lines
if "%ticker%"=="" exit /b

rem Default the population when the input line has no second parameter.
if not defined pop set "pop=6"

rem Skip comment lines starting with #
if "%ticker:~0,1%"=="#" exit /b

rem Skip this ticker when its run6 log was modified today.
forfiles /p "%CD%\runlogs" /m "%ticker%-run6.log" /d 0 /c "cmd /c exit 0" >nul 2>&1
if not errorlevel 1 (
    echo Skipping %ticker% - runlogs\%ticker%-run6.log already exists from today.
    exit /b
)

echo Running %ticker% with population %pop%...
echo "Running %ticker%..." >> "runlogs\\%ticker%-run6.log"
call run1.bat 3 "%ticker%" "%pop%"

exit /b

REM /d 0    today or later, /d 1    tomorrow or later, /d 2    two days from now or later, /d -1   yesterday or earlier, /d -7   seven days ago or earlier