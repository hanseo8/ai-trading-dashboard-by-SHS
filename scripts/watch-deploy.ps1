param(
    [int]$DebounceSeconds = 8,
    [switch]$IncludeStateFiles
)

$ErrorActionPreference = "Stop"

try {
    $repoRoot = (git rev-parse --show-toplevel).Trim()
} catch {
    Write-Host "[ERR ] Git repository not found." -ForegroundColor Red
    exit 1
}

Set-Location $repoRoot
$deployScript = Join-Path $repoRoot "scripts/deploy.ps1"

if (-not (Test-Path $deployScript)) {
    Write-Host "[ERR ] scripts/deploy.ps1 not found." -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Watching for changes in: $repoRoot" -ForegroundColor Cyan
Write-Host "[INFO] Debounce: $DebounceSeconds sec" -ForegroundColor Cyan
Write-Host "[INFO] Press Ctrl+C to stop." -ForegroundColor Cyan

$changed = $false
$lastChange = Get-Date

$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $repoRoot
$watcher.IncludeSubdirectories = $true
$watcher.EnableRaisingEvents = $true
$watcher.NotifyFilter = [IO.NotifyFilters]'FileName, LastWrite, CreationTime'

$handler = {
    param($sender, $eventArgs)
    $path = $eventArgs.FullPath
    if ($path -match "\\.git\\") { return }
    if ($path -match "__pycache__") { return }
    if ($path -match "\.pyc$") { return }
    if ($path -match "portfolio_.*\.json$") { return }

    $script:changed = $true
    $script:lastChange = Get-Date
    Write-Host "[INFO] Change detected: $($eventArgs.ChangeType) $path" -ForegroundColor DarkCyan
}

$createdReg = Register-ObjectEvent $watcher Created -Action $handler
$changedReg = Register-ObjectEvent $watcher Changed -Action $handler
$renamedReg = Register-ObjectEvent $watcher Renamed -Action $handler
$deletedReg = Register-ObjectEvent $watcher Deleted -Action $handler

try {
    while ($true) {
        Start-Sleep -Seconds 1
        if (-not $changed) { continue }

        $age = (Get-Date) - $lastChange
        if ($age.TotalSeconds -lt $DebounceSeconds) { continue }

        $changed = $false
        $msg = "deploy(auto): $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        Write-Host "[INFO] Running auto deploy..." -ForegroundColor Green

        if ($IncludeStateFiles) {
            & $deployScript -Message $msg -IncludeStateFiles
        } else {
            & $deployScript -Message $msg
        }
    }
}
finally {
    Unregister-Event -SourceIdentifier $createdReg.Name
    Unregister-Event -SourceIdentifier $changedReg.Name
    Unregister-Event -SourceIdentifier $renamedReg.Name
    Unregister-Event -SourceIdentifier $deletedReg.Name
    $watcher.Dispose()
}
