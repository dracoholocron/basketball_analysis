#!/usr/bin/env python3
"""Standalone pipeline benchmark runner (no api/DB/MinIO) — for cloud GPU tests
(e.g. RunPod RTX 4090). Feeds run_pipeline the same inputs the worker would use,
from the JSON produced by tools/export_game_annotations.py, and prints per-stage
wall times + the ball-source breakdown at the end.

Run from the engine root (basketball_analysis/):

  python tools/run_cloud_benchmark.py --video game.mp4 --annotations annotations.json \\
      [--ball-model models/ball_detector__prev.pt] [--out-dir bench_out]

Tuning comes from BA_* env vars (see RUNPOD_BENCHMARK.md for the recommended set).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.dirname(_HERE)
if _ENGINE not in sys.path:
    sys.path.insert(0, _ENGINE)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--annotations", required=True,
                    help="JSON from tools/export_game_annotations.py")
    ap.add_argument("--out-dir", default="bench_out")
    ap.add_argument("--player-model", default=None)
    ap.add_argument("--ball-model", default=None)
    ap.add_argument("--pose-model", default=None)
    args = ap.parse_args()

    with open(args.annotations) as f:
        ann = json.load(f)

    os.makedirs(args.out_dir, exist_ok=True)
    out_video = os.path.join(args.out_dir, "annotated.mp4")
    stub_dir = os.path.join(args.out_dir, "stubs")

    t0 = time.time()
    stage_t = {"_last": ("start", t0)}

    def on_progress(stage: str, pct: int) -> None:
        now = time.time()
        last_stage, last_t = stage_t["_last"]
        if stage != last_stage:
            stage_t[last_stage] = stage_t.get(last_stage, 0.0) + (now - last_t)
            stage_t["_last"] = (stage, now)
        print(f"[{now - t0:7.1f}s] {stage} {pct}%", flush=True)

    from main import run_pipeline

    metrics = run_pipeline(
        input_video=args.video,
        output_video=out_video,
        stub_path=stub_dir,
        use_stubs=False,
        team1_jersey=ann.get("team1_jersey") or "white shirt",
        team2_jersey=ann.get("team2_jersey") or "dark blue shirt",
        manual_landmarks=ann.get("manual_landmarks"),
        team_exemplars=ann.get("team_exemplars"),
        camera_motion=ann.get("camera_motion") or "static",
        ball_points=ann.get("ball_points"),
        hoop_boxes=ann.get("hoop_boxes"),
        team1_name=ann.get("team1_name"),
        team2_name=ann.get("team2_name"),
        player_detector_path=args.player_model,
        ball_detector_path=args.ball_model,
        pose_model_path=args.pose_model,
        on_progress=on_progress,
    )

    total = time.time() - t0
    last_stage, last_t = stage_t.pop("_last")
    stage_t[last_stage] = stage_t.get(last_stage, 0.0) + (time.time() - last_t)

    print("\n================ BENCHMARK SUMMARY ================")
    print(f"Total: {total / 60:.1f} min ({total:.0f}s)")
    print("Per-stage wall time:")
    for stage, secs in stage_t.items():
        if stage != "start":
            print(f"  {stage:<22} {secs / 60:6.1f} min")
    bsc = metrics.get("ball_source_counts") or {}
    btf = metrics.get("ball_total_frames") or 0
    print(f"Ball sources (of {btf} frames): {bsc}")
    print(f"Annotated video: {out_video}")
    summary = {
        "total_s": round(total, 1),
        "stages_s": {k: round(v, 1) for k, v in stage_t.items() if k != "start"},
        "ball_source_counts": bsc,
        "ball_total_frames": btf,
    }
    with open(os.path.join(args.out_dir, "benchmark.json"), "w") as f:
        json.dump(summary, f, indent=1)
    print(f"Summary: {os.path.join(args.out_dir, 'benchmark.json')}")


if __name__ == "__main__":
    main()
