<#
.SYNOPSIS
    Start the Stage 3 backend + frontend, detached, and open the browser.

.DESCRIPTION
    The real logic behind the double-click `start.bat` at the repo root.
    Written in PowerShell (not plain batch) because clean PID capture
    (Start-Process -PassThru) and later, precise process-tree shutdown
    need it -- see stop.ps1.

    Does NOT do first-time setup (venv creation, npm install, .env,
    curriculum ingestion) -- see RUNNING.md's "One-time setup". This script
    fails loud and early if that hasn't happened yet, rather than trying
    to paper over it.

    Safe to run again while already running: existing PID files are
    checked first, so this won't spawn a second pair of servers on top of
    a still-running pair.
#>

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$LogsDir = Join-Path $RepoRoot "logs"
$RunDir = Join-Path $RepoRoot ".run"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

$BackendPidFile = Join-Path $RunDir "backend.pid"
$FrontendPidFile = Join-Path $RunDir "frontend.pid"

function Test-ProcessAlive($pidFile) {
    if (-not (Test-Path $pidFile)) { return $false }
    $existingPid = (Get-Content $pidFile -Raw).Trim()
    if (-not $existingPid) { return $false }
    return [bool](Get-Process -Id $existingPid -ErrorAction SilentlyContinue)
}

if ((Test-ProcessAlive $BackendPidFile) -and (Test-ProcessAlive $FrontendPidFile)) {
    Write-Host "Stage 3 Tutor already appears to be running (PID files present)." -ForegroundColor Yellow
    Write-Host "Run stop.bat first if you want a clean restart." -ForegroundColor Yellow
    exit 0
}

# ---------------------------------------------------------------------------
# Pre-flight checks -- fail with a clear pointer, don't try to auto-fix.
# ---------------------------------------------------------------------------
# Prefer a project .venv if one exists (RUNNING.md's documented setup);
# fall back to whatever `python` resolves to on PATH otherwise (a global
# interpreter with the requirements installed directly is just as valid,
# and is in fact what this machine actually uses day-to-day).
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $onPath = Get-Command python -ErrorAction SilentlyContinue
    if (-not $onPath) {
        Write-Host "No .venv found and no 'python' on PATH." -ForegroundColor Red
        Write-Host "Run the one-time setup in RUNNING.md first (create a venv or install requirements.txt globally)." -ForegroundColor Red
        exit 1
    }
    $VenvPython = $onPath.Source
}

$NodeModules = Join-Path $RepoRoot "frontend\node_modules"
if (-not (Test-Path $NodeModules)) {
    Write-Host "frontend\node_modules not found." -ForegroundColor Red
    Write-Host "Run 'npm install' in frontend/ first (see RUNNING.md's one-time setup)." -ForegroundColor Red
    exit 1
}

$ChromaDir = Join-Path $RepoRoot "data\chroma"
if ((-not (Test-Path $ChromaDir)) -or ((Get-ChildItem $ChromaDir -ErrorAction SilentlyContinue | Measure-Object).Count -eq 0)) {
    Write-Host "Note: data\chroma looks empty -- no curriculum has been ingested yet." -ForegroundColor Yellow
    Write-Host "The tutor will start, but retrieval will return nothing until 'python -m stage3.ingest --source ...' has been run (see README.md)." -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# Start backend
# ---------------------------------------------------------------------------
Write-Host "Starting backend..."
$backendProc = Start-Process -FilePath $VenvPython `
    -ArgumentList "-m", "uvicorn", "stage3.api.main:app", "--reload" `
    -WorkingDirectory $RepoRoot `
    -RedirectStandardOutput (Join-Path $LogsDir "backend.log") `
    -RedirectStandardError (Join-Path $LogsDir "backend.err.log") `
    -WindowStyle Hidden -PassThru
$backendProc.Id | Out-File -FilePath $BackendPidFile -Encoding ascii

# ---------------------------------------------------------------------------
# Start frontend
# ---------------------------------------------------------------------------
Write-Host "Starting frontend..."
$frontendProc = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev" `
    -WorkingDirectory (Join-Path $RepoRoot "frontend") `
    -RedirectStandardOutput (Join-Path $LogsDir "frontend.log") `
    -RedirectStandardError (Join-Path $LogsDir "frontend.err.log") `
    -WindowStyle Hidden -PassThru
$frontendProc.Id | Out-File -FilePath $FrontendPidFile -Encoding ascii

# ---------------------------------------------------------------------------
# Wait for both to come up
# ---------------------------------------------------------------------------
Write-Host "Waiting for backend (first load can take ~20-30s -- loading the embedding model)..."
$backendReady = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $backendReady = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}
if (-not $backendReady) {
    Write-Host "Backend did not respond within 2 minutes -- check logs\backend.log / backend.err.log" -ForegroundColor Yellow
}

Write-Host "Waiting for frontend..."
$frontendReady = $false
for ($i = 0; $i -lt 20; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:5173" -TimeoutSec 2 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $frontendReady = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
}
if (-not $frontendReady) {
    Write-Host "Frontend did not respond within 20s -- check logs\frontend.log / frontend.err.log" -ForegroundColor Yellow
}

if ($backendReady -and $frontendReady) {
    Start-Process "http://localhost:5173"
}

Write-Host ""
Write-Host "Stage 3 Tutor:" -ForegroundColor Green
Write-Host "  Backend  (PID $($backendProc.Id)) -> http://127.0.0.1:8000  (logs\backend.log)"
Write-Host "  Frontend (PID $($frontendProc.Id)) -> http://localhost:5173  (logs\frontend.log)"
Write-Host "Run stop.bat to shut both down cleanly."
