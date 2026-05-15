<#
.SYNOPSIS
    Copy trained .pt models from basketball_analysis/models/ into the running
    worker-gpu container volume and restart the worker.

.DESCRIPTION
    After running train_models.ps1 or build_dummy_models.ps1, call this script
    to hot-deploy models into the worker without rebuilding the Docker image.

.EXAMPLE
    .\scripts\deploy_models.ps1

.EXAMPLE
    # Deploy a single model
    .\scripts\deploy_models.ps1 -Models player_detector

.EXAMPLE
    # Also set BA_DUMMY_MODELS to false (real models)
    .\scripts\deploy_models.ps1 -DisableDummyMode
#>

param(
    [string[]]$Models = @("player_detector", "ball_detector_model", "court_keypoint_detector"),
    [switch]$DisableDummyMode,
    [string]$ContainerName = "basketball_analysis-worker-gpu-1",
    [string]$ModelsDir = "$PSScriptRoot\..\basketball_analysis\models"
)

$ModelsDir = [System.IO.Path]::GetFullPath($ModelsDir)

Write-Host "Deploying models to container: $ContainerName"
Write-Host "Models source: $ModelsDir"
Write-Host ""

# Check container is running
$containerStatus = docker inspect $ContainerName --format "{{.State.Status}}" 2>&1
if ($LASTEXITCODE -ne 0 -or $containerStatus -ne "running") {
    Write-Error "Container $ContainerName is not running. Start the stack first: docker compose --profile dev up -d"
    exit 1
}

$success = 0
foreach ($modelName in $Models) {
    $srcPath = Join-Path $ModelsDir "${modelName}.pt"
    if (-not (Test-Path $srcPath)) {
        Write-Warning "  Not found: $srcPath — skipping"
        continue
    }
    $sizeMB = [math]::Round((Get-Item $srcPath).Length / 1MB, 1)
    Write-Host "  Copying ${modelName}.pt (${sizeMB} MB)..."
    docker cp $srcPath "${ContainerName}:/app/engine/models/${modelName}.pt" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    OK"
        $success++
    } else {
        Write-Warning "    FAILED to copy ${modelName}.pt"
    }
}

Write-Host ""
Write-Host "$success/$($Models.Count) model(s) deployed."

if ($DisableDummyMode) {
    Write-Host ""
    Write-Host "Setting BA_DUMMY_MODELS=false in .env..."
    $envFile = [System.IO.Path]::GetFullPath("$PSScriptRoot\..\.env")
    if (Test-Path $envFile) {
        $content = Get-Content $envFile -Raw
        if ($content -match "BA_DUMMY_MODELS") {
            $content = $content -replace "BA_DUMMY_MODELS=.*", "BA_DUMMY_MODELS=false"
        } else {
            $content += "`nBA_DUMMY_MODELS=false`n"
        }
        Set-Content -Path $envFile -Value $content -NoNewline
        Write-Host "  Updated .env"
    } else {
        Write-Warning "  .env not found at $envFile"
    }
}

Write-Host ""
Write-Host "Restarting worker-gpu..."
docker compose restart worker-gpu 2>&1 | Out-Null
Start-Sleep 3
$status = docker inspect $ContainerName --format "{{.State.Status}}" 2>&1
Write-Host "  Worker status: $status"
Write-Host ""
Write-Host "Done. The worker will now use the deployed models."
Write-Host ""
Write-Host "Run the benchmark to record real model performance:"
Write-Host "  python bench/run_bench.py --player_model basketball_analysis/models/player_detector.pt --ball_model basketball_analysis/models/ball_detector_model.pt --court_model basketball_analysis/models/court_keypoint_detector.pt --n_frames 200 --batch_size 8 --update-baseline"
