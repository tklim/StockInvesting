@echo off
setlocal
cd /d "%~dp0"

REM MSFT on the derived 3-year slice (backtest\data\MSFT-3Y.csv), pop=4 gen=2.
REM Resumable: skips combos already completed in backtest_run_history.csv, so
REM after a reboot just run this file again. A combo counts as completed only
REM for the SAME transition policy and GA seed, so an A/B pass never resumes
REM off the other policy's history.
REM run_grid.ps1 sweeps lookback 1/2Y x offset 3/6/9/12M for each fund. Lookback
REM 3Y is deliberately excluded: the data file is exactly 3.0 years, so a 3Y
REM lookback leaves no out-of-sample window and returns a degenerate 0% run.
REM It makes one pass and stops (no infinite loop) and aborts on repeated
REM failures instead of spinning. See msft-run4.log for progress.
REM
REM Override the log file per pass by setting LOGFILE first -- run_grid.ps1
REM rejects a second -LogFile on the command line (ParameterAlreadyBound):
REM   set "LOGFILE=msft-ab-none.log" && run4-msft.bat -GaSeed 999 -TransitionPolicy none
REM Any other run_grid.ps1 switch can be appended to this file's arguments.

if "%LOGFILE%"=="" set "LOGFILE=msft-run4.log"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0run_grid.ps1' -Funds MSFT -DataSuffix '-10Y' -GaWarmStart -LookbackYears 1,2 -Population 4 -Generations 2 -GaSearchPreset grid -PriceColumn 'Adj Close' -LogFile '%LOGFILE%' %*"

echo.
echo run_grid finished with exit code %ERRORLEVEL%.
echo (0 = all combos done/skipped, 1 = some failed, 2 = aborted on repeated failures)
endlocal
