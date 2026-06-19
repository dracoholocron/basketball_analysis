#!/usr/bin/env python3
"""Ball-source audit: export ball-box crops grouped by source (YOLO/SAM2/SAHI/Kalman/
interp) so you can quickly tally TRUE vs FALSE positives per model.

Inputs:
  - a video (the same one analyzed; crops are taken at 720p, matching the pipeline space)
  - the ball_debug.json produced when the pipeline runs with BA_BALL_DEBUG=true
    (saved next to the annotated output video as <output>.ball_debug.json)

Usage:
  python ball_source_audit.py --video game.mp4 --debug out.mp4.ball_debug.json \\
      --out audit/ --per-source 60 --pad 1.4

Then open audit/<source>/ and count how many crops actually contain the ball.
"""
from __future__ import annotations

import argparse
import json
import os
import random

import cv2


def _frame_at_720(frame):
    if frame.shape[0] > 720:
        s = 720 / frame.shape[0]
        frame = cv2.resize(frame, (int(frame.shape[1] * s), 720), interpolation=cv2.INTER_AREA)
    return frame


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--debug", required=True, help="<output>.ball_debug.json")
    ap.add_argument("--out", default="ball_audit")
    ap.add_argument("--per-source", type=int, default=60, help="max crops sampled per source")
    ap.add_argument("--pad", type=float, default=1.6, help="crop padding factor around the box")
    args = ap.parse_args()

    with open(args.debug) as f:
        dets = json.load(f)
    by_src: dict[str, list[dict]] = {}
    for d in dets:
        if d.get("bbox"):
            by_src.setdefault(d.get("source") or "none", []).append(d)

    # Sample up to per-source detections per source (stride-sampled for time spread).
    sampled: dict[int, list[tuple[str, list]]] = {}
    counts = {}
    for src, items in by_src.items():
        items = sorted(items, key=lambda d: d["frame"])
        if len(items) > args.per_source:
            step = len(items) / args.per_source
            items = [items[int(i * step)] for i in range(args.per_source)]
        counts[src] = len(items)
        os.makedirs(os.path.join(args.out, src), exist_ok=True)
        for d in items:
            sampled.setdefault(int(d["frame"]), []).append((src, d["bbox"]))

    print("Detections per source (total / sampled):")
    for src, items in by_src.items():
        print(f"  {src:8} {len(items):6} / {counts.get(src,0)}")

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {args.video}")
    idx = 0
    saved = 0
    want = set(sampled)
    while want:
        ok, frame = cap.read()
        if not ok:
            break
        if idx in sampled:
            frame = _frame_at_720(frame)
            H, W = frame.shape[:2]
            for src, box in sampled[idx]:
                x1, y1, x2, y2 = box
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                bw = max(8, (x2 - x1)) * args.pad
                bh = max(8, (y2 - y1)) * args.pad
                cx1 = max(0, int(cx - bw)); cy1 = max(0, int(cy - bh))
                cx2 = min(W, int(cx + bw)); cy2 = min(H, int(cy + bh))
                crop = frame[cy1:cy2, cx1:cx2]
                if crop.size:
                    cv2.imwrite(os.path.join(args.out, src, f"f{idx:06d}.jpg"), crop)
                    saved += 1
            want.discard(idx)
        idx += 1
    cap.release()
    print(f"\nSaved {saved} crops under {args.out}/<source>/. "
          f"Open each folder and count TRUE vs FALSE positives.")


if __name__ == "__main__":
    main()
