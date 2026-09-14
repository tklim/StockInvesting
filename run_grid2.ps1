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

.EXAMPLE
    # A/B the offset-month transition policy and/or GA warm start at a pinned
    # seed. Policy, seed, and warm-start settings are all part of the resume
    # identity, so these two passes do not skip each other.
    .\run_grid2.ps1 -Funds MSFT -Population 6 -Generations 3 -GaSeed 999 `
        -TransitionPolicy none        -LogFile ab-none.log
    .\run_grid2.ps1 -Funds MSFT -Population 6 -Generations 3 -GaSeed 999 `
        -TransitionPolicy grandfather -LogFile ab-grandfather.log
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
    # Fixed GA seed. Omit for the backtester's deterministic per-window seeding
    # (recorded as "deterministic"). Part of the resume identity below, so an
    # A/B at a pinned seed never resumes off differently-seeded history.
    [int]$GaSeed,
    # How a position carried across an offset-month boundary is exited.
    # 'grandfather' keeps the exit rules of the window that opened the
    # position until it closes. Part of the resume identity: the same combo
    # run under a different policy is a DIFFERENT experiment, not a repeat.
    [ValidateSet("none", "grandfather")]
    [string]$TransitionPolicy = "none",
    # Seed each window's GA with the previous window's best parameters instead
    # of starting from random guesses (H-014). Also part of the resume identity.
    [switch]$GaWarmStart,
    [ValidateRange(0.0, 1.0)][double]$GaWarmStartFraction = 0.5,
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

# A source slice with a lookback equal to its full source horizon has no
# out-of-sample run period. Keep the cell in the plan for transparent
# accounting, but never launch the backtest. The source horizon is taken from
# the explicit slice suffix (for example, -3Y); an unsuffixed file is left
# unchanged because it has no reliable source-year label.
$sourceYears = $null
$sourceSuffixMatch = [regex]::Match($DataSuffix, '^-?(?<years>\d+(?:\.\d+)?)Y$', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
if ($sourceSuffixMatch.Success) {
    $sourceYears = [double]$sourceSuffixMatch.Groups['years'].Value
}

# An omitted -GaSeed means "let the backtester seed each window deterministically",
# which it records as the literal string "deterministic".
$useGaSeed = $PSBoundParameters.ContainsKey('GaSeed')
if ($useGaSeed) { $gaSeedLabel = "$GaSeed" } else { $gaSeedLabel = "deterministic" }

# The backtester records ga_warm_start as a Python bool, i.e. True/False, and
# leaves the fraction blank when warm start is off.
if ($GaWarmStart) {
    $warmStartLabel = "True"
} else {
    $warmStartLabel = "False"
}

$repoRoot       = Split-Path -Parent $MyInvocation.MyCommand.Path
$backtestScript = Join-Path $repoRoot "backtest\backtest_stocks.py"
$runHistory     = Join-Path $repoRoot "backtest\outputs\tunings\backtest_run_history.csv"
$dataDir        = Join-Path $repoRoot "backtest\data"

function Get-DataFileHash {
    # Derived slice files (MSFT-3Y.csv) are regenerated periodically and roll
    # forward silently -- same name, often the same end date, different start
    # and row count. Keying resume on the file hash stops a completed run on an
    # older vintage from satisfying a sweep against the current one.
    param([string]$FundLabel)
    $path = Join-Path $dataDir "$FundLabel.csv"
    if (-not (Test-Path $path)) { return "" }
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower()
}

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

function Get-RowValue {
    # Read a history column that may not exist in older rows. Set-StrictMode
    # turns a plain $row.missing_column into a terminating error, so every
    # optional column must be probed through PSObject.Properties.
    param(
        [Parameter(Mandatory = $true)]$Row,
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Default = ""
    )
    $prop = $Row.PSObject.Properties[$Name]
    if (-not $prop) { return $Default }
    $value = "$($prop.Value)".Trim()
    if ($value -eq "") { return $Default }
    return $value
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
#
# transition_policy, ga_seed, and ga_warm_start(+fraction) join the bound
# checks below as row FILTERS, not key parts: a combo already run under a
# different policy, seed, or warm-start setting answers a different question,
# so it must not satisfy this invocation. Without this, an A/B sweep of any of
# these would skip every combo as "completed" and report success having
# launched nothing. Rows predating these columns read as policy "none", seed
# "deterministic", warm start "False" -- exactly what those rows actually were.
$completed = @{}
$staleCount = 0
$freshAfter = (Get-Date).AddDays(-$CompletedMaxAgeDays)
if ((-not $Force) -and (Test-Path $runHistory)) {
    try {
        Import-Csv -LiteralPath $runHistory | ForEach-Object {
            $rowPolicy = Get-RowValue -Row $_ -Name 'transition_policy' -Default 'none'
            $rowSeed   = Get-RowValue -Row $_ -Name 'ga_seed' -Default 'deterministic'
            $rowWarm   = Get-RowValue -Row $_ -Name 'ga_warm_start' -Default 'False'
            $rowWarmFraction = Get-RowValue -Row $_ -Name 'ga_warm_start_fraction' -Default ''
            # The fraction only distinguishes runs while warm start is on; when
            # it is off the backtester leaves the column blank.
            $warmMatches = ($rowWarm -eq $warmStartLabel) -and
                           ((-not $GaWarmStart) -or
                            ([double]("0" + $rowWarmFraction) -eq $GaWarmStartFraction))
            if ($_.run_status -eq "completed" -and
                $_.ga_search_preset -eq $GaSearchPreset -and
                $_.strategy_profile -eq $StrategyProfile -and
                $rowPolicy -eq $TransitionPolicy -and
                $rowSeed -eq $gaSeedLabel -and
                $warmMatches -and
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
                $rowDataHash = Get-RowValue -Row $_ -Name 'data_file_sha256' -Default ''
                $lb  = "{0:0.0}" -f [double]$_.lookback_years
                # The data hash joins the key rather than the filters above so a
                # vintage change invalidates only the affected fund's combos.
                # Rows predating the column carry an empty hash and can never
                # match a current file, so they are re-run rather than trusted.
                $key = "{0}|{1}|{2}|{3}" -f $slice, $lb, $_.offset_months, $rowDataHash
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
    $dataHash = Get-DataFileHash $fundLabel
    foreach ($lb in $LookbackYears) {
        foreach ($off in $OffsetMonths) {
            $skipReason = ""
            if ($sourceYears -eq 3.0 -and [double]$lb -eq 3.0) {
                $skipReason = "not applicable: 3Y source / 3Y lookback (no run period)"
            }
            $plan += [pscustomobject]@{
                Fund     = $fundLabel
                Group    = $fund
                Lookback = $lb
                Offset   = $off
                Skip     = ($skipReason -ne "")
                SkipReason = $skipReason
                Key      = "{0}|{1:0.0}|{2}|{3}" -f $fundLabel, [double]$lb, $off, $dataHash
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

Write-Log "==== run_grid2 start: $($Funds -join ',') | suffix='$DataSuffix' profile=$StrategyProfile preset=$GaSearchPreset pop=$Population gen=$Generations transition=$TransitionPolicy seed=$gaSeedLabel warmstart=$warmStartLabel$(if ($GaWarmStart) { "/$GaWarmStartFraction" }) | $total combos ===="
Write-Log "Bounds: shortEMA=$($ShortEmaBounds -join '-') longEMA=$($LongEmaBounds -join '-') RSI-OS=$($RsiOversoldBounds -join '-') RSI-OB=$($RsiOverboughtBounds -join '-') stop=$($StopLossBounds -join '-') takeProfit=0-$TakeProfitPct drawdown=$($DrawdownExitBounds -join '-') rebound=$($ReentryReboundBounds -join '-') cooldown=$($CooldownBounds -join '-')"
Write-Log "Fresh completed combos (will skip): $($completed.Count), within $CompletedMaxAgeDays day(s); stale/unparseable matching rows: $staleCount."

$idx = 0
foreach ($item in $plan) {
    $idx++
    $label = "$($item.Fund) $($item.Lookback)Y/$($item.Offset)M"

    if ($item.Skip) {
        $skipCount++
        Write-Log "SKIP  [$idx/$total] $label ($($item.SkipReason))"
        continue
    }

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
        "--transition-policy", $TransitionPolicy
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
    # Omitted entirely when unset so the backtester keeps its own deterministic
    # per-window seeding; passing a placeholder would silently pin every window.
    if ($useGaSeed) {
        $pyArgs += @("--ga-seed", "$GaSeed")
    }
    if ($GaWarmStart) {
        $pyArgs += @("--ga-warm-start", "--ga-warm-start-fraction", "$GaWarmStartFraction")
    }

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
