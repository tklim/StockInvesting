@echo off
cd /d "%~dp0"

REM First half of backtest\tickers.txt (AAPL, MSFT, GOOGL, AMZN, NVDA).
REM Resumable: skips (fund, lookback, offset) combos already completed in
REM backtest_run_history.csv, so after a reboot just run this file again.
REM run_grid.ps1 sweeps lookback 1/2/3Y x offset 3/6/9/12M for each fund.
REM It makes one pass and stops (no infinite loop) and aborts on repeated
REM failures instead of spinning. See run10a.log for progress.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0run_grid.ps1' -Funds V -DataSuffix '-4Y' -Population 8 -Generations 4 -GaSearchPreset grid -PriceColumn 'Adj Close' -LogFile 'v-run8-4Y.log'"

echo.
echo run_grid finished with exit code %ERRORLEVEL%.
echo (0 = all combos done/skipped, 1 = some failed, 2 = aborted on repeated failures)
