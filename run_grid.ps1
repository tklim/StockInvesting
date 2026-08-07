<#
.SYNOPSIS
    Resumable, crash-safe driver for the full-strength backtest grid sweep.

.DESCRIPTION
    Runs backtest\backtest_stocks.py once for every (fund, lookback, offset)
    combination in the requested grid. Unlike the old run10a.bat / run10b.bat
    loop, this script:

      * Skips only recently completed combos from backtest_run_history.csv
        (24 hours by default), so it resumes a recent interruption without
        silently treating an old sweep as the current invocation.
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
    # A/B the offset-month transition policy at a pinned seed. The two passes
    # do not skip each other: policy and seed are part of the resume identity.
    .\run_grid.ps1 -Funds MSFT,SPY,NVDA -DataSuffix '-3Y' -GaSeed 999 `
        -TransitionPolicy none        -LogFile ab-none.log
    .\run_grid.ps1 -Funds MSFT,SPY,NVDA -DataSuffix '-3Y' -GaSeed 999 `
        -TransitionPolicy grandfather -LogFile ab-grandfather.log

.EXAMPLE
    # Widen the GA search space. The bounds are part of the resume identity, so
    # this pass neither skips nor is skipped by a default-bounds sweep of the
    # same cell. Keep long EMA under the training window (a 1Y lookback is only
    # ~250 trading days) and RSI bounds inside 0-100, or the genes stop binding.
    .\run_grid.ps1 -Funds JPM -DataSuffix '-3Y' -LookbackYears 1 -OffsetMonths 3 `
        -Population 16 -Generations 8 -GaSeed 1111 -TransitionPolicy grandfather `
        -ShortEmaBounds 2,100 -LongEmaBounds 30,240 `
        -RsiOversoldBounds 5,45 -RsiOverboughtBounds 55,95 `
        -StopLossBounds 3,25 -LogFile jpm-wide.log
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
    # How a position carried across an offset-month boundary is exited.
    # 'grandfather' keeps the exit rules of the window that opened the position
    # until it closes. Part of the resume identity below: the same combo run
    # under a different policy is a DIFFERENT experiment, not a repeat.
    [ValidateSet("none", "grandfather")]
    [string]$TransitionPolicy = "none",
    # Fixed GA seed. Omit for the backtester's deterministic per-window seeding
    # (recorded as "deterministic"). Also part of the resume identity, so an
    # A/B at a pinned seed never resumes off differently-seeded history.
    [int]$GaSeed,
    # Seed each window's GA with the previous window's winner instead of
    # re-tuning from random guesses (H-014). Also part of the resume identity.
    [switch]$GaWarmStart,
    [ValidateRange(0.0, 1.0)][double]$GaWarmStartFraction = 0.5,
    # Search-space bound overrides, each "MIN MAX". Unlike the exit-gene bounds
    # below, these four have profile-INDEPENDENT defaults in backtest_stocks.py,
    # so run_grid always knows what a run would have used and can therefore hold
    # them in the resume identity unconditionally (see $expectedBounds).
    [int[]]$ShortEmaBounds,
    [int[]]$LongEmaBounds,
    [int[]]$RsiOversoldBounds,
    [int[]]$RsiOverboughtBounds,
    # Exit-gene bound overrides, each "MIN MAX". These beat the profile's own
    # gene_bounds, so e.g. -StopLossBounds 20,60 searches wider stops than the
    # profile would allow. Omit to let the profile decide.
    [double[]]$StopLossBounds,
    [double[]]$DrawdownExitBounds,
    [double[]]$ReentryReboundBounds,
    [int[]]$CooldownBounds,
    [string]$LogFile = "run_grid.log",
    [int]$MaxConsecutiveFailures = 3,
    [int]$TimeoutMinutes = 0,          # 0 = no per-combo timeout
    # Completed rows are reusable only while this recent. This lets a cancelled
    # grid continue from its fresh successes while re-running old history.
    # Set 0 to ignore all completed history; increase it for a longer window.
    [ValidateRange(0, 8760)][int]$CompletedMaxAgeHours = 24,
    # Uses the same <history>.lock sentinel as backtest_stocks.py while taking
    # the resume snapshot. Time out safely instead of treating a mid-write CSV
    # as an empty history and launching duplicate work.
    [ValidateRange(1, 900)][int]$HistoryReadLockTimeoutSeconds = 180,
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

# An omitted -GaSeed means "let the backtester seed each window deterministically",
# which it records as the literal string "deterministic".
$useGaSeed = $PSBoundParameters.ContainsKey('GaSeed')
if ($useGaSeed) { $gaSeedLabel = "$GaSeed" } else { $gaSeedLabel = "deterministic" }

# The backtester records ga_warm_start as a Python bool, i.e. True/False, and
# leaves the fraction blank when warm start is off.
if ($GaWarmStart) {
    $warmStartLabel = "True"
    $warmStartFractionLabel = "$GaWarmStartFraction"
} else {
    $warmStartLabel = "False"
    $warmStartFractionLabel = ""
}

# --- Search-space bounds, as part of the resume identity --------------------
# A run made over a WIDER search space answers a different question than one
# made over the default space, exactly like a different policy or seed does.
# Before this was enforced, a hand-launched wide-bounds run (e.g. JPM with
# --short-ema-bounds 1 100 --long-ema-bounds 30 600) was recorded as "completed"
# for its cell and silently satisfied a later default-bounds sweep.
#
# These four mirror DEFAULT_SHORT_EMA_BOUNDS / DEFAULT_LONG_EMA_BOUNDS /
# DEFAULT_RSI_OVERSOLD_BOUNDS / DEFAULT_RSI_OVERBOUGHT_BOUNDS in
# backtest_stocks.py. They are argparse defaults, NOT profile-derived, so the
# value a run used is knowable here without duplicating STRATEGY_PROFILE_SETTINGS.
# If the Python defaults ever change, these stop matching and every old row is
# treated as stale -- runs get repeated rather than wrongly skipped, which is
# the safe direction to fail.
$BACKTESTER_DEFAULT_BOUNDS = @{
    short_ema      = @(2, 60)
    long_ema       = @(30, 300)
    rsi_oversold   = @(10, 40)
    rsi_overbought = @(60, 90)
}

# Expected bounds for THIS invocation: the override when supplied, else the
# backtester default. Held unconditionally in the resume filter below.
$expectedBounds = @{}
foreach ($b in @(
    @{ Key = "short_ema";      Param = "ShortEmaBounds";      Value = $ShortEmaBounds },
    @{ Key = "long_ema";       Param = "LongEmaBounds";       Value = $LongEmaBounds },
    @{ Key = "rsi_oversold";   Param = "RsiOversoldBounds";   Value = $RsiOversoldBounds },
    @{ Key = "rsi_overbought"; Param = "RsiOverboughtBounds"; Value = $RsiOverboughtBounds }
)) {
    if ($PSBoundParameters.ContainsKey($b.Param)) {
        if (@($b.Value).Count -ne 2) { throw "-$($b.Param) needs exactly two values: MIN MAX." }
        $expectedBounds[$b.Key] = @([double]$b.Value[0], [double]$b.Value[1])
    } else {
        $expectedBounds[$b.Key] = @([double]$BACKTESTER_DEFAULT_BOUNDS[$b.Key][0],
                                    [double]$BACKTESTER_DEFAULT_BOUNDS[$b.Key][1])
    }
}

# The four exit-gene bounds resolve from the active profile's gene_bounds when
# not supplied, and run_grid has no copy of that table -- so they join the
# identity only when explicitly overridden here. Residual gap: a hand-launched
# run that overrode ONLY an exit-gene bound (and left the four above at their
# defaults) can still satisfy a sweep that omits it. Drive such experiments
# through -StopLossBounds etc. so both sides carry the same override.
$expectedExitBounds = @{}
foreach ($b in @(
    @{ Key = "stop_loss";       Param = "StopLossBounds";       Value = $StopLossBounds },
    @{ Key = "drawdown_exit";   Param = "DrawdownExitBounds";   Value = $DrawdownExitBounds },
    @{ Key = "reentry_rebound"; Param = "ReentryReboundBounds"; Value = $ReentryReboundBounds },
    @{ Key = "cooldown";        Param = "CooldownBounds";       Value = $CooldownBounds }
)) {
    if ($PSBoundParameters.ContainsKey($b.Param)) {
        if (@($b.Value).Count -ne 2) { throw "-$($b.Param) needs exactly two values: MIN MAX." }
        $expectedExitBounds[$b.Key] = @([double]$b.Value[0], [double]$b.Value[1])
    }
}

function Test-BoundMatch {
    # History stores bounds as strings and mixes int/float spellings ("15" vs
    # "15.0"), so compare numerically. A row missing the column (written before
    # it existed) can never match a known bound and is therefore not resumable.
    param(
        [Parameter(Mandatory = $true)]$Row,
        [Parameter(Mandatory = $true)][string]$MinColumn,
        [Parameter(Mandatory = $true)][string]$MaxColumn,
        [Parameter(Mandatory = $true)][double[]]$Expected
    )
    $rowMin = Get-RowValue -Row $Row -Name $MinColumn
    $rowMax = Get-RowValue -Row $Row -Name $MaxColumn
    if ($rowMin -eq "" -or $rowMax -eq "") { return $false }
    $parsedMin = 0.0; $parsedMax = 0.0
    if (-not [double]::TryParse($rowMin, [ref]$parsedMin)) { return $false }
    if (-not [double]::TryParse($rowMax, [ref]$parsedMax)) { return $false }
    return ($parsedMin -eq $Expected[0]) -and ($parsedMax -eq $Expected[1])
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

function Enter-RunHistoryLock {
    param(
        [string]$LockPath,
        [int]$TimeoutSeconds
    )

    # Match backtest/common.py's O_CREAT|O_EXCL sentinel protocol. The unique
    # token ensures this process only removes the lock it created.
    $token = "pid=$PID host=$env:COMPUTERNAME at=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') nonce=$([guid]::NewGuid().ToString('N'))"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $delayMilliseconds = 100

    while ($true) {
        $stream = $null
        $writer = $null
        try {
            $stream = [System.IO.File]::Open(
                $LockPath,
                [System.IO.FileMode]::CreateNew,
                [System.IO.FileAccess]::Write,
                [System.IO.FileShare]::None
            )
            $writer = New-Object System.IO.StreamWriter($stream)
            $writer.Write($token)
            $writer.Flush()
            return $token
        } catch [System.IO.IOException] {
            if ((Get-Date) -ge $deadline) {
                throw "Timed out after $TimeoutSeconds seconds waiting for run-history lock: $LockPath"
            }
            Start-Sleep -Milliseconds $delayMilliseconds
            $delayMilliseconds = [math]::Min($delayMilliseconds * 2, 1000)
        } finally {
            if ($writer) {
                $writer.Dispose()
            } elseif ($stream) {
                $stream.Dispose()
            }
        }
    }
}

function Exit-RunHistoryLock {
    param(
        [string]$LockPath,
        [string]$Token
    )

    try {
        if (Test-Path -LiteralPath $LockPath) {
            $owner = (Get-Content -LiteralPath $LockPath -Raw -ErrorAction Stop).Trim()
            if ($owner -eq $Token) {
                Remove-Item -LiteralPath $LockPath -Force -ErrorAction Stop
            }
        }
    } catch {
        # A stale-lock breaker may already have removed or replaced the lock.
        # Never delete an unverified lock belonging to another process.
        Write-Log "WARN could not release run-history lock ($($_.Exception.Message))."
    }
}

function Get-RunHistorySnapshot {
    param(
        [string]$HistoryPath,
        [int]$TimeoutSeconds
    )

    $lockPath = "$HistoryPath.lock"
    $token = Enter-RunHistoryLock -LockPath $lockPath -TimeoutSeconds $TimeoutSeconds
    try {
        if (-not (Test-Path -LiteralPath $HistoryPath)) {
            return [pscustomobject]@{ Exists = $false; Rows = @() }
        }

        $item = Get-Item -LiteralPath $HistoryPath
        if ($item.Length -eq 0) {
            throw "Run history is empty while locked: $HistoryPath"
        }

        return [pscustomobject]@{
            Exists = $true
            Rows   = @(Import-Csv -LiteralPath $HistoryPath -ErrorAction Stop)
        }
    } finally {
        Exit-RunHistoryLock -LockPath $lockPath -Token $token
    }
}

# --- Build the set of already-completed combos from the run history ---------
# Key = "<slice label>|<lookback:0.0>|<offset>". A combo counts as done when a row
# matches this preset / population / generations and has run_status=completed.
#
# The key must be the SLICE label (AAPL-3Y), not fund_label: the backtester now
# records the fund group (AAPL) in fund_label, so keying on it would make a
# no-suffix AAPL sweep skip combos that were only ever run on the 3Y/4Y slices.
# fund_slice_label carries the slice; rows written before that column existed
# fall back to fund_label, which held the slice label back then. Old or
# unparseable completion timestamps are deliberately stale, not resumable.
#
# transition_policy and ga_seed join preset/profile/pop/gen/price as row
# FILTERS, not key parts: a combo already run under a different policy or seed
# answers a different question, so it must not satisfy this invocation. Without
# this, an A/B sweep of the same grid would skip every combo as "completed" and
# report success having launched nothing.
$completed = New-Object 'System.Collections.Generic.HashSet[string]'
$staleCompleted = New-Object 'System.Collections.Generic.HashSet[string]'
$freshAfter = (Get-Date).AddHours(-$CompletedMaxAgeHours)
if (-not $Force) {
    try {
        $historySnapshot = Get-RunHistorySnapshot `
            -HistoryPath $runHistory `
            -TimeoutSeconds $HistoryReadLockTimeoutSeconds
        $historySnapshot.Rows | ForEach-Object {
            # Rows predating the transition_policy column were all produced by
            # the original behavior, which is exactly what "none" now means.
            $rowPolicy = Get-RowValue -Row $_ -Name 'transition_policy' -Default 'none'
            $rowSeed   = Get-RowValue -Row $_ -Name 'ga_seed' -Default 'deterministic'
            $rowWarm   = Get-RowValue -Row $_ -Name 'ga_warm_start' -Default 'False'
            $rowWarmFraction = Get-RowValue -Row $_ -Name 'ga_warm_start_fraction' -Default ''
            # The fraction only distinguishes runs while warm start is on; when
            # it is off the backtester leaves the column blank.
            $warmMatches = ($rowWarm -eq $warmStartLabel) -and
                           ((-not $GaWarmStart) -or
                            ([double]("0" + $rowWarmFraction) -eq $GaWarmStartFraction))
            # Search-space identity. The four profile-independent bounds are
            # always checked; the exit-gene bounds only when this invocation
            # overrode them (see $expectedExitBounds).
            $boundsMatch =
                (Test-BoundMatch -Row $_ -MinColumn 'short_ema_min'      -MaxColumn 'short_ema_max'      -Expected $expectedBounds['short_ema']) -and
                (Test-BoundMatch -Row $_ -MinColumn 'long_ema_min'       -MaxColumn 'long_ema_max'       -Expected $expectedBounds['long_ema']) -and
                (Test-BoundMatch -Row $_ -MinColumn 'rsi_oversold_min'   -MaxColumn 'rsi_oversold_max'   -Expected $expectedBounds['rsi_oversold']) -and
                (Test-BoundMatch -Row $_ -MinColumn 'rsi_overbought_min' -MaxColumn 'rsi_overbought_max' -Expected $expectedBounds['rsi_overbought'])
            if ($boundsMatch) {
                foreach ($exit in @(
                    @{ Key = 'stop_loss';       Min = 'stop_loss_min';       Max = 'stop_loss_max' },
                    @{ Key = 'drawdown_exit';   Min = 'drawdown_exit_min';   Max = 'drawdown_exit_max' },
                    @{ Key = 'reentry_rebound'; Min = 'reentry_rebound_min'; Max = 'reentry_rebound_max' },
                    @{ Key = 'cooldown';        Min = 'cooldown_min';        Max = 'cooldown_max' }
                )) {
                    if ($expectedExitBounds.ContainsKey($exit.Key)) {
                        if (-not (Test-BoundMatch -Row $_ -MinColumn $exit.Min -MaxColumn $exit.Max `
                                                  -Expected $expectedExitBounds[$exit.Key])) {
                            $boundsMatch = $false
                            break
                        }
                    }
                }
            }
            if ($_.run_status -eq "completed" -and
                $boundsMatch -and
                $_.ga_search_preset -eq $GaSearchPreset -and
                $_.strategy_profile -eq $StrategyProfile -and
                $rowPolicy -eq $TransitionPolicy -and
                $rowSeed -eq $gaSeedLabel -and
                $warmMatches -and
                $_.pop_ranges -eq [string]$Population -and
                $_.gen_ranges -eq [string]$Generations -and
                $_.price_column -eq $PriceColumn) {
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
                if ($CompletedMaxAgeHours -eq 0 -or
                    -not [datetime]::TryParse("$($_.run_completed_at)", [ref]$completedAt) -or
                    $completedAt -lt $freshAfter) {
                    [void]$staleCompleted.Add($key)
                    return
                }
                [void]$completed.Add($key)
                [void]$staleCompleted.Remove($key)
            }
        }
    } catch {
        throw "Could not read a stable run-history snapshot. Refusing to launch a duplicate grid: $($_.Exception.Message)"
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
            $plan += [pscustomobject]@{
                Fund     = $fundLabel
                Group    = $fund
                Lookback = $lb
                Offset   = $off
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
$freshPlanCount = @($plan | Where-Object { $completed.Contains($_.Key) }).Count
$stalePlanCount = @($plan | Where-Object {
    (-not $completed.Contains($_.Key)) -and $staleCompleted.Contains($_.Key)
}).Count

$boundsLabel = "sEMA=$($expectedBounds['short_ema'][0])-$($expectedBounds['short_ema'][1])" +
               " lEMA=$($expectedBounds['long_ema'][0])-$($expectedBounds['long_ema'][1])" +
               " rsiOS=$($expectedBounds['rsi_oversold'][0])-$($expectedBounds['rsi_oversold'][1])" +
               " rsiOB=$($expectedBounds['rsi_overbought'][0])-$($expectedBounds['rsi_overbought'][1])"
foreach ($k in @('stop_loss', 'drawdown_exit', 'reentry_rebound', 'cooldown')) {
    if ($expectedExitBounds.ContainsKey($k)) {
        $boundsLabel += " $k=$($expectedExitBounds[$k][0])-$($expectedExitBounds[$k][1])"
    }
}

Write-Log "==== run_grid start: $($Funds -join ',') | suffix='$DataSuffix' profile=$StrategyProfile preset=$GaSearchPreset pop=$Population gen=$Generations transition=$TransitionPolicy seed=$gaSeedLabel warmstart=$warmStartLabel$(if ($GaWarmStart) { "/$GaWarmStartFraction" }) | bounds: $boundsLabel | $total combos ===="
if ($Force) {
    Write-Log "Force mode: completion history ignored."
} else {
    Write-Log "Fresh completed combos (will skip): $freshPlanCount/$total within $CompletedMaxAgeHours hour(s); stale/unparseable plan combos: $stalePlanCount."
}

$idx = 0
foreach ($item in $plan) {
    $idx++
    $label = "$($item.Fund) $($item.Lookback)Y/$($item.Offset)M"

    if ((-not $Force) -and $completed.Contains($item.Key)) {
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
    # Optional search-space bound overrides, forwarded only when supplied so the
    # backtester keeps its own defaults for anything left unset.
    if ($PSBoundParameters.ContainsKey('ShortEmaBounds')) {
        $pyArgs += @("--short-ema-bounds", "$($ShortEmaBounds[0])", "$($ShortEmaBounds[1])")
    }
    if ($PSBoundParameters.ContainsKey('LongEmaBounds')) {
        $pyArgs += @("--long-ema-bounds", "$($LongEmaBounds[0])", "$($LongEmaBounds[1])")
    }
    if ($PSBoundParameters.ContainsKey('RsiOversoldBounds')) {
        $pyArgs += @("--rsi-oversold-bounds", "$($RsiOversoldBounds[0])", "$($RsiOversoldBounds[1])")
    }
    if ($PSBoundParameters.ContainsKey('RsiOverboughtBounds')) {
        $pyArgs += @("--rsi-overbought-bounds", "$($RsiOverboughtBounds[0])", "$($RsiOverboughtBounds[1])")
    }
    # Optional exit-gene bound overrides, forwarded only when supplied so the
    # profile keeps control of anything left unset.
    if ($PSBoundParameters.ContainsKey('StopLossBounds')) {
        $pyArgs += @("--stop-loss-bounds", "$($StopLossBounds[0])", "$($StopLossBounds[1])")
    }
    if ($PSBoundParameters.ContainsKey('DrawdownExitBounds')) {
        $pyArgs += @("--drawdown-exit-bounds", "$($DrawdownExitBounds[0])", "$($DrawdownExitBounds[1])")
    }
    if ($PSBoundParameters.ContainsKey('ReentryReboundBounds')) {
        $pyArgs += @("--reentry-rebound-bounds", "$($ReentryReboundBounds[0])", "$($ReentryReboundBounds[1])")
    }
    if ($PSBoundParameters.ContainsKey('CooldownBounds')) {
        $pyArgs += @("--cooldown-bounds", "$($CooldownBounds[0])", "$($CooldownBounds[1])")
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

Write-Log "==== run_grid done: ran=$doneCount skipped=$skipCount failed=$failCount of $total | aborted=$aborted ===="

if ($aborted) { exit 2 }
if ($failCount -gt 0) { exit 1 }
exit 0
