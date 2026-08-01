<#
.SYNOPSIS
    Resumable, crash-safe driver for the full-strength backtest grid sweep.

.DESCRIPTION
    Runs backtest\backtest_stocks.py once for every (fund, lookback, offset)
    combination in the requested grid. Unlike the old run10a.bat / run10b.bat
    loop, this script:

      * Skips any combo already marked "completed" in backtest_run_history.csv,
        so it resumes cleanly after a reboot or interruption -- just run it
        again and it picks up the remaining combos.
      * Checks the Python exit code for every combo and stops after
        -MaxConsecutiveFailures failures in a row, instead of spinning forever.
      * Makes exactly one pass (no infinite goto loop) and prints a summary.

    Written for Windows PowerShell 5.1 (what the .bat launchers invoke) and
    pwsh 7+ alike -- no ternary / null-coalescing operators are used.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\run_grid.ps1 `
        -Funds AAPL,MSFT,GOOGL,AMZN,NVDA -LogFile run10a.log

.EXAMPLE
    # Re-run the exact same command after a reboot; completed combos are skipped.
    .\run_grid.ps1 -Funds META,TSLA,JPM,V,JNJ -LogFile run10b.log

.EXAMPLE
    # Sweep the derived 4-year slices (data\AAPL-4Y.csv) instead of full history.
    .\run_grid.ps1 -Funds AAPL -DataSuffix '-4Y' -LogFile run4-4Y.log

.EXAMPLE
    # Keep matching runs for three days, then automatically tune them again.
    .\run_grid2.ps1 -Funds NVDA -Population 8 -Generations 4 `
        -ShortEmaBounds 1,100 -LongEmaBounds 30,600 -CompletedMaxAgeDays 3
#>
[CmdletBinding()]
param(
    [string[]]$Funds = @("AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"),
    [double[]]$LookbackYears = @(1, 2, 3),
    [int[]]$OffsetMonths = @(3, 6, 9, 12),
    [int]$Population = 10,
    [int]$Generations = 10,
    [string]$GaSearchPreset = "grid",
    [string]$PriceColumn = "Adj Close",
    # Appended to each fund name to pick the data file, e.g. -DataSuffix '-4Y'
    # runs data\AAPL-4Y.csv. Results are recorded under fund_label AAPL (the
    # group) with fund_slice_label AAPL-4Y.
    [string]$DataSuffix = "",
    # Every profile defined in backtest_stocks.py's STRATEGY_PROFILE_SETTINGS.
    # Keep this list in step with that dict -- a profile missing here cannot be
    # driven from the grid at all, which silently hid generic-ride,
    # generic-ride-slow and qqq-return-plus-nolev until 2026-07-26.
    [ValidateSet("generic", "generic-ride", "generic-ride-slow", "generic-bh-reachable",
                 "buyhold-1x", "qqq", "qqq-return-plus", "qqq-return-plus-nolev",
                 "qqq-buyhold-plus")]
    [string]$StrategyProfile = "generic",
    # Search bounds, each supplied as "MIN MAX". These are deliberately
    # broader than run_grid.ps1's defaults, but can now be customized per run.
    [ValidateCount(2, 2)][int[]]$ShortEmaBounds = @(1, 100),
    [ValidateCount(2, 2)][int[]]$LongEmaBounds = @(30, 600),
    [ValidateCount(2, 2)][int[]]$RsiOversoldBounds = @(1, 49),
    [ValidateCount(2, 2)][int[]]$RsiOverboughtBounds = @(51, 99),
    [ValidateCount(2, 2)][double[]]$StopLossBounds = @(5, 50),
    # Enables GA take-profit tuning from 0 through this percentage.
    [ValidateRange(0, 100)][double]$TakeProfitPct = 100,
    [ValidateCount(2, 2)][double[]]$DrawdownExitBounds = @(2, 100),
    [ValidateCount(2, 2)][double[]]$ReentryReboundBounds = @(0, 30),
    [ValidateCount(2, 2)][int[]]$CooldownBounds = @(0, 10),
    [string]$LogFile = "run_grid.log",
    [int]$MaxConsecutiveFailures = 3,
    [int]$TimeoutMinutes = 0,          # 0 = no per-combo timeout
    # A completed row is skipped only while it is this recent. Set 0 to re-run
    # all completed rows without using -Force; negative values are rejected.
    [ValidateRange(0, 3650)][int]$CompletedMaxAgeDays = 3,
    [switch]$Force,                    # re-run combos even if already completed
    [switch]$DryRun                    # print the skip/run plan, launch nothing
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Normalize -Funds so a single comma-joined string (e.g. when invoked via
# `powershell.exe -File ... -Funds AAPL,MSFT,GOOGL`, which does not split
# arrays) is expanded into individual fund names.
$Funds = @($Funds | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
if ($Funds.Count -eq 0) { throw "No funds specified." }

$repoRoot       = Split-Path -Parent $MyInvocation.MyCommand.Path
$backtestScript = Join-Path $repoRoot "backtest\backtest_stocks.py"
$runHistory     = Join-Path $repoRoot "backtest\outputs\tunings\backtest_run_history.csv"

if (-not (Test-Path $backtestScript)) {
    throw "Backtest script not found: $backtestScript"
}

if (-not [System.IO.Path]::IsPathRooted($LogFile)) {
    $LogFile = Join-Path $repoRoot $LogFile
}

function Write-Log {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line  = "[$stamp] $Message"
    Write-Host $line
    Add-Content -LiteralPath $LogFile -Value $line
}

function Test-NumberPairMatch {
    param(
        [object]$First,
        [object]$Second,
        [double[]]$Expected
    )
    if ($null -eq $First -or $null -eq $Second -or "$First" -eq "" -or "$Second" -eq "") {
        return $false
    }
    return ([math]::Abs(([double]$First) - $Expected[0]) -lt 0.000001) -and
           ([math]::Abs(([double]$Second) - $Expected[1]) -lt 0.000001)
}

# --- Build the set of already-completed combos from the run history ---------
# Key = "<slice label>|<lookback:0.0>|<offset>". A combo counts as done when a row
# matches this preset / population / generations and has run_status=completed.
#
# The key must be the SLICE label (AAPL-3Y), not fund_label: the backtester now
# records the fund group (AAPL) in fund_label, so keying on it would make a
# no-suffix AAPL sweep skip combos that were only ever run on the 3Y/4Y slices.
# fund_slice_label carries the slice; rows written before that column existed
# fall back to fund_label, which held the slice label back then.
$completed = @{}
$staleCount = 0
$freshAfter = (Get-Date).AddDays(-$CompletedMaxAgeDays)
if ((-not $Force) -and (Test-Path $runHistory)) {
    try {
        Import-Csv -LiteralPath $runHistory | ForEach-Object {
            if ($_.run_status -eq "completed" -and
                $_.ga_search_preset -eq $GaSearchPreset -and
                $_.strategy_profile -eq $StrategyProfile -and
                $_.pop_ranges -eq [string]$Population -and
                $_.gen_ranges -eq [string]$Generations -and
                $_.price_column -eq $PriceColumn -and
                (Test-NumberPairMatch $_.short_ema_min $_.short_ema_max $ShortEmaBounds) -and
                (Test-NumberPairMatch $_.long_ema_min $_.long_ema_max $LongEmaBounds) -and
                (Test-NumberPairMatch $_.rsi_oversold_min $_.rsi_oversold_max $RsiOversoldBounds) -and
                (Test-NumberPairMatch $_.rsi_overbought_min $_.rsi_overbought_max $RsiOverboughtBounds) -and
                (Test-NumberPairMatch $_.stop_loss_min $_.stop_loss_max $StopLossBounds) -and
                $null -ne $_.PSObject.Properties['take_profit_max'] -and
                "$($_.take_profit_max)" -ne "" -and
                ([math]::Abs(([double]$_.take_profit_max) - $TakeProfitPct) -lt 0.000001) -and
                (Test-NumberPairMatch $_.drawdown_exit_min $_.drawdown_exit_max $DrawdownExitBounds) -and
                (Test-NumberPairMatch $_.reentry_rebound_min $_.reentry_rebound_max $ReentryReboundBounds) -and
                (Test-NumberPairMatch $_.cooldown_min $_.cooldown_max $CooldownBounds)) {
                $sliceProp = $_.PSObject.Properties['fund_slice_label']
                if ($sliceProp -and "$($sliceProp.Value)".Trim() -ne "") {
                    $slice = $sliceProp.Value
                } else {
                    $slice = $_.fund_label
                }
                $lb  = "{0:0.0}" -f [double]$_.lookback_years
                $key = "{0}|{1}|{2}" -f $slice, $lb, $_.offset_months
                $completedAt = [datetime]::MinValue
                if (-not [datetime]::TryParse("$($_.run_completed_at)", [ref]$completedAt)) {
                    $staleCount++
                    return
                }
                if ($completedAt -lt $freshAfter) {
                    $staleCount++
                    return
                }
                if ((-not $completed.ContainsKey($key)) -or $completed[$key] -lt $completedAt) {
                    $completed[$key] = $completedAt
                }
            }
        }
    } catch {
        Write-Log "WARN could not parse run history ($($_.Exception.Message)); running all combos."
    }
}

# --- Plan the pass ----------------------------------------------------------
$plan = @()
foreach ($fund in $Funds) {
    # The data file stem is the slice label the backtester records in
    # fund_slice_label, so the suffix must be applied here for both the CSV name
    # and the resume key. (fund_label holds the group, e.g. AAPL for AAPL-3Y.)
    $fundLabel = "$fund$DataSuffix"
    foreach ($lb in $LookbackYears) {
        foreach ($off in $OffsetMonths) {
            $plan += [pscustomobject]@{
                Fund     = $fundLabel
                Group    = $fund
                Lookback = $lb
                Offset   = $off
                Key      = "{0}|{1:0.0}|{2}" -f $fundLabel, [double]$lb, $off
            }
        }
    }
}

$total     = $plan.Count
$skipCount = 0
$doneCount = 0
$failCount = 0
$consecFailures = 0
$aborted   = $false

Write-Log "==== run_grid2 start: $($Funds -join ',') | suffix='$DataSuffix' profile=$StrategyProfile preset=$GaSearchPreset pop=$Population gen=$Generations | $total combos ===="
Write-Log "Bounds: shortEMA=$($ShortEmaBounds -join '-') longEMA=$($LongEmaBounds -join '-') RSI-OS=$($RsiOversoldBounds -join '-') RSI-OB=$($RsiOverboughtBounds -join '-') stop=$($StopLossBounds -join '-') takeProfit=0-$TakeProfitPct drawdown=$($DrawdownExitBounds -join '-') rebound=$($ReentryReboundBounds -join '-') cooldown=$($CooldownBounds -join '-')"
Write-Log "Fresh completed combos (will skip): $($completed.Count), within $CompletedMaxAgeDays day(s); stale/unparseable matching rows: $staleCount."

$idx = 0
foreach ($item in $plan) {
    $idx++
    $label = "$($item.Fund) $($item.Lookback)Y/$($item.Offset)M"

    if ((-not $Force) -and $completed.ContainsKey($item.Key)) {
        $skipCount++
        Write-Log "SKIP  [$idx/$total] $label (already completed)"
        continue
    }

    if ($DryRun) {
        $doneCount++
        Write-Log "PLAN  [$idx/$total] $label (would run)"
        continue
    }

    Write-Log "RUN   [$idx/$total] $label"
    $sw = [System.Diagnostics.Stopwatch]::StartNew()

    $pyArgs = @(
        $backtestScript
        "--lookback-years", "$($item.Lookback)"
        "--offset-months", "$($item.Offset)"
        "--pop_ranges", "$Population"
        "--gen_ranges", "$Generations"
        "--ga-search-preset", $GaSearchPreset
        "--strategy-profile", $StrategyProfile
        "--price-column", $PriceColumn
        "--reuse-tuned-params"
        "--short-ema-bounds", "$($ShortEmaBounds[0])", "$($ShortEmaBounds[1])"
        "--long-ema-bounds", "$($LongEmaBounds[0])", "$($LongEmaBounds[1])"
        "--rsi-oversold-bounds", "$($RsiOversoldBounds[0])", "$($RsiOversoldBounds[1])"
        "--rsi-overbought-bounds", "$($RsiOverboughtBounds[0])", "$($RsiOverboughtBounds[1])"
        "--stop-loss-bounds", "$($StopLossBounds[0])", "$($StopLossBounds[1])"
        "--take-profit-pct", "$TakeProfitPct"
        "--drawdown-exit-bounds", "$($DrawdownExitBounds[0])", "$($DrawdownExitBounds[1])"
        "--reentry-rebound-bounds", "$($ReentryReboundBounds[0])", "$($ReentryReboundBounds[1])"
        "--cooldown-bounds", "$($CooldownBounds[0])", "$($CooldownBounds[1])"
        "--data-file", "$($item.Fund).csv"
        "--fund-group", "$($item.Group)"
    )

    $exit = 0
    try {
        if ($TimeoutMinutes -gt 0) {
            $proc = Start-Process -FilePath "python" -ArgumentList $pyArgs `
                -NoNewWindow -PassThru
            if (-not $proc.WaitForExit($TimeoutMinutes * 60 * 1000)) {
                try { $proc.Kill() } catch {}
                $exit = 124
                Write-Log "TIMEOUT [$idx/$total] $label after $TimeoutMinutes min"
            } else {
                $exit = $proc.ExitCode
            }
        } else {
            & python @pyArgs
            $exit = $LASTEXITCODE
        }
    } catch {
        $exit = 1
        Write-Log "ERROR [$idx/$total] $label threw: $($_.Exception.Message)"
    }

    $sw.Stop()
    $mins = [math]::Round($sw.Elapsed.TotalMinutes, 1)

    if ($exit -eq 0) {
        $doneCount++
        $consecFailures = 0
        Write-Log "OK    [$idx/$total] $label in ${mins}m"
    } else {
        $failCount++
        $consecFailures++
        Write-Log "FAIL  [$idx/$total] $label exit=$exit (${mins}m) consecutive=$consecFailures"
        if ($consecFailures -ge $MaxConsecutiveFailures) {
            Write-Log "ABORT $consecFailures consecutive failures >= $MaxConsecutiveFailures. Stopping."
            $aborted = $true
            break
        }
    }
}

Write-Log "==== run_grid2 done: ran=$doneCount skipped=$skipCount failed=$failCount of $total | aborted=$aborted ===="

if ($aborted) { exit 2 }
if ($failCount -gt 0) { exit 1 }
exit 0
