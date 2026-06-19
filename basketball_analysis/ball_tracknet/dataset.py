"""PyTorch Dataset for TrackNet training.

Reads triplets of consecutive frames from the YOLO-format corpus produced by
`ball_sam2/export_dataset.py`.  For each middle frame that has a ball label
it produces:

    input  : (9, H, W) float32 tensor  — frames t-1, t, t+1 stacked (BGR→RGB /255)
    target : (1, H, W) float32 tensor  — Gaussian heatmap at ball centre

Negative examples (empty label files) contribute 10 % of the dataset (sampled)
so the model learns to output a blank heatmap when the ball is absent.
"""
from __future__ import annotations

import math
import os
import random
from typing import Optional

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from .model import INPUT_HW, SIGMA_PX


def _make_heatmap(cx_norm: float, cy_norm: float,
                  h: int, w: int, sigma: int = SIGMA_PX) -> np.ndarray:
    """Return a float32 heatmap with a Gaussian blob at (cx_norm*w, cy_norm*h)."""
    cx, cy = int(cx_norm * w), int(cy_norm * h)
    hm = np.zeros((h, w), dtype=np.float32)
    r = sigma * 3
    x0, x1 = max(0, cx - r), min(w, cx + r + 1)
    y0, y1 = max(0, cy - r), min(h, cy + r + 1)
    for y in range(y0, y1):
        for x in range(x0, x1):
            d2 = (x - cx) ** 2 + (y - cy) ** 2
            hm[y, x] = math.exp(-d2 / (2 * sigma ** 2))
    return hm


def _load_resize(path: str, hw: tuple[int, int]) -> np.ndarray:
    img = cv2.imread(path)
    if img is None:
        return np.zeros((hw[0], hw[1], 3), dtype=np.uint8)
    return cv2.resize(img, (hw[1], hw[0]))


class TrackNetDataset(Dataset):
    """Triplet ball-detection dataset built from a YOLO-format export directory.

    Parameters
    ----------
    dataset_dir   Root directory with images/ and labels/ sub-trees.
    split         "train" or "val".
    neg_ratio     Fraction of negative (ball-absent) frames to include.
    max_samples   Cap total samples (None = unlimited).
    augment       Horizontal flip + colour jitter on-the-fly.
    """

    def __init__(
        self,
        dataset_dir: str,
        split: str = "train",
        neg_ratio: float = 0.1,
        max_samples: Optional[int] = None,
        augment: bool = True,
    ) -> None:
        self.hw = INPUT_HW
        self.augment = augment and (split == "train")

        img_dir = os.path.join(dataset_dir, "images", split)
        # prefer tn_labels (cx cy format) over YOLO labels (0 cx cy w h)
        tn_lbl = os.path.join(dataset_dir, "tn_labels", split)
        yolo_lbl = os.path.join(dataset_dir, "labels", split)
        lbl_dir = tn_lbl if os.path.isdir(tn_lbl) else yolo_lbl
        self._tn_format = os.path.isdir(tn_lbl)

        all_imgs = sorted(f for f in os.listdir(img_dir) if f.endswith(".jpg"))

        # Build a game→sorted-frame list mapping so we can look up neighbours.
        # Stem pattern: <game_id>_<frame:06d>.jpg
        by_game: dict[str, list[str]] = {}
        for name in all_imgs:
            stem = name[:-4]
            parts = stem.rsplit("_", 1)
            if len(parts) == 2:
                by_game.setdefault(parts[0], []).append(stem)
        for v in by_game.values():
            v.sort()

        # Collect positive and negative stems separately
        positives, negatives = [], []
        for game, stems in by_game.items():
            for stem in stems:
                lbl = os.path.join(lbl_dir, stem + ".txt")
                if os.path.exists(lbl) and os.path.getsize(lbl) > 0:
                    positives.append((game, stem))
                else:
                    negatives.append((game, stem))

        # Sample negatives — use an isolated RNG so we don't stomp global random state
        n_neg = min(len(negatives), max(1, int(len(positives) * neg_ratio)))
        _rng = random.Random(42)
        sampled_neg = _rng.sample(negatives, n_neg)

        samples = positives + sampled_neg
        _rng.shuffle(samples)
        if max_samples:
            samples = samples[:max_samples]

        self.samples = samples
        self.by_game = {g: {s: i for i, s in enumerate(v)} for g, v in by_game.items()}
        self.game_stems = {g: v for g, v in by_game.items()}
        self.img_dir = img_dir
        self.lbl_dir = lbl_dir

    def __len__(self) -> int:
        return len(self.samples)

    def _neighbour(self, game: str, stem: str, delta: int) -> str:
        stems = self.game_stems.get(game, [])
        idx = self.by_game.get(game, {}).get(stem, 0)
        nb = max(0, min(len(stems) - 1, idx + delta))
        return stems[nb] if stems else stem

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        game, stem = self.samples[idx]
        stems = [
            self._neighbour(game, stem, -1),
            stem,
            self._neighbour(game, stem, +1),
        ]
        frames = [_load_resize(os.path.join(self.img_dir, s + ".jpg"), self.hw)
                  for s in stems]

        hflip = self.augment and random.random() < 0.5
        if hflip:
            frames = [f[:, ::-1, :].copy() for f in frames]

        # Stack as 9-channel float [0,1]
        inp = np.concatenate([f.astype(np.float32) / 255.0 for f in frames], axis=2)
        inp = torch.from_numpy(inp).permute(2, 0, 1)  # (9, H, W)

        # Heatmap target
        h, w = self.hw
        lbl_path = os.path.join(self.lbl_dir, stem + ".txt")
        hm = np.zeros((h, w), dtype=np.float32)
        if os.path.exists(lbl_path) and os.path.getsize(lbl_path) > 0:
            with open(lbl_path) as f:
                line = f.readline().strip()
            if line:
                parts = line.split()
                # tn_labels: "cx cy"  |  YOLO labels: "0 cx cy w h"
                if self._tn_format and len(parts) >= 2:
                    cx_n, cy_n = float(parts[0]), float(parts[1])
                elif not self._tn_format and len(parts) >= 3:
                    cx_n, cy_n = float(parts[1]), float(parts[2])
                else:
                    cx_n, cy_n = None, None
                if cx_n is not None:
                    if hflip:
                        cx_n = 1.0 - cx_n
                    hm = _make_heatmap(cx_n, cy_n, h, w)

        tgt = torch.from_numpy(hm).unsqueeze(0)  # (1, H, W)
        return inp, tgt
