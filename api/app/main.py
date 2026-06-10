"""
Basketball Analytics Platform — FastAPI application entry point.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .routers import auth, games, jobs, metrics
from .routers import organizations, seasons, teams, players
from .routers import box_scores, game_events, matchups, plays, playbooks, training
from .routers import annotations, ball_annotations, hoop_annotations, lab

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Basketball Analytics Platform",
    description=(
        "Video analysis API for school basketball — player tracking, "
        "team assignment, possession, passes, interceptions, speed & distance."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_prefix = settings.api_prefix
app.include_router(auth.router, prefix=_prefix)
app.include_router(games.router, prefix=_prefix)
app.include_router(jobs.router, prefix=_prefix)
app.include_router(metrics.router, prefix=_prefix)
app.include_router(organizations.router, prefix=_prefix)
app.include_router(seasons.router, prefix=_prefix)
app.include_router(teams.router, prefix=_prefix)
app.include_router(players.router, prefix=_prefix)
app.include_router(box_scores.router, prefix=_prefix)
app.include_router(game_events.router, prefix=_prefix)
app.include_router(matchups.router, prefix=_prefix)
app.include_router(plays.router, prefix=_prefix)
app.include_router(playbooks.router, prefix=_prefix)
app.include_router(training.router, prefix=_prefix)
app.include_router(annotations.router, prefix=_prefix)
app.include_router(ball_annotations.router, prefix=_prefix)
app.include_router(hoop_annotations.router, prefix=_prefix)
app.include_router(lab.router, prefix=_prefix)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
