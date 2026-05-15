<#
.SYNOPSIS
    Download YOLO model files (.pt) into the Docker named volume used by the worker.

.DESCRIPTION
    Models are too large for git. This script downloads them from a shared source
    (Google Drive, S3, or a local path) into the `models_data` volume.

    Set the BA_MODELS_SOURCE env var to one of:
      - A local Windows path:  "C:\models\"
      - An S3 URL:             "s3://your-bucket/models/"
      - A Google Drive folder: set BA_GDRIVE_FOLDER_ID

.EXAMPLE
    $env:BA_MODELS_SOURCE = "C:\Users\user\Downloads\basketball_models"
    .\scripts\fetch_models.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ModelsSource = $env:BA_MODELS_SOURCE
$GDriveFolderId = $env:BA_GDRIVE_FOLDER_ID

$ModelFiles = @(
    "player_detector.pt",
    "ball_detector_model.pt",
    "court_keypoint_detector.pt"
)

# ── Ensure temporary container for volume access ──────────────────────────────
Write-Host "Ensuring models Docker volume exists…" -ForegroundColor Cyan
docker volume create models_data | Out-Null

# ── Option 1: Copy from local path ────────────────────────────────────────────
if ($ModelsSource -and (Test-Path $ModelsSource)) {
    Write-Host "Copying models from local path: $ModelsSource" -ForegroundColor Yellow
    foreach ($model in $ModelFiles) {
        $src = Join-Path $ModelsSource $model
        if (Test-Path $src) {
            Write-Host "  Copying $model…"
            # Use a temp alpine container to write into the Docker volume
            $srcWsl = $src -replace "\\", "/" -replace "C:", "/mnt/c"
            docker run --rm `
                -v "${ModelsSource}:/src:ro" `
                -v "models_data:/dst" `
                alpine sh -c "cp /src/$model /dst/$model"
        } else {
            Write-Warning "  $model not found at $src — skipping"
        }
    }
    Write-Host "Done." -ForegroundColor Green
    exit 0
}

# ── Option 2: Download from S3 ────────────────────────────────────────────────
if ($ModelsSource -and $ModelsSource.StartsWith("s3://")) {
    Write-Host "Downloading models from S3: $ModelsSource" -ForegroundColor Yellow
    docker run --rm `
        -v "models_data:/models" `
        -e AWS_ACCESS_KEY_ID=$env:AWS_ACCESS_KEY_ID `
        -e AWS_SECRET_ACCESS_KEY=$env:AWS_SECRET_ACCESS_KEY `
        amazon/aws-cli s3 sync $ModelsSource /models/
    Write-Host "Done." -ForegroundColor Green
    exit 0
}

# ── Option 3: Download from Google Drive ──────────────────────────────────────
if ($GDriveFolderId) {
    Write-Host "Downloading models from Google Drive folder: $GDriveFolderId" -ForegroundColor Yellow
    Write-Warning "Requires gdown: pip install gdown"
    foreach ($model in $ModelFiles) {
        Write-Host "  NOTE: Add your file IDs to this script for model: $model"
    }
    Write-Error "Set BA_GDRIVE_FILE_IDS map in the script for each .pt file"
}

Write-Error @"
No model source configured. Set one of:
  - BA_MODELS_SOURCE = path to folder with .pt files
  - BA_MODELS_SOURCE = s3://bucket/prefix/
  - BA_GDRIVE_FOLDER_ID = Google Drive folder ID
"@
