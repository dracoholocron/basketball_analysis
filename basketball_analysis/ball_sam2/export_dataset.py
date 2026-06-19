"""
Export SAM2-propagated ball boxes as a YOLO-format dataset for fine-tuning the
ball detector (purpose 2 of the ball-annotation module).

`export_yolo_dataset` turns a per-frame ball-track list (e.g. SAM2 output, in 720p
space) + the source video into images + YOLO labels:
  out_dir/images/{split}/<game>_<frame>.jpg
  out_dir/labels/{split}/<game>_<frame>.txt    # "0 cx cy w h" normalized, class Ball
Frames marked NOT visible (negatives) are written with an empty label file.

This accumulates across games. Train with the existing notebook / `yolo train`
using a data.yaml that points at out_dir (single class: Ball).
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def export_yolo_dataset(
    video_path: str,
    ball_tracks: list[dict],
    out_dir: str,
    game_id: str,
    not_visible_frames: set[int] | None = None,
    min_score: float = 0.3,
    val_every: int = 5,
    max_frames: int | None = None,
) -> int:
    """Write images + YOLO labels for frames with a confident ball box.

    Returns the number of labeled (positive) frames written.
    """
    import cv2
    from utils.video_utils import iter_video_frames

    not_visible_frames = not_visible_frames or set()
    img_train = os.path.join(out_dir, "images", "train")
    img_val = os.path.join(out_dir, "images", "val")
    lbl_train = os.path.join(out_dir, "labels", "train")
    lbl_val = os.path.join(out_dir, "labels", "val")
    for d in (img_train, img_val, lbl_train, lbl_val):
        os.makedirs(d, exist_ok=True)

    written = 0
    for i, frame in enumerate(iter_video_frames(video_path, max_height=720)):
        if i >= len(ball_tracks):
            break
        if max_frames and written >= max_frames:
            break
        h, w = frame.shape[:2]
        bt = ball_tracks[i]
        is_val = (i % val_every == 0)
        img_dir = img_val if is_val else img_train
        lbl_dir = lbl_val if is_val else lbl_train
        stem = f"{game_id}_{i:06d}"

        label_lines: list[str] = []
        bbox = bt.get(1, {}).get("bbox", [])
        score = bt.get(1, {}).get("score", 1.0)
        if i in not_visible_frames:
            # negative example — empty label
            pass
        elif len(bbox) >= 4 and score >= min_score:
            x1, y1, x2, y2 = bbox[:4]
            cx = ((x1 + x2) / 2.0) / w
            cy = ((y1 + y2) / 2.0) / h
            bw = abs(x2 - x1) / w
            bh = abs(y2 - y1) / h
            if 0 < bw < 1 and 0 < bh < 1:
                label_lines.append(f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
        else:
            continue  # no confident box and not a labeled negative → skip frame

        cv2.imwrite(os.path.join(img_dir, stem + ".jpg"), frame)
        with open(os.path.join(lbl_dir, stem + ".txt"), "w") as f:
            f.write("\n".join(label_lines))
        if label_lines:
            written += 1

    # data.yaml (single class)
    yaml_path = os.path.join(out_dir, "data.yaml")
    if not os.path.exists(yaml_path):
        with open(yaml_path, "w") as f:
            f.write(
                f"path: {out_dir}\ntrain: images/train\nval: images/val\n"
                "nc: 1\nnames: ['Ball']\n"
            )
    logger.info("Exported %d positive ball frames to %s", written, out_dir)
    return written


def export_tracknet_dataset(
    video_path: str,
    ball_tracks: list[dict],
    out_dir: str,
    game_id: str,
    min_score: float = 0.3,
    val_every: int = 5,
    max_frames: int | None = None,
) -> int:
    """Write single-frame JPEG images + normalized (cx,cy) text labels for TrackNet.

    Reuses the same images/{train,val}/<game>_<frame>.jpg and
    labels/{train,val}/<game>_<frame>.txt layout as export_yolo_dataset so both
    datasets share disk space.  Only the label format differs: TrackNet labels
    contain a single line ``cx cy`` (both 0–1 normalised) instead of YOLO's
    ``0 cx cy w h``.  Empty label = ball not visible.

    A separate ``tracknet_data.yaml`` is written for the training script.
    Returns the number of labeled (positive) frames written.
    """
    import cv2
    from utils.video_utils import iter_video_frames

    tn_lbl_train = os.path.join(out_dir, "tn_labels", "train")
    tn_lbl_val   = os.path.join(out_dir, "tn_labels", "val")
    img_train    = os.path.join(out_dir, "images", "train")
    img_val      = os.path.join(out_dir, "images", "val")
    for d in (tn_lbl_train, tn_lbl_val, img_train, img_val):
        os.makedirs(d, exist_ok=True)

    written = 0
    for i, frame in enumerate(iter_video_frames(video_path, max_height=720)):
        if i >= len(ball_tracks):
            break
        if max_frames and i >= max_frames:
            break
        h, w = frame.shape[:2]
        bt = ball_tracks[i]
        is_val = (i % val_every == 0)
        img_dir = img_val if is_val else img_train
        lbl_dir = tn_lbl_val if is_val else tn_lbl_train
        stem = f"{game_id}_{i:06d}"
        img_path = os.path.join(img_dir, stem + ".jpg")

        # Write image (shared with YOLO export if already there)
        if not os.path.exists(img_path):
            cv2.imwrite(img_path, frame)

        bbox = bt.get(1, {}).get("bbox", [])
        score = bt.get(1, {}).get("score", 1.0)
        lbl_path = os.path.join(lbl_dir, stem + ".txt")
        if len(bbox) >= 4 and score >= min_score:
            x1, y1, x2, y2 = bbox[:4]
            cx = ((x1 + x2) / 2.0) / w
            cy = ((y1 + y2) / 2.0) / h
            if 0 < cx < 1 and 0 < cy < 1:
                with open(lbl_path, "w") as f:
                    f.write(f"{cx:.6f} {cy:.6f}\n")
                written += 1
                continue
        # Negative or no confident detection → empty label
        open(lbl_path, "w").close()

    yaml_path = os.path.join(out_dir, "tracknet_data.yaml")
    if not os.path.exists(yaml_path):
        with open(yaml_path, "w") as f:
            f.write(
                f"path: {out_dir}\n"
                "images_train: images/train\nimages_val: images/val\n"
                "labels_train: tn_labels/train\nlabels_val: tn_labels/val\n"
            )
    logger.info("Exported %d positive TrackNet frames to %s", written, out_dir)
    return written
