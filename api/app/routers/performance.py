"""Performance dashboard — aggregate per-run analysis summaries (detection-quality
proxies + timing/efficiency) by day/month/year, plus a TrackNet-vs-YOLO comparison.

Aggregation is done in Python over JobRunSummary rows so it stays DB-dialect agnostic;
the volume (one row per analysis) is small enough that this is cheap.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import require_role
from ..models.job_run_summary import JobRunSummary

router = APIRouter(prefix="/performance", tags=["performance"])
_staff = require_role("admin", "coach")


def _bucket(dt, period: str) -> str:
    if period == "yearly":
        return dt.strftime("%Y")
    if period == "monthly":
        return dt.strftime("%Y-%m")
    return dt.strftime("%Y-%m-%d")  # daily


def _avg(vals: list[float]) -> Optional[float]:
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


@router.get("/summary")
async def performance_summary(
    period: str = Query("daily", pattern="^(daily|monthly|yearly)$"),
    db: AsyncSession = Depends(get_db),
    _=Depends(_staff),
):
    """Time series (by period) of detection-quality proxies + timing, and a per-ball-detector
    comparison aggregated over all runs in range."""
    rows = (await db.execute(
        select(JobRunSummary).order_by(JobRunSummary.created_at.asc())
    )).scalars().all()

    buckets: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    by_detector: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for r in rows:
        if r.created_at is None:
            continue
        b = _bucket(r.created_at, period)
        buckets[b]["coverage"].append(r.ball_coverage_pct)
        buckets[b]["raw_rate"].append(r.ball_raw_detection_rate)
        buckets[b]["total_seconds"].append(r.total_seconds)
        buckets[b]["fps"].append(r.fps_processed)
        buckets[b]["review_flags"].append(r.ball_review_flags)
        buckets[b]["static_fp"].append(
            (r.ball_static_fp_dropped or 0) + (r.ball_static_fp_dropped_post_sahi or 0))
        buckets[b]["count"].append(1)

        det = r.ball_detector_source or "unknown"
        by_detector[det]["coverage"].append(r.ball_coverage_pct)
        by_detector[det]["raw_rate"].append(r.ball_raw_detection_rate)
        by_detector[det]["total_seconds"].append(r.total_seconds)
        by_detector[det]["count"].append(1)

    series = [
        {
            "period": b,
            "runs": int(sum(d["count"])),
            "avg_coverage_pct": _avg(d["coverage"]),
            "avg_raw_detection_rate": _avg(d["raw_rate"]),
            "avg_total_seconds": _avg(d["total_seconds"]),
            "avg_fps_processed": _avg(d["fps"]),
            "avg_review_flags": _avg(d["review_flags"]),
            "total_static_fp_dropped": int(sum(d["static_fp"])),
        }
        for b, d in sorted(buckets.items())
    ]

    detectors = [
        {
            "detector": det,
            "runs": int(sum(d["count"])),
            "avg_coverage_pct": _avg(d["coverage"]),
            "avg_raw_detection_rate": _avg(d["raw_rate"]),
            "avg_total_seconds": _avg(d["total_seconds"]),
        }
        for det, d in sorted(by_detector.items())
    ]

    return {
        "period": period,
        "total_runs": len(rows),
        "series": series,
        "detectors": detectors,
    }
