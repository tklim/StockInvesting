@echo off
cd /d "%~dp0"

REM First half of backtest\tickers.txt (AAPL, MSFT, GOOGL, AMZN, NVDA).
REM Resumable: skips (fund, lookback, offset) combos already completed in
REM backtest_run_history.csv, so after a reboot just run this file again.
REM run_grid.ps1 sweeps lookback 1/2/3Y x offset 3/6/9/12M for each fund.
REM It makes one pass and stops (no infinite loop) and aborts on repeated
REM failures instead of spinning. See run10a.log for progress.
REM Any additional PowerShell parameters passed to this .bat are forwarded, e.g.
REM   run6.bat -Force

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0run_grid.ps1' -Funds MSFT  -DataSuffix '-5Y' -Population 6 -Generations 3 -GaSearchPreset grid -PriceColumn 'Adj Close' -LogFile 'msft-run6.log' %*"

echo.
echo run_grid finished with exit code %ERRORLEVEL%.
echo (0 = all combos done/skipped, 1 = some failed, 2 = aborted on repeated failures)
