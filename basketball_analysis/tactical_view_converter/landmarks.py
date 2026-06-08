"""
FIBA/NBA court landmark catalog for manual homography calibration.

Each landmark has a unique ID, a human-readable label, a category,
and a function that maps court dimensions (width_m, height_m) to the
landmark's position in metres on the tactical view.

Distances follow the FIBA standard court (28m × 15m):
  - Free-throw line: 5.79 m from baseline
  - Lane (key) width: 4.9 m centred on court
  - Hoop: 1.575 m from baseline, centred laterally
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class CourtLandmark:
    id: str
    label: str
    category: str  # "corner" | "circle" | "line" | "key" | "hoop"
    tactical_pos: Callable[[float, float], tuple[float, float]]  # (w_m, h_m) -> (x_m, y_m)


CATALOG: list[CourtLandmark] = [
    # ── Corners ───────────────────────────────────────────────────────────
    CourtLandmark("corner_tl", "Court corner - Top Left",       "corner", lambda w, h: (0,       0)),
    CourtLandmark("corner_tr", "Court corner - Top Right",      "corner", lambda w, h: (w,       0)),
    CourtLandmark("corner_br", "Court corner - Bottom Right",   "corner", lambda w, h: (w,       h)),
    CourtLandmark("corner_bl", "Court corner - Bottom Left",    "corner", lambda w, h: (0,       h)),

    # ── Center circle & midline ───────────────────────────────────────────
    CourtLandmark("center_circle",  "Center circle - center",      "circle", lambda w, h: (w / 2,  h / 2)),
    CourtLandmark("midline_top",    "Midline - Top edge",          "line",   lambda w, h: (w / 2,  0)),
    CourtLandmark("midline_bottom", "Midline - Bottom edge",       "line",   lambda w, h: (w / 2,  h)),

    # ── Left key ──────────────────────────────────────────────────────────
    CourtLandmark("ftline_left",    "Free-throw line - Left",      "key",    lambda w, h: (5.79,       h / 2)),
    CourtLandmark("key_tl_left",    "Left key - Top-Left corner",  "key",    lambda w, h: (0,          h / 2 - 2.45)),
    CourtLandmark("key_bl_left",    "Left key - Bottom-Left corner","key",   lambda w, h: (0,          h / 2 + 2.45)),
    CourtLandmark("key_tr_left",    "Left key - Top-Right corner", "key",    lambda w, h: (5.79,       h / 2 - 2.45)),
    CourtLandmark("key_br_left",    "Left key - Bottom-Right corner","key",  lambda w, h: (5.79,       h / 2 + 2.45)),

    # ── Right key ─────────────────────────────────────────────────────────
    CourtLandmark("ftline_right",   "Free-throw line - Right",     "key",    lambda w, h: (w - 5.79,   h / 2)),
    CourtLandmark("key_tl_right",   "Right key - Top-Left corner", "key",    lambda w, h: (w - 5.79,   h / 2 - 2.45)),
    CourtLandmark("key_bl_right",   "Right key - Bottom-Left corner","key",  lambda w, h: (w - 5.79,   h / 2 + 2.45)),
    CourtLandmark("key_tr_right",   "Right key - Top-Right corner","key",    lambda w, h: (w,          h / 2 - 2.45)),
    CourtLandmark("key_br_right",   "Right key - Bottom-Right corner","key", lambda w, h: (w,          h / 2 + 2.45)),

    # ── Hoops ─────────────────────────────────────────────────────────────
    CourtLandmark("hoop_left",  "Hoop - Left baseline center",  "hoop", lambda w, h: (1.575,     h / 2)),
    CourtLandmark("hoop_right", "Hoop - Right baseline center", "hoop", lambda w, h: (w - 1.575, h / 2)),
]

# Convenience mapping by id
CATALOG_BY_ID: dict[str, CourtLandmark] = {lm.id: lm for lm in CATALOG}
