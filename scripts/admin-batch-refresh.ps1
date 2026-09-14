<#
.SYNOPSIS
    Refresh market data and/or generate AI reports for saved watchlist tickers.

.DESCRIPTION
    The default mode runs the selected operations for every ticker returned by
    stocks:portfolio. Use -Auto to make the run resumable and read each selected
    ticker's persisted timestamp from the chosen development or production
    deployment. It skips an operation whose persisted update is less than
    -IntervalHours old (24 hours by default).
    Use -Force when an automatic run must refresh a ticker before that interval;
    -Force does not bypass the production confirmation safeguard.

    This script calls the same Convex functions as the local Admin page. It is
    intentionally sequential by default so provider APIs and Convex writes are
    not overwhelmed. Use -ThrottleSeconds for an additional pause between
    operations.

.EXAMPLE
    pwsh -File .\scripts\admin-batch-refresh.ps1 -DryRun

.EXAMPLE
    pwsh -File .\scripts\admin-batch-refresh.ps1 -Auto -ReportPath .\logs\admin-batch.json

.EXAMPLE
    pwsh -File .\scripts\admin-batch-refresh.ps1 -Ticker NVDA,MSFT -Operation both -Force

.EXAMPLE
    pwsh -File .\scripts\admin-batch-refresh.ps1 -Target production -ConfirmProduction -Auto
#>

[CmdletBinding()]
param(
    [ValidateSet("development", "production")]
    [string]$Target = "development",

    [ValidateSet("both", "syncTicker", "generateAiReport")]
    [string]$Operation = "both",

    [Alias("Tickers")]
    [string[]]$Ticker = @(),

    [string]$Watchlist,

    [ValidateRange(0, 10000)]
    [int]$Limit = 0,

    [switch]$Auto,

    [switch]$Force,

    [ValidateRange(1, 720)]
    [int]$IntervalHours = 24,

    [ValidateRange(0, 86400)]
    [int]$ThrottleSeconds = 0,

    [switch]$DryRun,

    [switch]$ContinueOnError,

    [switch]$ConfirmProduction,

    [string]$NodePath,

    [string]$ConvexCliPath,

    [string]$ReportPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script:Deployment = if ($Target -eq "production") { "prod" } else { "dev" }

if ($Target -eq "production" -and -not $ConfirmProduction) {
    throw "Production changes public data. Re-run with -ConfirmProduction after reviewing the selected options."
}

if (-not $NodePath) {
    $nodeCommand = Get-Command node -ErrorAction Stop
    $NodePath = $nodeCommand.Source
}
if (-not (Test-Path -LiteralPath $NodePath -PathType Leaf)) {
    throw "Node executable not found: $NodePath"
}
$script:NodePath = (Resolve-Path -LiteralPath $NodePath).Path

if (-not $ConvexCliPath) {
    $ConvexCliPath = Join-Path $script:RepoRoot "node_modules\convex\dist\cli.bundle.cjs"
}
if (-not (Test-Path -LiteralPath $ConvexCliPath -PathType Leaf)) {
    throw "Convex CLI not found: $ConvexCliPath"
}
$script:ConvexCliPath = (Resolve-Path -LiteralPath $ConvexCliPath).Path

function ConvertTo-CompactJson {
    param([Parameter(Mandatory)]$Value)

    return ($Value | ConvertTo-Json -Compress -Depth 50)
}

function Remove-ConsoleAnsi {
    param([Parameter(Mandatory)][string]$Value)

    return [regex]::Replace($Value, "`e\[[0-?]*[ -/]*[@-~]", "")
}

function Invoke-ConvexQuery {
    param(
        [Parameter(Mandatory)][string]$FunctionName,
        [Parameter(Mandatory)]$Arguments
    )

    $argumentsJson = ConvertTo-CompactJson $Arguments
    $cliArguments = @(
        $script:ConvexCliPath,
        "run",
        $FunctionName,
        $argumentsJson,
        "--deployment",
        $script:Deployment,
        "--typecheck",
        "disable",
        "--codegen",
        "disable"
    )

    $rawOutput = & $script:NodePath @cliArguments 2>&1
    $exitCode = $LASTEXITCODE
    $output = (($rawOutput | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine).Trim()
    $output = Remove-ConsoleAnsi $output

    if ($exitCode -ne 0) {
        throw "Convex $FunctionName failed (exit $exitCode): $output"
    }

    if (-not $output) {
        return $null
    }

    try {
        return ($output | ConvertFrom-Json -Depth 100)
    } catch {
        throw "Convex $FunctionName returned invalid JSON: $output"
    }
}

function Normalize-Ticker {
    param([Parameter(Mandatory)][string]$Value)

    $normalized = $Value.Trim().ToUpperInvariant()
    if ($normalized -notmatch "^[A-Z0-9][A-Z0-9.-]{0,14}$") {
        throw "Invalid ticker '$Value'. Use letters, numbers, dots, or hyphens only."
    }
    return $normalized
}

function Get-PortfolioRows {
    $rawRows = @(Invoke-ConvexQuery -FunctionName "stocks:portfolio" -Arguments @{})
    $byTicker = @{}

    foreach ($row in $rawRows) {
        if ($null -eq $row -or -not $row.ticker) { continue }
        $normalized = Normalize-Ticker ([string]$row.ticker)
        if ($byTicker.ContainsKey($normalized)) { continue }

        $companyName = $null
        if ($row.stock -and $row.stock.companyName) {
            $companyName = [string]$row.stock.companyName
        }

        $byTicker[$normalized] = [pscustomobject]@{
            Ticker      = $normalized
            ListName    = if ($row.listName) { [string]$row.listName } else { "Watchlist" }
            CompanyName = $companyName
        }
    }

    return @($byTicker.Values | Sort-Object Ticker)
}

function Convert-UnixMilliseconds {
    param($Value)

    if ($null -eq $Value) { return $null }
    try {
        return [DateTimeOffset]::FromUnixTimeMilliseconds([int64]$Value)
    } catch {
        return $null
    }
}

function Get-StatusRows {
    param([Parameter(Mandatory)][object[]]$SelectedRows)

    # Read each selected ticker from the requested deployment. Snapshot.syncedAt
    # is the market quote's timestamp, which may be Friday's close over a
    # weekend; _creationTime is the persisted date/time of the actual sync.
    $statusRows = foreach ($selected in $SelectedRows) {
        try {
            $bundle = Invoke-ConvexQuery -FunctionName "stocks:researchBundle" -Arguments @{ ticker = $selected.Ticker }
            $latestSnapshot = if ($bundle.snapshots -and $bundle.snapshots.Count -gt 0) { $bundle.snapshots[0] } else { $null }
            [pscustomobject]@{
                ticker        = $selected.Ticker
                marketDataAt  = if ($latestSnapshot) { $latestSnapshot._creationTime } elseif ($bundle.stock) { $bundle.stock._creationTime } else { $null }
                aiReportAt    = if ($bundle.aiReport) { $bundle.aiReport.generatedAt } else { $null }
            }
        } catch {
            throw "Could not read the $script:Deployment refresh status for $($selected.Ticker): $($_.Exception.Message)"
        }
    }
    return @($statusRows)
}

function Test-FreshTimestamp {
    param($Value)

    $timestamp = Convert-UnixMilliseconds $Value
    if ($null -eq $timestamp) { return $false }
    return (([DateTimeOffset]::UtcNow - $timestamp).TotalHours -lt $IntervalHours)
}

function Format-PersistedTimestamp {
    param($Value)

    $timestamp = Convert-UnixMilliseconds $Value
    if ($null -eq $timestamp) { return "not available" }
    return $timestamp.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss zzz")
}

function Get-OperationSteps {
    if ($Operation -eq "syncTicker") { return @("syncTicker") }
    if ($Operation -eq "generateAiReport") { return @("generateAiReport") }
    return @("syncTicker", "generateAiReport")
}

$portfolioRows = Get-PortfolioRows
if ($portfolioRows.Count -eq 0) {
    throw "No saved watchlist tickers were returned by stocks:portfolio on $script:Deployment."
}

$requestedTickers = @{}
foreach ($tickerValue in $Ticker) {
    foreach ($part in ($tickerValue -split ",")) {
        if ($part.Trim()) {
            $normalized = Normalize-Ticker $part
            $requestedTickers[$normalized] = $true
        }
    }
}

$selectedRows = @(
    $portfolioRows | Where-Object {
        ($requestedTickers.Count -eq 0 -or $requestedTickers.ContainsKey($_.Ticker)) -and
        (-not $Watchlist -or $_.ListName -ieq $Watchlist)
    }
)
if ($Limit -gt 0) {
    $selectedRows = @($selectedRows | Select-Object -First $Limit)
}
if ($selectedRows.Count -eq 0) {
    throw "No tickers matched the requested filters."
}

$statusByTicker = @{}
if ($Auto -and -not $Force) {
    foreach ($status in (Get-StatusRows -SelectedRows $selectedRows)) {
        if ($status -and $status.ticker) {
            $statusByTicker[(Normalize-Ticker ([string]$status.ticker))] = $status
        }
    }
}

$steps = Get-OperationSteps
$plan = foreach ($row in $selectedRows) {
    $status = if ($statusByTicker.ContainsKey($row.Ticker)) { $statusByTicker[$row.Ticker] } else { $null }
    $planned = [System.Collections.Generic.List[string]]::new()
    $skipped = [System.Collections.Generic.List[string]]::new()
    $marketDataAt = if ($null -ne $status) { $status.marketDataAt } else { $null }
    $aiReportAt = if ($null -ne $status) { $status.aiReportAt } else { $null }

    if ($Operation -eq "both" -and $Auto -and -not $Force) {
        $syncFresh = Test-FreshTimestamp $marketDataAt
        $reportFresh = Test-FreshTimestamp $aiReportAt

        if ($syncFresh -and $reportFresh) {
            $skipped.Add("syncTicker")
            $skipped.Add("generateAiReport")
        } elseif ($syncFresh) {
            $skipped.Add("syncTicker")
            $planned.Add("generateAiReport")
        } else {
            # A new market-data sync invalidates the report's freshness, so the
            # two operations stay together when the sync is due.
            $planned.Add("syncTicker")
            $planned.Add("generateAiReport")
        }
    } else {
        foreach ($step in $steps) {
            $timestamp = if ($null -eq $status) {
                $null
            } elseif ($step -eq "syncTicker") {
                $status.marketDataAt
            } else {
                $status.aiReportAt
            }
            if ($Auto -and -not $Force -and (Test-FreshTimestamp $timestamp)) {
                $skipped.Add($step)
            } else {
                $planned.Add($step)
            }
        }
    }

    [pscustomobject]@{
        Ticker       = $row.Ticker
        CompanyName  = $row.CompanyName
        ListName     = $row.ListName
        MarketDataAt = $marketDataAt
        AiReportAt   = $aiReportAt
        Steps        = @($planned)
        Skipped      = @($skipped)
    }
}

Write-Host "Target: $Target ($script:Deployment)"
Write-Host "Operation: $Operation | Auto: $Auto | Force: $Force | Interval: ${IntervalHours}h"
Write-Host "Selected tickers: $($selectedRows.Count)"
if ($Auto -and -not $Force) {
    Write-Host "Freshness source: persisted $script:Deployment snapshot and AI-report timestamps."
}
if ($DryRun) { Write-Host "Mode: DRY RUN" -ForegroundColor Yellow }

$results = [System.Collections.Generic.List[object]]::new()
$startedAt = [DateTimeOffset]::UtcNow
$summary = [pscustomobject]@{
    target = $Target
    deployment = $script:Deployment
    operation = $Operation
    auto = [bool]$Auto
    force = [bool]$Force
    intervalHours = $IntervalHours
    dryRun = [bool]$DryRun
    status = "running"
    startedAtUtc = $startedAt.ToString("o")
    completedAtUtc = $null
    currentTicker = $null
    currentOperation = $null
    selectedTickers = $selectedRows.Count
    results = $results
}

function Save-BatchReport {
    if (-not $ReportPath) { return }

    $reportDirectory = Split-Path -Parent $ReportPath
    if ($reportDirectory -and -not (Test-Path -LiteralPath $reportDirectory)) {
        New-Item -ItemType Directory -Path $reportDirectory -Force | Out-Null
    }

    $temporaryPath = "$ReportPath.partial"
    $summary | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $temporaryPath -Encoding utf8
    Move-Item -LiteralPath $temporaryPath -Destination $ReportPath -Force
}

# Create the report before any write operation, then update it after every
# completed, skipped, or failed step. Interrupting a long AI generation will
# therefore leave a usable report showing the last in-progress operation.
Save-BatchReport

foreach ($item in $plan) {
    $result = [pscustomobject]@{
        ticker = $item.Ticker
        listName = $item.ListName
        status = "running"
        operations = [System.Collections.Generic.List[string]]::new()
        skippedOperations = @($item.Skipped)
        currentOperation = $null
        marketDataUpdatedAt = $item.MarketDataAt
        marketDataUpdatedAtLocal = Format-PersistedTimestamp $item.MarketDataAt
        aiReportUpdatedAt = $item.AiReportAt
        aiReportUpdatedAtLocal = Format-PersistedTimestamp $item.AiReportAt
        error = $null
        reason = $null
    }
    $results.Add($result)
    $summary.currentTicker = $item.Ticker
    $summary.currentOperation = $null

    if ($item.Skipped.Count -gt 0) {
        Write-Host "SKIP $($item.Ticker): $($item.Skipped -join ', ') is inside the $IntervalHours-hour auto interval (market: $(Format-PersistedTimestamp $item.MarketDataAt); AI: $(Format-PersistedTimestamp $item.AiReportAt))." -ForegroundColor DarkYellow
    }

    if ($item.Steps.Count -eq 0) {
        $result.status = "skipped"
        $result.reason = "All selected operations are inside the auto interval."
        Save-BatchReport
        continue
    }

    $failed = $false
    foreach ($step in $item.Steps) {
        $label = if ($step -eq "syncTicker") { "Sync market data" } else { "Generate AI report" }
        $result.currentOperation = $step
        $summary.currentOperation = $step
        Save-BatchReport
        if ($DryRun) {
            Write-Host "PLAN $($item.Ticker): $label" -ForegroundColor Cyan
            $result.operations.Add($step)
            continue
        }

        Write-Host "RUN  $($item.Ticker): $label"
        try {
            $arguments = @{ ticker = $item.Ticker }
            [void](Invoke-ConvexQuery -FunctionName $(if ($step -eq "syncTicker") { "marketData:syncTicker" } else { "aiResearch:generateReport" }) -Arguments $arguments)
            $result.operations.Add($step)
            $result.currentOperation = $null
            $summary.currentOperation = $null
            Save-BatchReport
            Write-Host "DONE $($item.Ticker): $label" -ForegroundColor Green
        } catch {
            $failed = $true
            $errorMessage = $_.Exception.Message
            $result.error = $errorMessage
            $result.currentOperation = $null
            $result.status = "failed"
            $summary.currentOperation = $null
            Save-BatchReport
            Write-Host "FAIL $($item.Ticker): $label - $errorMessage" -ForegroundColor Red
            if (-not $ContinueOnError) {
                $summary.status = "failed"
                $summary.completedAtUtc = [DateTimeOffset]::UtcNow.ToString("o")
                Save-BatchReport
                throw
            }
            break
        }

        if ($ThrottleSeconds -gt 0) { Start-Sleep -Seconds $ThrottleSeconds }
    }

    if (-not $failed) {
        $result.status = if ($DryRun) { "planned" } else { "completed" }
    }
    $result.currentOperation = $null
    $summary.currentOperation = $null
    Save-BatchReport
}

$summary.status = if (@($results | Where-Object status -eq "failed").Count -gt 0) { "completed_with_errors" } else { "completed" }
$summary.completedAtUtc = [DateTimeOffset]::UtcNow.ToString("o")
$summary.currentTicker = $null
$summary.currentOperation = $null
Save-BatchReport
if ($ReportPath) { Write-Host "Report written to $ReportPath" }

$completedCount = @($results | Where-Object status -eq "completed").Count
$plannedCount = @($results | Where-Object status -eq "planned").Count
$skippedCount = @($results | Where-Object status -eq "skipped").Count
$failedCount = @($results | Where-Object status -eq "failed").Count
Write-Host "Summary: completed=$completedCount planned=$plannedCount skipped=$skippedCount failed=$failedCount"

if ($failedCount -gt 0) { exit 1 }
