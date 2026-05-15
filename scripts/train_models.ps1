<#
.SYNOPSIS
  Train the three basketball analysis models from Roboflow datasets
  and place the resulting best.pt files into basketball_analysis/models/.

.DESCRIPTION
  Track B (real models) training script.

  Models trained:
    1. Player detector  — workspace-5ujvu / basketball-players-fy4c2-vfsuv / v17
                          yolov5l6u.pt  100 epochs  batch 8   (~30-45 min on RTX 5070)
    2. Ball detector    — same dataset as above (dataset contains both classes)
                          yolov5l6u.pt  250 epochs             (~60-90 min on RTX 5070)
    3. Court keypoints  — fyp-3bwmg / reloc2-den7l / v1
                          yolov8x-pose.pt  500 epochs  batch 16  (~60-90 min on RTX 5070)

  Total expected time: ~3-4 hours on RTX 5070 12 GB.

.PREREQUISITES
  - Python venv activated with ultralytics + roboflow installed
  - ROBOFLOW_API_KEY env var set

.EXAMPLE
  $env:ROBOFLOW_API_KEY = "your_key_here"
  .\scripts\train_models.ps1

.EXAMPLE
  # Override epochs for a quick smoke test
  .\scripts\train_models.ps1 -PlayerEpochs 5 -BallEpochs 5 -CourtEpochs 5
#>

param(
    [string]$PythonExe     = "python",
    [string]$ModelsDir     = "$PSScriptRoot\..\basketball_analysis\models",
    [int]   $PlayerEpochs  = 100,
    [int]   $BallEpochs    = 250,
    [int]   $CourtEpochs   = 500,
    [int]   $PlayerBatch   = 8,
    [int]   $CourtBatch    = 16,
    [int]   $ImgSz         = 640,
    [switch]$SkipPlayer,
    [switch]$SkipBall,
    [switch]$SkipCourt
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Resolve API key ──────────────────────────────────────────────────────────
if (-not $env:ROBOFLOW_API_KEY) {
    $env:ROBOFLOW_API_KEY = Read-Host "Enter your Roboflow API key"
}
if (-not $env:ROBOFLOW_API_KEY) {
    Write-Error "ROBOFLOW_API_KEY is required."
    exit 1
}

# ── Resolve paths ────────────────────────────────────────────────────────────
$ModelsDir  = [System.IO.Path]::GetFullPath($ModelsDir)
$WorkDir    = [System.IO.Path]::GetFullPath("$PSScriptRoot\..")
$TrainDir   = Join-Path $WorkDir "train_workspace"

if (-not (Test-Path $ModelsDir)) {
    New-Item -ItemType Directory -Path $ModelsDir | Out-Null
    Write-Host "[+] Created models directory: $ModelsDir"
}
if (-not (Test-Path $TrainDir)) {
    New-Item -ItemType Directory -Path $TrainDir | Out-Null
}

Set-Location $TrainDir

function Find-BestPt {
    param([string]$RunsDir, [string]$TaskName)
    # Ultralytics saves to runs/<task>/train*/weights/best.pt
    $candidates = Get-ChildItem -Path $RunsDir -Recurse -Filter "best.pt" -ErrorAction SilentlyContinue |
                  Sort-Object LastWriteTime -Descending
    if ($candidates.Count -eq 0) {
        Write-Warning "No best.pt found under $RunsDir for $TaskName"
        return $null
    }
    return $candidates[0].FullName
}

# ═══════════════════════════════════════════════════════════════════════════
# 1. Download shared dataset (Player + Ball share the same Roboflow project)
# ═══════════════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "═══ Downloading dataset: basketball-players-fy4c2-vfsuv v17 ═══"
Write-Host "    (used by both player detector and ball detector)"
Write-Host ""

$datasetScript = @"
from roboflow import Roboflow
import os, shutil

rf = Roboflow(api_key=os.environ['ROBOFLOW_API_KEY'])
project = rf.workspace('workspace-5ujvu').project('basketball-players-fy4c2-vfsuv')
version = project.version(17)
dataset = version.download('yolov5')

# Roboflow downloads to Basketball-Players-17/; fix internal structure
base = dataset.location
train_src = os.path.join(base, 'train')
valid_src = os.path.join(base, 'valid')
inner_base = os.path.join(base, os.path.basename(base))

os.makedirs(inner_base, exist_ok=True)
if os.path.exists(train_src) and not os.path.exists(os.path.join(inner_base, 'train')):
    shutil.move(train_src, os.path.join(inner_base, 'train'))
if os.path.exists(valid_src) and not os.path.exists(os.path.join(inner_base, 'valid')):
    shutil.move(valid_src, os.path.join(inner_base, 'valid'))

print('DATASET_LOCATION=' + dataset.location)
"@

$datasetOutput = & $PythonExe -c $datasetScript
if ($LASTEXITCODE -ne 0) { Write-Error "Dataset download failed"; exit 1 }

# Extract dataset location from output
$datasetLocation = ($datasetOutput | Where-Object { $_ -like "DATASET_LOCATION=*" }) -replace "DATASET_LOCATION=", ""
if (-not $datasetLocation) {
    # Fallback: look for the expected directory
    $datasetLocation = Join-Path $TrainDir "Basketball-Players-17"
}
$dataYaml = Join-Path $datasetLocation "data.yaml"
Write-Host "Dataset at: $datasetLocation"

# ═══════════════════════════════════════════════════════════════════════════
# 2. Train player detector
# ═══════════════════════════════════════════════════════════════════════════
if (-not $SkipPlayer) {
    Write-Host ""
    Write-Host "═══ Training player detector ($PlayerEpochs epochs, batch $PlayerBatch) ═══"
    Write-Host ""

    & $PythonExe -m ultralytics.utils.benchmarks `
        2>&1 | Out-Null  # just to check ultralytics is available

    yolo task=detect mode=train `
        model=yolov5l6u.pt `
        data="$dataYaml" `
        epochs=$PlayerEpochs `
        imgsz=$ImgSz `
        batch=$PlayerBatch `
        name=player_detector `
        project="$TrainDir\runs\detect" `
        exist_ok=True `
        plots=True

    if ($LASTEXITCODE -ne 0) { Write-Error "Player detector training failed"; exit 1 }

    $playerBest = Find-BestPt "$TrainDir\runs\detect" "player_detector"
    if ($playerBest) {
        $dst = Join-Path $ModelsDir "player_detector.pt"
        Copy-Item $playerBest $dst -Force
        Write-Host "[+] Saved player_detector.pt  ← $playerBest"
    }
} else {
    Write-Host "[skip] Player detector training skipped (-SkipPlayer)"
}

# ═══════════════════════════════════════════════════════════════════════════
# 3. Train ball detector (same dataset, more epochs, focus on Ball class)
# ═══════════════════════════════════════════════════════════════════════════
if (-not $SkipBall) {
    Write-Host ""
    Write-Host "═══ Training ball detector ($BallEpochs epochs) ═══"
    Write-Host ""

    yolo task=detect mode=train `
        model=yolov5l6u.pt `
        data="$dataYaml" `
        epochs=$BallEpochs `
        imgsz=$ImgSz `
        name=ball_detector `
        project="$TrainDir\runs\detect" `
        exist_ok=True

    if ($LASTEXITCODE -ne 0) { Write-Error "Ball detector training failed"; exit 1 }

    $ballBest = Find-BestPt "$TrainDir\runs\detect" "ball_detector"
    if ($ballBest) {
        $dst = Join-Path $ModelsDir "ball_detector_model.pt"
        Copy-Item $ballBest $dst -Force
        Write-Host "[+] Saved ball_detector_model.pt  ← $ballBest"
    }
} else {
    Write-Host "[skip] Ball detector training skipped (-SkipBall)"
}

# ═══════════════════════════════════════════════════════════════════════════
# 4. Download court keypoint dataset and train pose model
# ═══════════════════════════════════════════════════════════════════════════
if (-not $SkipCourt) {
    Write-Host ""
    Write-Host "═══ Downloading dataset: reloc2-den7l v1 ═══"
    Write-Host ""

    $courtScript = @"
from roboflow import Roboflow
import os

rf = Roboflow(api_key=os.environ['ROBOFLOW_API_KEY'])
project = rf.workspace('fyp-3bwmg').project('reloc2-den7l')
version = project.version(1)
dataset = version.download('yolov8')
print('COURT_DATASET_LOCATION=' + dataset.location)
"@

    $courtOutput = & $PythonExe -c $courtScript
    if ($LASTEXITCODE -ne 0) { Write-Error "Court dataset download failed"; exit 1 }

    $courtLocation = ($courtOutput | Where-Object { $_ -like "COURT_DATASET_LOCATION=*" }) -replace "COURT_DATASET_LOCATION=", ""
    $courtYaml = Join-Path $courtLocation "data.yaml"
    Write-Host "Court dataset at: $courtLocation"

    Write-Host ""
    Write-Host "═══ Training court keypoint detector ($CourtEpochs epochs, batch $CourtBatch) ═══"
    Write-Host ""

    yolo task=pose mode=train `
        model=yolov8x-pose.pt `
        data="$courtYaml" `
        epochs=$CourtEpochs `
        imgsz=$ImgSz `
        batch=$CourtBatch `
        name=court_keypoint_detector `
        project="$TrainDir\runs\pose" `
        exist_ok=True

    if ($LASTEXITCODE -ne 0) { Write-Error "Court keypoint training failed"; exit 1 }

    $courtBest = Find-BestPt "$TrainDir\runs\pose" "court_keypoint_detector"
    if ($courtBest) {
        $dst = Join-Path $ModelsDir "court_keypoint_detector.pt"
        Copy-Item $courtBest $dst -Force
        Write-Host "[+] Saved court_keypoint_detector.pt  ← $courtBest"
    }
} else {
    Write-Host "[skip] Court keypoint training skipped (-SkipCourt)"
}

# ═══════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "═══ Training complete ═══"
Write-Host "Models in: $ModelsDir"
Get-ChildItem $ModelsDir -Filter "*.pt" | ForEach-Object {
    $sizeKB = [math]::Round($_.Length / 1KB)
    Write-Host "  $($_.Name)  ($sizeKB KB)"
}
Write-Host ""
Write-Host "Unset BA_DUMMY_MODELS (or set to false) to use real models:"
Write-Host "  Remove-Item Env:\BA_DUMMY_MODELS -ErrorAction SilentlyContinue"
