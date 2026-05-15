<#
.SYNOPSIS
  Download YOLOv8 nano checkpoints from Ultralytics and wire them as the
  basketball analysis models so the full pipeline can run end-to-end without
  any custom-trained weights.

.DESCRIPTION
  Track A (dummy models) — for smoke tests and fast E2E validation.

  These models are trained on COCO, not on basketball data, so detection
  quality will be poor (they will detect "person" instead of "Player" and
  "sports ball" instead of "Ball").  Set the env var BA_DUMMY_MODELS=true
  so ball_tracker.py accepts "sports ball" as a valid ball class.

  Approximate download size: ~12 MB (yolov8n.pt) + ~6 MB (yolov8n-pose.pt)

.EXAMPLE
  # From repo root
  .\scripts\build_dummy_models.ps1

.EXAMPLE
  # Specify a custom Python interpreter
  .\scripts\build_dummy_models.ps1 -PythonExe "C:\code\basketball_analysis\.venv\Scripts\python.exe"
#>

param(
    [string]$PythonExe = "python",
    [string]$ModelsDir = "$PSScriptRoot\..\basketball_analysis\models"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Resolve paths ───────────────────────────────────────────────────────────
$ModelsDir = [System.IO.Path]::GetFullPath($ModelsDir)

if (-not (Test-Path $ModelsDir)) {
    New-Item -ItemType Directory -Path $ModelsDir | Out-Null
    Write-Host "[+] Created models directory: $ModelsDir"
}

# ── Download YOLOv8n checkpoints via Ultralytics (auto-cached) ───────────────
Write-Host ""
Write-Host "Downloading yolov8n.pt and yolov8n-pose.pt from Ultralytics hub..."
Write-Host "(First run may take a minute; subsequent runs use the local cache)"
Write-Host ""

& $PythonExe -c @"
from ultralytics import YOLO
import os

# Force download (or load from cache) — weights land in ~/.cache/ultralytics/
det  = YOLO('yolov8n.pt')
pose = YOLO('yolov8n-pose.pt')

det_path  = det.ckpt_path  or os.path.join(os.path.expanduser('~'), '.cache', 'ultralytics', 'yolov8n.pt')
pose_path = pose.ckpt_path or os.path.join(os.path.expanduser('~'), '.cache', 'ultralytics', 'yolov8n-pose.pt')

print('det_path=' + str(det_path))
print('pose_path=' + str(pose_path))
"@

if ($LASTEXITCODE -ne 0) {
    Write-Error "Python download step failed.  Make sure ultralytics is installed."
    exit 1
}

# Locate the cached files via a second Python call that just prints paths
$paths = & $PythonExe -c @"
from ultralytics import YOLO, settings as ul_settings
import os

det_path  = YOLO('yolov8n.pt').ckpt_path
pose_path = YOLO('yolov8n-pose.pt').ckpt_path

# ultralytics caches to <weights_dir>/yolov8n.pt
weights_dir = ul_settings.get('weights_dir', os.path.join(os.path.expanduser('~'), '.cache', 'ultralytics'))
if not det_path:  det_path  = os.path.join(weights_dir, 'yolov8n.pt')
if not pose_path: pose_path = os.path.join(weights_dir, 'yolov8n-pose.pt')

print(det_path)
print(pose_path)
"@

$detPt   = $paths[0].Trim()
$posePt  = $paths[1].Trim()

if (-not (Test-Path $detPt)) {
    # Fall back to common cache locations
    $candidates = @(
        "$env:USERPROFILE\.cache\ultralytics\yolov8n.pt",
        "$env:LOCALAPPDATA\Ultralytics\yolov8n.pt",
        "yolov8n.pt"          # might be in CWD after download
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $detPt = $c; break }
    }
}

if (-not (Test-Path $posePt)) {
    $candidates = @(
        "$env:USERPROFILE\.cache\ultralytics\yolov8n-pose.pt",
        "$env:LOCALAPPDATA\Ultralytics\yolov8n-pose.pt",
        "yolov8n-pose.pt"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $posePt = $c; break }
    }
}

if (-not (Test-Path $detPt)) {
    Write-Error "Could not locate yolov8n.pt after download.  Searched: $detPt"
    exit 1
}
if (-not (Test-Path $posePt)) {
    Write-Error "Could not locate yolov8n-pose.pt after download.  Searched: $posePt"
    exit 1
}

Write-Host "Source det  : $detPt"
Write-Host "Source pose : $posePt"
Write-Host ""

# ── Copy / rename into models/ ───────────────────────────────────────────────
$mappings = @(
    @{ Src = $detPt;  Dst = "player_detector.pt"       },
    @{ Src = $detPt;  Dst = "ball_detector_model.pt"   },
    @{ Src = $posePt; Dst = "court_keypoint_detector.pt" }
)

foreach ($m in $mappings) {
    $dst = Join-Path $ModelsDir $m.Dst
    Copy-Item -Path $m.Src -Destination $dst -Force
    Write-Host "[+] $($m.Dst)"
}

Write-Host ""
Write-Host "Done!  Dummy models are in: $ModelsDir"
Write-Host ""
Write-Host "IMPORTANT — set this env var before running the pipeline:"
Write-Host "  `$env:BA_DUMMY_MODELS = 'true'"
Write-Host ""
Write-Host "Detection quality will be low (COCO weights, not basketball-specific)."
Write-Host "Use these models only for smoke / E2E tests while real models train."
