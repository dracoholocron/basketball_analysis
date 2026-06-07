"""
Retrain the court keypoint detector using the existing reloc2-1 dataset.

Dataset: train_workspace/reloc2-1
  - 1 class: basketball court
  - 18 keypoints per court instance
  - 1172 train / 222 valid / 74 test images

Usage:
    cd basketball_analysis
    python scripts/train_court_keypoints.py [--epochs 100] [--device 0]
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("train_court_keypoints")

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
ENGINE_DIR = SCRIPT_DIR.parent          # basketball_analysis/basketball_analysis/
REPO_ROOT = ENGINE_DIR.parent           # basketball_analysis/
DATASET_YAML = REPO_ROOT / "train_workspace" / "reloc2-1" / "data.yaml"
MODELS_DIR = ENGINE_DIR / "models"
BASE_MODEL = "yolo11x-pose.pt"          # YOLO11 pose variant (downloads automatically)
OUTPUT_NAME = "smartbasket_court_kp"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Retrain court keypoint detector with YOLO11-pose")
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--device", type=str, default="0", help="GPU device index or 'cpu'")
    p.add_argument("--patience", type=int, default=50)
    p.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not DATASET_YAML.exists():
        log.error("Dataset not found: %s", DATASET_YAML)
        log.error("Expected the reloc2-1 dataset in train_workspace/reloc2-1/")
        raise SystemExit(1)

    log.info("Dataset YAML : %s", DATASET_YAML)
    log.info("Base model   : %s", BASE_MODEL)
    log.info("Epochs       : %d", args.epochs)
    log.info("Batch        : %d", args.batch)
    log.info("Image size   : %d", args.imgsz)
    log.info("Device       : %s", args.device)

    from ultralytics import YOLO

    # When resuming, YOLO requires loading last.pt directly (not the base model)
    last_pt = ENGINE_DIR / "runs" / "pose" / "runs" / "pose" / OUTPUT_NAME / "weights" / "last.pt"
    if args.resume and last_pt.exists():
        log.info("Resuming from checkpoint: %s", last_pt)
        model = YOLO(str(last_pt))
        results = model.train(resume=True)
    else:
        if args.resume:
            log.warning("No checkpoint found at %s — starting fresh training", last_pt)
        model = YOLO(BASE_MODEL)
        results = model.train(
            task="pose",
            data=str(DATASET_YAML),
            epochs=args.epochs,
            batch=args.batch,
            imgsz=args.imgsz,
            device=args.device,
            patience=args.patience,
            project="runs/pose",
            name=OUTPUT_NAME,
            exist_ok=True,
            # Augmentation — moderate for court keypoints
            hsv_h=0.010,
            hsv_s=0.5,
            hsv_v=0.3,
            fliplr=0.5,
            mosaic=0.8,
            amp=True,
        )

    # ── Deploy best model ──────────────────────────────────────────────────────
    best_pt = Path(results.save_dir) / "weights" / "best.pt"
    if best_pt.exists():
        dest = MODELS_DIR / "court_keypoint_detector_yolo11.pt"
        MODELS_DIR.mkdir(exist_ok=True)
        shutil.copy(best_pt, dest)
        log.info("Best model saved → %s", dest)

        # Also replace the active model used by the pipeline
        active = MODELS_DIR / "court_keypoint_detector.pt"
        shutil.copy(best_pt, active)
        log.info("Active model updated → %s", active)
    else:
        log.warning("best.pt not found at %s — training may have failed", best_pt)

    log.info("Training complete. Results in: %s", results.save_dir)


if __name__ == "__main__":
    main()
