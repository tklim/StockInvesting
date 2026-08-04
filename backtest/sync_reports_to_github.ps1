[CmdletBinding()]
param(
    [string]$Message = "Publish dashboard reports and chart assets",
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$reportsDir = Join-Path $repoRoot "backtest\outputs\reports"
$chartsDir = Join-Path $repoRoot "backtest\outputs\charts"
$siteDir = Join-Path $env:TEMP "stockinvesting-pages-site"
$publisher = Join-Path $repoRoot "backtest\publish_reports_site.py"
$launcher = Join-Path $PSScriptRoot "g.bat"

function Invoke-Git {
    param([Parameter(Mandatory)][string[]]$Arguments)
    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

function Get-RepositoryRelativePath {
    param([Parameter(Mandatory)][string]$Path)

    $rootWithSeparator = $repoRoot.TrimEnd('\') + '\'
    if (-not $Path.StartsWith($rootWithSeparator, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside the repository: $Path"
    }
    return $Path.Substring($rootWithSeparator.Length).Replace('\', '/')
}

Set-Location $repoRoot

Invoke-Git -Arguments @("status", "--short", "--branch")
if (-not $WhatIf) {
    Invoke-Git -Arguments @("fetch", "--all", "--prune")

    $divergence = (& git rev-list --left-right --count HEAD...origin/main).Trim().Split("`t")
    if ($LASTEXITCODE -ne 0 -or $divergence.Count -ne 2) {
        throw "Could not determine whether local main is aligned with origin/main."
    }
    if ([int]$divergence[1] -gt 0) {
        Invoke-Git -Arguments @("pull", "--ff-only")
    }
}

# This fails before staging if HTML contains a missing or unsafe chart reference.
& python $publisher --reports-dir $reportsDir --charts-dir $chartsDir --site-dir $siteDir
if ($LASTEXITCODE -ne 0) {
    throw "Report site validation failed; no files were staged or pushed."
}

$manifest = Get-Content (Join-Path $siteDir "chart-manifest.json") -Raw | ConvertFrom-Json
$reportPaths = Get-ChildItem $reportsDir -File -Recurse -Filter "*.html" |
    ForEach-Object { Get-RepositoryRelativePath $_.FullName }
$chartPaths = $manifest.charts |
    ForEach-Object { "backtest/outputs/charts/$_" }
$helperPaths = @(
    (Get-RepositoryRelativePath $launcher),
    (Get-RepositoryRelativePath $PSCommandPath)
)
$publishPaths = @($reportPaths + $chartPaths + $helperPaths)

if ($publishPaths.Count -eq 0) {
    throw "No HTML reports or chart assets were found to publish."
}

Write-Host "Validated $($reportPaths.Count) HTML reports and $($chartPaths.Count) referenced PNGs."
if ($WhatIf) {
    Write-Host "WhatIf: would stage only the validated report HTML, referenced PNGs, and sync helper."
    return
}

$alreadyStaged = @(& git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect files that were already staged."
}
$allowedPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$publishPaths | ForEach-Object { [void]$allowedPaths.Add($_) }
$unexpectedStaged = $alreadyStaged | Where-Object { -not $allowedPaths.Contains($_) }
if ($unexpectedStaged) {
    throw "Refusing to commit unrelated files already staged:`n$($unexpectedStaged -join "`n")"
}

$gitAddArguments = @("add", "--") + $publishPaths
Invoke-Git -Arguments $gitAddArguments
$staged = @(& git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect the staged publication files."
}
if ($staged.Count -eq 0) {
    Write-Host "No report or referenced-chart changes to publish."
    return
}

Write-Host "Staged $($staged.Count) publication files:"
$staged
& git diff --cached --check
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Generated HTML contains whitespace warnings; review the list above before rerunning if unexpected."
}

Invoke-Git -Arguments @("commit", "-m", $Message)
Invoke-Git -Arguments @("push", "origin", "main")

if (Get-Command gh -ErrorAction SilentlyContinue) {
    & gh workflow run publish-reports.yml --ref main
    if ($LASTEXITCODE -ne 0) {
        throw "The commit was pushed, but GitHub Pages workflow dispatch failed."
    }
    Write-Host "Pages deployment started. Check it with: gh run list --workflow publish-reports.yml --limit 1"
} else {
    Write-Warning "Commit pushed, but GitHub CLI was not found. Start publish-reports.yml manually in GitHub Actions."
}
