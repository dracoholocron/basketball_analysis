"""CPU-bound Celery tasks — Monte Carlo simulation."""
from __future__ import annotations

import asyncio
import uuid as _uuid

from .celery_app import celery_app


@celery_app.task(bind=True, name="app.worker.cpu_tasks.run_simulation_task", queue="cpu")
def run_simulation_task(self, matchup_id: str, n_runs: int = 1000) -> dict:
    """Run Monte Carlo simulation async. Wraps the async endpoint logic in a sync Celery task."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select

    from ..core.config import settings
    from ..models.matchup import Matchup
    from ..models.simulation import GameSimulation, KeyToVictory
    from ..services import simulation as sim_engine
    from ..services.llm import generate_keys_to_victory
    from ..routers.matchups import _get_team_stats

    async def _run() -> dict:
        engine = create_async_engine(settings.database_url, echo=False)
        SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

        async with SessionLocal() as db:
            matchup_uuid = _uuid.UUID(matchup_id)
            matchup = await db.get(Matchup, matchup_uuid)
            if matchup is None:
                return {"error": "Matchup not found"}

            own_stats: dict = {}
            opp_stats: dict = {}
            if matchup.own_team_id:
                own_stats = await _get_team_stats(db, matchup.own_team_id)
            if matchup.opponent_team_id:
                opp_stats = await _get_team_stats(db, matchup.opponent_team_id)

            data_source = "real" if (own_stats or opp_stats) else "default"
            results = sim_engine.run_monte_carlo(own_stats, opp_stats, n_runs=min(n_runs, 5000))

            sim = GameSimulation(
                matchup_id=matchup_uuid,
                n_runs=results["n_runs"],
                win_pct_own=results["win_pct_own"],
                win_pct_opp=results["win_pct_opp"],
                avg_score_own=results["avg_score_own"],
                avg_score_opp=results["avg_score_opp"],
                score_range_own_low=results["score_range_own_low"],
                score_range_own_high=results["score_range_own_high"],
                score_range_opp_low=results["score_range_opp_low"],
                score_range_opp_high=results["score_range_opp_high"],
                key_drivers=results.get("key_drivers"),
                base_log_odds=results.get("base_log_odds"),
                runs_data=results.get("runs_data"),
            )
            db.add(sim)
            await db.flush()

            key_drivers = results.get("key_drivers", [])
            keys_data = await generate_keys_to_victory(
                simulation_summary={
                    "win_pct_own": results["win_pct_own"],
                    "avg_score_own": results["avg_score_own"],
                    "avg_score_opp": results["avg_score_opp"],
                    "data_source": data_source,
                    "own_rates": results.get("own_rates", {}),
                    "opp_rates": results.get("opp_rates", {}),
                    "own_stats": own_stats,
                    "opp_stats": opp_stats,
                    "key_drivers": key_drivers,
                },
                matchup_name=matchup.name,
            )

            for i, key in enumerate(keys_data[:6]):
                driver = key_drivers[i] if i < len(key_drivers) else {}
                k = KeyToVictory(
                    simulation_id=sim.id,
                    title=key.get("title", f"Key {i+1}"),
                    description=key.get("description"),
                    target_metric=key.get("target_metric") or driver.get("feature_name"),
                    target_value=key.get("target_value"),
                    weight=abs(driver.get("coefficient", key.get("weight", 1.0))),
                    active=True,
                    order=i,
                    feature_name=driver.get("feature_name"),
                    coefficient=driver.get("coefficient"),
                    feature_mean=driver.get("feature_mean"),
                    feature_std=driver.get("feature_std"),
                )
                db.add(k)

            await db.commit()
            return {
                "simulation_id": str(sim.id),
                "win_pct_own": results["win_pct_own"],
                "win_pct_opp": results["win_pct_opp"],
            }

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()
