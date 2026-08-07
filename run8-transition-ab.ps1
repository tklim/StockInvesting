<#
.SYNOPSIS
    Staged 2x2 A/B of the offset-month transition algorithms at pop=8/gen=4
    (override with -Population/-Generations, e.g. 16/8 for H-016).

.DESCRIPTION
    Runs the transition-smoothing test matrix on JPM-3Y and MSFT-3Y at the
    1Y-lookback / 3M-offset cell (9 windows -> 8 transitions per run, the most
    boundaries any cell provides).

    Stage 1 (default): baseline vs grandfather, warm start OFF.
        Primary question: does the grandfather policy hold up at a tuning
        budget where the noise floor should finally be below the ~1.4-point
        effect H-013 measured?
    Stage 2 (-Stage2): the same two policies with warm start ON (fraction 0.5).
        Secondary: does warm start redeem itself at pop=8, and does it
        interact with grandfathering?

    Every (arm, seed) is one run_grid.ps1 invocation covering both funds, so
    the whole experiment is resume-safe: rerun this script after any
    interruption and completed combos are skipped. Policy, seed, warm-start
    setting and data-file hash are all part of the resume identity, so arms
    never satisfy each other and a data refresh mid-experiment forces re-runs
    instead of producing silently incomparable results.

    DO NOT refresh the data files while this is running -- JPM-3Y.csv and
    MSFT-3Y.csv are on the same vintage (2023-08-04 -> 2026-08-04) and every
    arm must trade exactly that series.

    Expected cost per run at pop=8/gen=4: ~35-50 min (extrapolated from 13 min
    at pop4/gen2 and 19 min at pop6/gen3 on this same cell). Stage 1 with the
    default 3 seeds = 12 runs, roughly 7-10 hours.

.EXAMPLE
    # Stage 1 overnight (12 runs):
    .\run8-transition-ab.ps1

.EXAMPLE
    # Quick look at what would run without launching anything:
    .\run8-transition-ab.ps1 -DryRun

.EXAMPLE
    # Stage 2 after reviewing Stage 1 (12 more runs):
    .\run8-transition-ab.ps1 -Stage2

.EXAMPLE
    # Shorter first pass: two seeds now, top up seed 2222 later for free.
    .\run8-transition-ab.ps1 -Seeds 999,1111

.EXAMPLE
    # H-016: double the search effort on the same six seeds/arms to see
    # whether training-score disagreement shrinks and whether live-result
    # spread shrinks. ~4x the pop=8/gen=4 cost (35-50 min) per run.
    .\run8-transition-ab.ps1 -Population 16 -Generations 8
#>
[CmdletBinding()]
param(
    [int[]]$Seeds = @(999, 1111, 2222),
    [int]$Population = 8,
    [int]$Generations = 4,
    [switch]$Stage2,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$runGrid  = Join-Path $repoRoot "run_grid.ps1"

if ($Stage2) {
    $arms = @(
        @{ Name = "warm-none";        TransitionPolicy = "none";        GaWarmStart = $true  },
        @{ Name = "warm-grandfather"; TransitionPolicy = "grandfather"; GaWarmStart = $true  }
    )
} else {
    $arms = @(
        @{ Name = "base-none";        TransitionPolicy = "none";        GaWarmStart = $false },
        @{ Name = "base-grandfather"; TransitionPolicy = "grandfather"; GaWarmStart = $false }
    )
}

# Seeds outermost so an interrupted experiment still yields complete A/B pairs
# for the seeds it finished: a pair within one seed is the unit of analysis
# (same seed + reuse-tuned-params => identical parameter schedules, so the
# policy is the only difference).
$failures = 0
foreach ($seed in $Seeds) {
    foreach ($arm in $arms) {
        $label = "$($arm.Name) seed=$seed"
        $args = @{
            Funds                 = "JPM,MSFT"
            DataSuffix            = "-3Y"
            LookbackYears         = 1
            OffsetMonths          = 3
            Population            = $Population
            Generations           = $Generations
            GaSearchPreset        = "grid"
            PriceColumn           = "Adj Close"
            GaSeed                = $seed
            TransitionPolicy      = $arm.TransitionPolicy
            # A multi-day experiment must still resume, so completed rows stay
            # reusable far beyond run_grid's 24h default. The data-file hash in
            # the resume key keeps this safe: only same-vintage rows match.
            CompletedMaxAgeHours  = 8760
            LogFile               = "ab$Population-$($arm.Name)-s$seed.log"
        }
        if ($arm.GaWarmStart) { $args["GaWarmStart"] = $true }
        if ($DryRun)          { $args["DryRun"] = $true }

        Write-Host "==== [$label] starting at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===="
        & $runGrid @args
        if ($LASTEXITCODE -ne 0) {
            $failures++
            Write-Host "==== [$label] finished with exit $LASTEXITCODE ===="
            if ($LASTEXITCODE -eq 2) {
                Write-Host "Aborting the experiment: run_grid stopped on repeated failures."
                exit 2
            }
        }
    }
}

if ($failures -gt 0) { exit 1 }
Write-Host "==== All arms complete. ===="
exit 0
