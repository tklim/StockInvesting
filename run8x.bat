@echo off
cd /d "%~dp0"

REM First half of backtest\tickers.txt (AAPL, MSFT, GOOGL, AMZN, NVDA).
REM Resumable: skips (fund, lookback, offset) combos already completed in
REM backtest_run_history.csv, so after a reboot just run this file again.
REM run_grid2.ps1 sweeps lookback 1/2/3Y x offset 3/6/9/12M for each fund.
REM It makes one pass and stops (no infinite loop) and aborts on repeated
REM failures instead of spinning. See nvda-run8x.log for progress.
REM Any additional PowerShell parameters passed to this .bat are forwarded, e.g.
REM   run8x.bat -CompletedMaxAgeDays 1 -ShortEmaBounds 5,80 -Force

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0run_grid2.ps1' -Funds V -Population 8 -Generations 4 -GaSearchPreset grid -PriceColumn 'Adj Close' -LogFile 'v-run8x.log' %*"

echo.
echo run_grid2 finished with exit code %ERRORLEVEL%.
echo (0 = all combos done/skipped, 1 = some failed, 2 = aborted on repeated failures)
