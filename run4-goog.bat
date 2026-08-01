@echo off
cd /d "%~dp0"

REM AAPL on the derived 4-year slice (backtest\data\AAPL-4Y.csv), pop=4 gen=2.
REM Resumable: skips (fund, lookback, offset) combos already completed in
REM backtest_run_history.csv, so after a reboot just run this file again.
REM run_grid.ps1 sweeps lookback 1/2/3Y x offset 3/6/9/12M for each fund.
REM It makes one pass and stops (no infinite loop) and aborts on repeated
REM failures instead of spinning. See run4-4Y.log for progress.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0run_grid.ps1' -Funds GOOGL  -DataSuffix '-5Y' -Population 4 -Generations 2 -GaSearchPreset grid -PriceColumn 'Adj Close' -LogFile 'goog-run4.log' %*"

echo.
echo run_grid finished with exit code %ERRORLEVEL%.
echo (0 = all combos done/skipped, 1 = some failed, 2 = aborted on repeated failures)
