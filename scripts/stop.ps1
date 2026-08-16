<#
.SYNOPSIS
    Cleanly stop the Stage 3 backend + frontend started by start.ps1.

.DESCRIPTION
    Kills by PID file first (the precise path), then falls back to
    checking ports 8000/5173 directly -- so this cleans up correctly even
    if the servers were started the old manual way (two terminals, see
    RUNNING.md), not just via start.bat. Uses `taskkill /T` (tree-kill):
    `uvicorn --reload` and `npm run dev` both spawn child processes that
    Stop-Process on just the parent PID would leave orphaned.

    Fails soft throughout -- a missing or stale PID file is reported, not
    an error. This is a cleanup script; it should never itself need
    cleaning up after.
#>

$RepoRoot = Split-Path -Parent $PSScriptRoot
$RunDir = Join-Path $RepoRoot ".run"

function Stop-ByPidFile($pidFile, $label) {
    $path = Join-Path $RunDir $pidFile
    if (-not (Test-Path $path)) {
        Write-Host "$label`: no PID file found (not started via start.bat?)."
        return
    }
    $targetPid = (Get-Content $path -Raw).Trim()
    if ($targetPid -and (Get-Process -Id $targetPid -ErrorAction SilentlyContinue)) {
        Write-Host "Stopping $label (PID $targetPid)..."
        taskkill /PID $targetPid /T /F 2>$null | Out-Null
    } else {
        Write-Host "$label`: PID file present but process already gone."
    }
    Remove-Item $path -Force -ErrorAction SilentlyContinue
}

Stop-ByPidFile "backend.pid" "Backend"
Stop-ByPidFile "frontend.pid" "Frontend"

# Fallback: catch anything still listening on the known ports, in case the
# servers were started a different way than start.bat.
foreach ($port in 8000, 5173) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        Write-Host "Also stopping process still listening on port $port (PID $($c.OwningProcess))..."
        taskkill /PID $c.OwningProcess /T /F 2>$null | Out-Null
    }
}

Write-Host "Done."
