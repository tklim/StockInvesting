@echo off
setlocal
cd /d "%~dp0"

rem Usage: run14x-fix.bat [year] [ticker] [population] [run_grid2 options]
rem Example: run14x-fix.bat 3 TSM 14 -Force
rem Defaults preserve the original launcher behavior.
set "year=%~1"
if not defined year set "year=3"
set "ticker=%~2"
if not defined ticker set "ticker=fix"
set "pop=%~3"
if not defined pop set "pop=14"

rem Arguments 4-9 are optional run_grid2.ps1 parameters, e.g. -Force or
rem -CompletedMaxAgeDays 1. Keep their quoting intact when forwarding them.
set "EXTRA_ARGS=%4 %5 %6 %7 %8 %9"

rem toupper
for /f %%A in ('powershell -NoProfile -Command "'%ticker%'.ToUpper()"') do set "ticker_upper=%%A"
set /a gen=pop/2
rem make logfile=tsm-run8.log
set "LOGFILE=runlogs\%ticker%-run%pop%.log"

echo year=%year%
echo ticker=%ticker%
echo ticker_upper=%ticker_upper%
echo pop=%pop%
echo gen=%gen%
echo LOGFILE=%LOGFILE%


powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0run_grid.ps1' -Funds %ticker_upper% -DataSuffix '-%year%Y' -TransitionPolicy grandfather -Population %pop% -Generations %gen% -GaSearchPreset grid -PriceColumn 'Adj Close' -LogFile '%LOGFILE%' %EXTRA_ARGS%"
set "EXIT_CODE=%ERRORLEVEL%"


echo.
echo run_grid finished with exit code %EXIT_CODE%.
echo (0 = all combos done/skipped, 1 = some failed, 2 = aborted on repeated failures)
endlocal & exit /b %EXIT_CODE%

rem Usage: run14x-fix.bat [year] [ticker] [population] [run_grid2 options]
