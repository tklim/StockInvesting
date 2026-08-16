[CmdletBinding()]
param(
  [switch]$Commit,
  [switch]$Push,
  [string]$Message = "Sync public app updates"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($Push -and -not $Commit) {
  throw "-Push requires -Commit. Run without switches first to review the exact file set."
}

$syncPaths = @(
  "convex/stocks.ts",
  "local-admin/plugin.ts",
  "src/App.tsx",
  "src/styles.css",
  "src/admin/main.tsx",
  "src/admin/operations.ts",
  "src/admin/operations.test.ts",
  "src/admin/styles.css",
  "src/admin/ManagementPanel.tsx",
  "src/admin/elapsed.ts",
  "src/admin/elapsed.test.ts",
  "src/admin/management.ts",
  "src/admin/watchlist.ts",
  "src/admin/watchlist.test.ts",
  "sync-public-app.cmd",
  "sync-public-app.ps1"
)

function Invoke-Git {
  param([Parameter(Mandatory = $true)][string[]]$GitArgs)
  & git @GitArgs
  if ($LASTEXITCODE -ne 0) {
    throw "git $($GitArgs -join ' ') failed."
  }
}

function Invoke-NodeTool {
  param([string[]]$Arguments)
  $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
  $nodePath = if ($nodeCommand) { $nodeCommand.Source } else { "C:\nvm4w\nodejs\node.exe" }
  if (-not (Test-Path -LiteralPath $nodePath)) {
    throw "Node.js was not found. Install Node.js or make it available on PATH."
  }

  & $nodePath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Node verification command failed: $($Arguments -join ' ')"
  }
}

Write-Host "Reviewing origin/main..." -ForegroundColor Cyan
Invoke-Git -GitArgs @("fetch", "--all", "--prune")
$divergence = @(git rev-list --left-right --count main...origin/main)
if ($LASTEXITCODE -ne 0 -or $divergence.Count -ne 1) {
  throw "Unable to determine local/remote divergence."
}
$ahead, $behind = $divergence[0].Trim().Split("`t")
Write-Host "main vs origin/main: $ahead ahead, $behind behind"
if ([int]$behind -gt 0) {
  throw "origin/main has commits not present locally. Resolve that first; this script will not pull or merge."
}

$status = @(git status --porcelain)
if ($LASTEXITCODE -ne 0) {
  throw "Unable to read Git status."
}
$trackedCount = @($status | Where-Object { $_ -notmatch '^\?\? ' }).Count
$untrackedCount = @($status | Where-Object { $_ -match '^\?\? ' }).Count
Write-Host "Working tree: $trackedCount modified/deleted, $untrackedCount untracked entries."

Write-Host "`nCandidate public-app files:" -ForegroundColor Cyan
Invoke-Git -GitArgs (@("status", "--short", "--") + $syncPaths)

Write-Host "`nCandidate diff summary:" -ForegroundColor Cyan
Invoke-Git -GitArgs (@("diff", "--stat", "--") + $syncPaths)
Invoke-Git -GitArgs (@("diff", "--check", "--") + $syncPaths)

if (-not $Commit) {
  Write-Host "`nDry run complete. Nothing was staged, committed, or pushed." -ForegroundColor Green
  Write-Host "To commit: .\sync-public-app.ps1 -Commit"
  Write-Host "To commit and push: .\sync-public-app.ps1 -Commit -Push -Message 'Describe the update'"
  exit 0
}

$alreadyStaged = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) {
  throw "Unable to inspect the Git staging area."
}
if ($alreadyStaged.Count -gt 0) {
  Write-Host "Existing staged files were left untouched:" -ForegroundColor Yellow
  $alreadyStaged | ForEach-Object { Write-Host "  $_" }
  throw "Refusing to mix this sync with an existing staging area."
}

Write-Host "`nStaging only the candidate public-app files..." -ForegroundColor Cyan
Invoke-Git -GitArgs (@("add", "-A", "--") + $syncPaths)
$staged = @(git diff --cached --name-only)
$unexpected = @($staged | Where-Object { $_ -notin $syncPaths })
if ($unexpected.Count -gt 0) {
  Write-Host "Unexpected staged files:" -ForegroundColor Red
  $unexpected | ForEach-Object { Write-Host "  $_" }
  throw "Refusing to commit files outside the public-app allowlist."
}
if ($staged.Count -eq 0) {
  Write-Host "No candidate changes to commit." -ForegroundColor Yellow
  exit 0
}

Invoke-Git -GitArgs @("diff", "--cached", "--check")

$credentialPattern = '(?i)(sk-[a-z0-9_-]{8,}|AKIA[0-9A-Z]{16}|ghp_[a-zA-Z0-9]{20,}|github_pat_[a-zA-Z0-9_]{20,})'
$credentialHits = Select-String -LiteralPath $staged -Pattern $credentialPattern
if ($credentialHits) {
  Write-Host "Potential credentials found in staged files:" -ForegroundColor Red
  $credentialHits | ForEach-Object { Write-Host "  $($_.Path):$($_.LineNumber)" }
  throw "Remove or rotate the credential before committing."
}

Write-Host "`nRunning tests and production build..." -ForegroundColor Cyan
Invoke-NodeTool @(".\node_modules\vitest\vitest.mjs", "run")
Invoke-NodeTool @(".\node_modules\typescript\bin\tsc", "-b", "--force", "--pretty", "false")
Invoke-NodeTool @(".\node_modules\vite\bin\vite.js", "build")

Write-Host "`nCreating commit..." -ForegroundColor Cyan
Invoke-Git -GitArgs @("commit", "-m", $Message)

if (-not $Push) {
  Write-Host "Commit created locally. Push later with: .\sync-public-app.ps1 -Commit -Push" -ForegroundColor Green
  exit 0
}

Write-Host "`nPushing main..." -ForegroundColor Cyan
Invoke-Git -GitArgs @("push", "origin", "main")
Invoke-Git -GitArgs @("fetch", "origin", "main")
$localHead = (git rev-parse HEAD).Trim()
$remoteHead = (git rev-parse origin/main).Trim()
if ($localHead -ne $remoteHead) {
  throw "Push finished but origin/main does not match local HEAD."
}

Write-Host "Safe sync complete. origin/main matches $localHead" -ForegroundColor Green
