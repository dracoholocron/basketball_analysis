<#
.SYNOPSIS
    Deploy the Basketball Analytics Platform via SSH on the Windows + Docker Desktop + WSL2 server.

.DESCRIPTION
    1. Pulls latest code from git
    2. Builds and recreates Docker Compose services (prod profile)
    3. Runs Alembic migrations inside the `api` container
    4. Runs smoke tests

.PARAMETER Profile
    Docker Compose profile to activate: 'dev' or 'prod' (default: prod)

.PARAMETER SkipPull
    Skip `git pull` (useful for local testing)

.EXAMPLE
    .\scripts\deploy.ps1
    .\scripts\deploy.ps1 -Profile dev
#>

param(
    [string]$Profile = "prod",
    [switch]$SkipPull
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "=== Basketball Analytics Deployment ===" -ForegroundColor Cyan
Write-Host "Profile : $Profile"
Write-Host "Repo    : $RepoRoot"
Write-Host ""

# ── Step 0: Git pull ──────────────────────────────────────────────────────────
if (-not $SkipPull) {
    Write-Host "[1/5] Pulling latest code…" -ForegroundColor Yellow
    Push-Location $RepoRoot
    git pull --ff-only
    Pop-Location
} else {
    Write-Host "[1/5] Skipping git pull (--SkipPull)" -ForegroundColor DarkGray
}

# ── Step 1: Copy .env ─────────────────────────────────────────────────────────
Write-Host "[2/5] Checking .env file…" -ForegroundColor Yellow
if (-not (Test-Path "$RepoRoot\.env")) {
    Write-Warning ".env file not found! Copying from .env.example — edit it before proceeding."
    Copy-Item "$RepoRoot\.env.example" "$RepoRoot\.env"
    Write-Error "Please edit $RepoRoot\.env with your secrets and re-run the script."
}

# ── Step 2: Build + start services ────────────────────────────────────────────
Write-Host "[3/5] Building and starting services (profile: $Profile)…" -ForegroundColor Yellow
Push-Location $RepoRoot
docker compose --profile $Profile up -d --build --remove-orphans
Pop-Location

# ── Step 3: Wait for API to be healthy ────────────────────────────────────────
Write-Host "[4/5] Waiting for API to be healthy…" -ForegroundColor Yellow
$maxWait = 120
$waited = 0
do {
    Start-Sleep -Seconds 5
    $waited += 5
    $health = docker inspect --format "{{.State.Health.Status}}" basketball_analysis-api-1 2>$null
    Write-Host "  api health: $health (${waited}s elapsed)"
} until ($health -eq "healthy" -or $waited -ge $maxWait)

if ($health -ne "healthy") {
    Write-Error "API did not become healthy within ${maxWait}s. Check logs: docker compose logs api"
}

# ── Step 4: Run Alembic migrations ────────────────────────────────────────────
Write-Host "[4b/5] Running database migrations…" -ForegroundColor Yellow
docker compose exec api alembic upgrade head

# ── Step 5: Smoke tests ───────────────────────────────────────────────────────
Write-Host "[5/5] Running smoke tests…" -ForegroundColor Yellow
docker compose exec api python -m pytest tests/smoke -v --tb=short

Write-Host ""
Write-Host "=== Deployment complete! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Services:"
Write-Host "  API          http://localhost:8000/docs"
Write-Host "  Frontend     http://localhost:3000  (prod profile)"
Write-Host "  MinIO        http://localhost:9001  (console)"
Write-Host ""
Write-Host "To follow logs:  docker compose logs -f"
Write-Host "To stop:         docker compose --profile $Profile down"
