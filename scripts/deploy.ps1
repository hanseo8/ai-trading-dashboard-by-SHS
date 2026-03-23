param(
    [string]$Message = "",
    [switch]$IncludeStateFiles,
    [switch]$SkipValidation
)

$ErrorActionPreference = "Stop"

function Info($text) {
    Write-Host "[INFO] $text" -ForegroundColor Cyan
}

function Warn($text) {
    Write-Host "[WARN] $text" -ForegroundColor Yellow
}

function Fail($text) {
    Write-Host "[ERR ] $text" -ForegroundColor Red
    exit 1
}

try {
    $repoRoot = (git rev-parse --show-toplevel).Trim()
} catch {
    Fail "Git repository not found."
}

Set-Location $repoRoot

$branch = (git branch --show-current).Trim()
if (-not $branch) {
    Fail "Could not detect current branch."
}

Info "Repository: $repoRoot"
Info "Branch: $branch"

if (-not $SkipValidation) {
    Info "Running syntax check (app.py)..."
    python -m py_compile "app.py"
}

if (-not $Message) {
    $Message = "deploy: streamlit update $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
}

Info "Staging changes..."
git add -A

# Exclude runtime/state files by default to keep commits clean.
if (-not $IncludeStateFiles) {
    git reset -- "portfolio_*.json" 2>$null
    git reset -- "__pycache__" 2>$null
    git reset -- "*.pyc" 2>$null
}

$staged = git diff --cached --name-only
if (-not $staged) {
    Warn "No staged changes to commit."
    exit 0
}

Info "Committing..."
git commit -m "$Message"

Info "Pushing to origin/$branch ..."
git push origin $branch

Info "Done. Streamlit Cloud will auto-redeploy shortly."
