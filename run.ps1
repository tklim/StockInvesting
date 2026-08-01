param(
    [double[]]$LookbackYears = @(1, 2, 3),
    [int[]]$OffsetMonths = @(3, 6, 9, 12),
    [int]$Population = 10,
    [int]$Generations = 10,
    [string]$GaSearchPreset = "focused",
    [string]$PriceColumn = "Adj Close",
    [string[]]$ExtraArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backtestScript = Join-Path $repoRoot "backtest\backtest_stocks.py"

if (-not (Test-Path $backtestScript)) {
    throw "Backtest script not found: $backtestScript"
}

foreach ($lookback in $LookbackYears) {
    foreach ($offset in $OffsetMonths) {
        $pyArgs = @(
            $backtestScript
            "--lookback-years", "$lookback"
            "--offset-months", "$offset"
            "--pop_ranges", "$Population"
            "--gen_ranges", "$Generations"
            "--ga-search-preset", $GaSearchPreset
            "--price-column", $PriceColumn
            "--reuse-tuned-params"
        ) + $ExtraArgs

        Write-Host ""
        Write-Host ("=" * 72)
        Write-Host "Running backtest with lookback-years=$lookback and offset-months=$offset"
        Write-Host "Command: python $($pyArgs -join ' ')"
        Write-Host ("=" * 72)

        & python @pyArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Backtest failed for lookback-years=$lookback, offset-months=$offset with exit code $LASTEXITCODE"
        }
    }
}
