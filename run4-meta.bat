@echo off
cd /d "%~dp0"

REM META on current local history (backtest\data\META.csv), pop=4 gen=2.
REM Resumable for 24 hours: skips only recently completed (fund, lookback,
REM offset) combos, so a cancelled run continues from today's successes while
REM old history is re-run. Override with -CompletedMaxAgeHours N or -Force.
REM run_grid.ps1 sweeps lookback 1/2/3Y x offset 3/6/9/12M for each fund.
REM It makes one pass and stops (no infinite loop) and aborts on repeated
REM failures instead of spinning. See meta-run4.log for progress.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0run_grid.ps1' -Funds META  -DataSuffix '-5Y' -Population 4 -Generations 2 -GaSearchPreset grid -PriceColumn 'Adj Close' -LogFile 'meta-run4.log'  %*"
rem powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0run_grid.ps1' -Funds META  -Population 4 -Generations 2 -GaSearchPreset grid -PriceColumn 'Adj Close' -LogFile 'meta-run4.log'  %*"

echo.
echo run_grid finished with exit code %ERRORLEVEL%.
echo (0 = all combos done/skipped, 1 = some failed, 2 = aborted on repeated failures)
