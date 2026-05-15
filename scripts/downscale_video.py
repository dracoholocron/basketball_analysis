"""
Downscale videos to a target height using OpenCV (no ffmpeg needed).

Usage:
    python scripts/downscale_video.py \\
        --input  "C:\\videos\\input\\game.mp4" \\
        --output "C:\\videos\\720p\\game.mp4" \\
        [--height 720] \\
        [--fps 30]

Or batch-process a folder:
    python scripts/downscale_video.py \\
        --folder  "C:\\videos\\input" \\
        --out-dir "C:\\videos\\720p" \\
        --height 576
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:
    print("opencv-python-headless is required: pip install opencv-python-headless")
    sys.exit(1)

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def downscale(input_path: Path, output_path: Path, target_height: int, target_fps: float | None) -> None:
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        print(f"  ERROR: cannot open {input_path}")
        return

    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out_fps = target_fps or src_fps

    # Preserve aspect ratio
    scale = target_height / src_h
    out_w = int(src_w * scale)
    out_h = target_height
    # Ensure dimensions are even (required by H.264)
    out_w = out_w if out_w % 2 == 0 else out_w + 1
    out_h = out_h if out_h % 2 == 0 else out_h + 1

    print(f"  {src_w}x{src_h} @ {src_fps:.1f} fps -> {out_w}x{out_h} @ {out_fps:.1f} fps  ({total_frames} frames)")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, out_fps, (out_w, out_h))
    if not writer.isOpened():
        print(f"  ERROR: cannot create output file {output_path}")
        cap.release()
        return

    frame_idx = 0
    t0 = time.time()
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        resized = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)
        writer.write(resized)
        frame_idx += 1
        if frame_idx % 300 == 0:
            elapsed = time.time() - t0
            pct = frame_idx / total_frames * 100 if total_frames > 0 else 0
            fps_proc = frame_idx / elapsed
            eta = (total_frames - frame_idx) / fps_proc if fps_proc > 0 else 0
            print(f"  {pct:.0f}%  ({frame_idx}/{total_frames})  {fps_proc:.0f} fps proc  ETA {eta:.0f}s")

    cap.release()
    writer.release()

    in_mb = input_path.stat().st_size / 1_048_576
    out_mb = output_path.stat().st_size / 1_048_576
    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.0f}s  |  {in_mb:.0f} MB -> {out_mb:.0f} MB")


def main() -> None:
    parser = argparse.ArgumentParser(description="Downscale videos using OpenCV")
    parser.add_argument("--input", help="Single input video file")
    parser.add_argument("--output", help="Single output video file")
    parser.add_argument("--folder", help="Input folder (batch mode)")
    parser.add_argument("--out-dir", help="Output folder (batch mode)")
    parser.add_argument("--height", type=int, default=576,
                        help="Target height in pixels (default 576 -> 1280x576 from 2400x1080)")
    parser.add_argument("--fps", type=float, default=None,
                        help="Target FPS (default: keep source FPS)")
    args = parser.parse_args()

    if args.input:
        inp = Path(args.input)
        out = Path(args.output) if args.output else inp.parent / f"{inp.stem}_scaled{inp.suffix}"
        print(f"\n{inp.name}")
        downscale(inp, out, args.height, args.fps)
    elif args.folder:
        folder = Path(args.folder)
        out_dir = Path(args.out_dir) if args.out_dir else folder / "_scaled"
        videos = sorted(p for p in folder.iterdir() if p.suffix.lower() in VIDEO_EXTS)
        if not videos:
            print(f"No videos found in {folder}")
            sys.exit(0)
        print(f"Found {len(videos)} video(s) in {folder} -> {out_dir}\n")
        for v in videos:
            print(f"{v.name}")
            downscale(v, out_dir / v.name, args.height, args.fps)
        print(f"\nAll done. Scaled videos in: {out_dir}")
        print(f"\nNext: ingest them:")
        print(f"  python scripts/ingest_folder.py --folder \"{out_dir}\" --season-id <UUID>")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
