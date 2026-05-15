<#
.SYNOPSIS
    Downscale videos to 720p for safe GPU inference.

.DESCRIPTION
    Uses ffmpeg to re-encode videos from a source folder to 720p H.264,
    which reduces GPU VRAM usage during YOLO inference for long recordings.

.PARAMETER InputFolder
    Folder containing source videos (default: current dir).

.PARAMETER OutputFolder
    Destination folder for 720p videos (default: <InputFolder>\_720p).

.PARAMETER Crf
    H.264 quality (18-28, lower = better quality, larger file). Default: 23.

.PARAMETER Pattern
    File glob to match (default: *.mp4). Use "*.mp4 *.avi" for multiple.

.EXAMPLE
    .\scripts\preprocess_video.ps1 `
        -InputFolder "C:\code\SmartBasket\basketball-highlight-agent\videos\input" `
        -OutputFolder "C:\code\SmartBasket\basketball-highlight-agent\videos\720p"
#>

param(
    [string]$InputFolder = ".",
    [string]$OutputFolder = "",
    [int]$Crf = 23,
    [string]$Pattern = "*.mp4"
)

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Error "ffmpeg not found. Install from https://ffmpeg.org/download.html or run: winget install ffmpeg"
    exit 1
}

if (-not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    Write-Error "ffprobe not found (part of ffmpeg package)."
    exit 1
}

$InputFolder = (Resolve-Path $InputFolder).Path
if ($OutputFolder -eq "") {
    $OutputFolder = Join-Path $InputFolder "_720p"
}

New-Item -ItemType Directory -Path $OutputFolder -Force | Out-Null
Write-Host "Input  : $InputFolder"
Write-Host "Output : $OutputFolder"
Write-Host ""

$videos = Get-ChildItem -Path $InputFolder -Filter $Pattern
if ($videos.Count -eq 0) {
    Write-Host "No files matching '$Pattern' found in $InputFolder"
    exit 0
}

foreach ($video in $videos) {
    # Probe resolution
    $probeArgs = @("-v", "quiet", "-print_format", "json", "-show_streams", $video.FullName)
    $probeJson = & ffprobe @probeArgs 2>&1 | Out-String
    $probe = $probeJson | ConvertFrom-Json -ErrorAction SilentlyContinue
    $videoStream = $probe.streams | Where-Object { $_.codec_type -eq "video" } | Select-Object -First 1

    $width  = [int]($videoStream.width  ?? 0)
    $height = [int]($videoStream.height ?? 0)
    $fps    = $videoStream.r_frame_rate ?? "?"
    $sizeMB = [math]::Round($video.Length / 1MB, 1)

    Write-Host "[$($video.Name)]  ${width}x${height} @ $fps fps  (${sizeMB} MB)"

    if ($height -le 720 -and $width -le 1280) {
        Write-Host "  -> Already <= 720p, copying without re-encode..."
        $outPath = Join-Path $OutputFolder $video.Name
        Copy-Item $video.FullName $outPath -Force
        Write-Host "  -> Copied to $outPath"
    } else {
        $outPath = Join-Path $OutputFolder $video.Name
        Write-Host "  -> Downscaling to 720p..."
        $ffmpegArgs = @(
            "-i", $video.FullName,
            "-vf", "scale=-2:720",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", $Crf.ToString(),
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            "-y", $outPath
        )
        & ffmpeg @ffmpegArgs
        if ($LASTEXITCODE -eq 0) {
            $outSize = [math]::Round((Get-Item $outPath).Length / 1MB, 1)
            Write-Host "  -> Saved: $outPath (${outSize} MB)"
        } else {
            Write-Warning "  -> ffmpeg failed for $($video.Name)"
        }
    }
    Write-Host ""
}

Write-Host "Done. 720p videos are in: $OutputFolder"
Write-Host ""
Write-Host "Next step: ingest them into the platform:"
Write-Host "  python scripts/ingest_folder.py --folder `"$OutputFolder`" --season-id <UUID>"
