"""
GPU benchmark — measure inference FPS for the three YOLO models on the RTX 5070.

Usage:
    python bench/run_bench.py \
        --player_model basketball_analysis/models/player_detector.pt \
        --ball_model   basketball_analysis/models/ball_detector_model.pt \
        --court_model  basketball_analysis/models/court_keypoint_detector.pt \
        --n_frames 100 \
        --width 1280 \
        --height 720 \
        --out bench/report.json

Exits with code 1 if any model's FPS drops more than 15% below the baseline
stored in bench/baseline.json (updated with --update-baseline).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bench")


def _make_random_frames(n: int, width: int, height: int) -> list[np.ndarray]:
    return [
        np.random.randint(0, 255, (height, width, 3), dtype=np.uint8) for _ in range(n)
    ]


def _bench_model(
    model_path: str,
    frames: list[np.ndarray],
    batch_size: int = 8,
    conf: float = 0.35,
    warmup: int = 3,
) -> dict[str, float]:
    from ultralytics import YOLO

    logger.info("Loading model: %s", model_path)
    model = YOLO(model_path)

    # Warm-up
    for _ in range(warmup):
        model.predict(frames[:batch_size], conf=conf, verbose=False)

    t0 = time.perf_counter()
    for i in range(0, len(frames), batch_size):
        model.predict(frames[i : i + batch_size], conf=conf, verbose=False)
    elapsed = time.perf_counter() - t0

    fps = len(frames) / elapsed
    ms_per_frame = elapsed / len(frames) * 1000
    logger.info("  FPS: %.1f  ms/frame: %.2f", fps, ms_per_frame)
    return {"fps": fps, "ms_per_frame": ms_per_frame, "n_frames": len(frames)}


def _check_regression(
    results: dict[str, Any],
    baseline_path: str,
    threshold: float = 0.15,
) -> list[str]:
    if not os.path.exists(baseline_path):
        return []
    with open(baseline_path) as f:
        baseline = json.load(f)
    regressions = []
    for model_key, stats in results.items():
        if model_key not in baseline:
            continue
        base_fps = baseline[model_key]["fps"]
        curr_fps = stats["fps"]
        if (base_fps - curr_fps) / base_fps > threshold:
            msg = (
                f"{model_key}: FPS dropped {((base_fps-curr_fps)/base_fps*100):.1f}% "
                f"(baseline={base_fps:.1f}, current={curr_fps:.1f})"
            )
            regressions.append(msg)
    return regressions


def main() -> None:
    parser = argparse.ArgumentParser(description="GPU FPS benchmark for basketball YOLO models")
    parser.add_argument("--player_model", required=True)
    parser.add_argument("--ball_model", required=True)
    parser.add_argument("--court_model", required=True)
    parser.add_argument("--n_frames", type=int, default=100)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--batch_size", type=int, default=8)
    parser.add_argument("--out", default="bench/report.json")
    parser.add_argument("--baseline", default="bench/baseline.json")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--regression-threshold", type=float, default=0.15)
    args = parser.parse_args()

    # Check GPU
    try:
        import torch
        if torch.cuda.is_available():
            logger.info("GPU: %s  CUDA: %s", torch.cuda.get_device_name(0), torch.version.cuda)
        else:
            logger.warning("CUDA not available — benchmarking on CPU")
    except ImportError:
        logger.warning("torch not installed")

    # Add engine to path
    engine_path = str(Path(__file__).parent.parent / "basketball_analysis" / "basketball_analysis")
    if engine_path not in sys.path:
        sys.path.insert(0, engine_path)

    frames = _make_random_frames(args.n_frames, args.width, args.height)
    logger.info("Generated %d synthetic %dx%d frames", args.n_frames, args.width, args.height)

    results: dict[str, Any] = {
        "metadata": {
            "n_frames": args.n_frames,
            "resolution": f"{args.width}x{args.height}",
            "batch_size": args.batch_size,
        }
    }

    for key, path in [
        ("player_detector", args.player_model),
        ("ball_detector", args.ball_model),
        ("court_keypoint_detector", args.court_model),
    ]:
        if not os.path.exists(path):
            logger.warning("Model not found: %s — skipping", path)
            results[key] = {"fps": 0, "ms_per_frame": 0, "n_frames": 0, "skipped": True}
            continue
        logger.info("=== %s ===", key)
        results[key] = _bench_model(path, frames, batch_size=args.batch_size)

    # Write report
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    logger.info("Report saved to %s", args.out)

    # Update baseline
    if args.update_baseline:
        baseline_data = {k: v for k, v in results.items() if k != "metadata"}
        with open(args.baseline, "w") as f:
            json.dump(baseline_data, f, indent=2)
        logger.info("Baseline updated: %s", args.baseline)

    # Check regressions
    regressions = _check_regression(results, args.baseline, args.regression_threshold)
    if regressions:
        logger.error("PERFORMANCE REGRESSIONS DETECTED:")
        for msg in regressions:
            logger.error("  %s", msg)
        sys.exit(1)

    logger.info("Benchmark complete. No regressions detected.")


if __name__ == "__main__":
    main()
