@echo off
setlocal
cd /d "%~dp0"

set "year=3"
set "ticker=fix"
set "pop=12"

rem toupper
for /f %%A in ('powershell -NoProfile -Command "'%ticker%'.ToUpper()"') do set "ticker_upper=%%A"
set /a gen=pop/2
rem make logfile=tsm-run8.log
set "LOGFILE=%ticker%-run%pop%.log"

echo ticker=%ticker%
echo ticker_upper=%ticker_upper%
echo pop=%pop%
echo gen=%gen%
echo LOGFILE=%LOGFILE%


powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0run_grid.ps1' -Funds %ticker_upper%   -DataSuffix '-%year%Y' -TransitionPolicy grandfather -Population %pop% -Generations %gen% -GaSearchPreset grid -PriceColumn 'Adj Close' -LogFile '%LOGFILE%' %*"


rem powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0run_grid.ps1' -Funds FIX -DataSuffix '-3Y' -TransitionPolicy grandfather -Population 6 -Generations 3 -GaSearchPreset grid -PriceColumn 'Adj Close' -LogFile '%LOGFILE%' %*"

echo.
echo run_grid finished with exit code %ERRORLEVEL%.
echo (0 = all combos done/skipped, 1 = some failed, 2 = aborted on repeated failures)
endlocal
