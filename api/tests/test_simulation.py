"""Monte Carlo simulation unit + endpoint tests."""
from __future__ import annotations

import math
import pytest
from httpx import AsyncClient

from app.services.simulation import run_monte_carlo, compute_key_drivers, sigmoid


def test_monte_carlo_unit_empty_stats():
    """Simulation with no stats should return reasonable defaults."""
    result = run_monte_carlo({}, {}, n_runs=100)
    assert 0.0 <= result["win_pct_own"] <= 1.0
    assert 0.0 <= result["win_pct_opp"] <= 1.0
    assert abs(result["win_pct_own"] + result["win_pct_opp"] - 1.0) < 0.01
    assert result["avg_score_own"] > 0
    assert result["avg_score_opp"] > 0
    assert result["n_runs"] == 100


def test_monte_carlo_unit_with_stats():
    """Higher-scoring team should win more often on average (statistical test)."""
    strong = {"avg_fgm": 35.0, "avg_fga": 70.0, "avg_fg3m": 12.0, "avg_fg3a": 30.0,
              "avg_ftm": 18.0, "avg_fta": 22.0, "avg_tov": 10.0, "avg_reb": 35.0}
    weak = {"avg_fgm": 22.0, "avg_fga": 65.0, "avg_fg3m": 6.0, "avg_fg3a": 22.0,
            "avg_ftm": 10.0, "avg_fta": 15.0, "avg_tov": 16.0, "avg_reb": 25.0}
    result = run_monte_carlo(strong, weak, n_runs=2000)
    # Stronger team should win more than 55% of the time with a clear advantage
    assert result["win_pct_own"] > 0.55


def test_monte_carlo_returns_key_drivers():
    """run_monte_carlo should return key_drivers from logistic regression."""
    result = run_monte_carlo({}, {}, n_runs=200)
    assert "key_drivers" in result
    assert isinstance(result["key_drivers"], list)
    assert len(result["key_drivers"]) > 0
    driver = result["key_drivers"][0]
    assert "feature_name" in driver
    assert "coefficient" in driver
    assert "feature_mean" in driver
    assert "feature_std" in driver
    assert isinstance(driver["coefficient"], float)


def test_compute_key_drivers_deterministic():
    """When one feature perfectly predicts wins, it should have the highest coefficient."""
    import random
    random.seed(42)

    n = 500
    # Create synthetic data: own_fg_pct perfectly correlates with wins
    runs = []
    wins = []
    for i in range(n):
        own_fg_pct = random.uniform(0.3, 0.6)
        win = 1 if own_fg_pct > 0.45 else 0
        runs.append({
            "own_fg_pct": own_fg_pct,
            "own_fg3_pct": random.uniform(0.25, 0.45),
            "own_tov_rate": random.uniform(0.1, 0.2),
            "own_oreb_rate": random.uniform(0.15, 0.35),
            "opp_fg_pct": random.uniform(0.35, 0.50),
        })
        wins.append(win)

    drivers = compute_key_drivers(runs, wins)
    assert len(drivers) > 0
    # own_fg_pct should have the largest absolute coefficient
    assert drivers[0]["feature_name"] == "own_fg_pct"
    assert abs(drivers[0]["coefficient"]) > 0.5


def test_sigmoid_values():
    assert abs(sigmoid(0) - 0.5) < 0.001
    assert sigmoid(100) > 0.99
    assert sigmoid(-100) < 0.01


def test_monte_carlo_returns_runs_data():
    """run_monte_carlo should persist compact runs_data."""
    result = run_monte_carlo({}, {}, n_runs=50)
    assert "runs_data" in result
    assert len(result["runs_data"]) == 50
    run = result["runs_data"][0]
    assert "win" in run
    assert "own_fg_pct" in run


def test_monte_carlo_returns_base_log_odds():
    result = run_monte_carlo({}, {}, n_runs=200)
    assert "base_log_odds" in result
    assert isinstance(result["base_log_odds"], float)
    # sigmoid(base_log_odds) should match win_pct_own approximately
    reconstructed = sigmoid(result["base_log_odds"])
    assert abs(reconstructed - result["win_pct_own"]) < 0.05


@pytest.mark.asyncio
async def test_simulate_endpoint_no_matchup(client: AsyncClient, auth_headers: dict):
    import uuid
    resp = await client.post(
        f"/api/v1/matchups/{uuid.uuid4()}/simulate",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_simulate_endpoint(client: AsyncClient, auth_headers: dict, monkeypatch):
    """Simulate endpoint with LLM mocked to avoid openai dependency."""
    import app.services.llm as llm_module

    async def _mock_keys(*args, **kwargs):
        return [{"title": "Key 1", "description": "Test key", "weight": 0.8,
                 "target_metric": "fg_pct", "target_value": 0.45}]

    monkeypatch.setattr(llm_module, "generate_keys_to_victory", _mock_keys)

    create_resp = await client.post(
        "/api/v1/matchups",
        json={"name": "Sim Matchup Mocked"},
        headers=auth_headers,
    )
    matchup_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/matchups/{matchup_id}/simulate",
        params={"n_runs": 100},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "win_pct_own" in data
    assert "keys" in data
    assert len(data["keys"]) > 0


@pytest.mark.skip(reason="keys-impact endpoint not implemented")
@pytest.mark.asyncio
async def test_keys_impact_endpoint(client: AsyncClient, auth_headers: dict, monkeypatch):
    """Keys-impact endpoint should return mathematically adjusted win probability."""
    import app.services.llm as llm_module

    async def _mock_keys(*args, **kwargs):
        return [{"title": "FG% Key", "description": "Shoot well", "weight": 0.8,
                 "target_metric": "own_fg_pct", "target_value": 0.55}]

    monkeypatch.setattr(llm_module, "generate_keys_to_victory", _mock_keys)

    create_resp = await client.post(
        "/api/v1/matchups",
        json={"name": "Keys Impact Matchup"},
        headers=auth_headers,
    )
    matchup_id = create_resp.json()["id"]

    sim_resp = await client.post(
        f"/api/v1/matchups/{matchup_id}/simulate",
        params={"n_runs": 200},
        headers=auth_headers,
    )
    assert sim_resp.status_code == 200
    keys = sim_resp.json()["keys"]
    active_ids = [k["id"] for k in keys]

    impact_resp = await client.post(
        f"/api/v1/matchups/{matchup_id}/keys-impact",
        json={"active_key_ids": active_ids},
        headers=auth_headers,
    )
    assert impact_resp.status_code == 200
    data = impact_resp.json()
    assert "adjusted_win_pct" in data
    assert 0.0 <= data["adjusted_win_pct"] <= 1.0
    assert "delta_log_odds" in data


@pytest.mark.asyncio
async def test_halftime_resim_endpoint(client: AsyncClient, auth_headers: dict, monkeypatch):
    """Halftime resim should work when game events exist."""
    import app.services.llm as llm_module

    async def _mock_keys(*args, **kwargs):
        return [{"title": "Key 1", "description": "Test", "weight": 0.7}]

    monkeypatch.setattr(llm_module, "generate_keys_to_victory", _mock_keys)

    # Create matchup
    create_resp = await client.post(
        "/api/v1/matchups",
        json={"name": "Halftime Matchup"},
        headers=auth_headers,
    )
    matchup_id = create_resp.json()["id"]

    # Add some events
    for i in range(5):
        await client.post(
            f"/api/v1/matchups/{matchup_id}/events",
            json={"event_type": "2pt_made", "team": 1, "points": 2},
            headers=auth_headers,
        )
    for i in range(3):
        await client.post(
            f"/api/v1/matchups/{matchup_id}/events",
            json={"event_type": "2pt_made", "team": 2, "points": 2},
            headers=auth_headers,
        )

    resp = await client.post(
        f"/api/v1/matchups/{matchup_id}/halftime-resim",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "win_pct_own" in data
    assert 0.0 <= data["win_pct_own"] <= 1.0



def test_monte_carlo_unit_empty_stats():
    """Simulation with no stats should return reasonable defaults."""
    result = run_monte_carlo({}, {}, n_runs=100)
    assert 0.0 <= result["win_pct_own"] <= 1.0
    assert 0.0 <= result["win_pct_opp"] <= 1.0
    assert abs(result["win_pct_own"] + result["win_pct_opp"] - 1.0) < 0.01
    assert result["avg_score_own"] > 0
    assert result["avg_score_opp"] > 0
    assert result["n_runs"] == 100


def test_monte_carlo_unit_with_stats():
    """Higher-scoring team should win more often on average (statistical test)."""
    strong = {"avg_fgm": 35.0, "avg_fga": 70.0, "avg_fg3m": 12.0, "avg_fg3a": 30.0,
              "avg_ftm": 18.0, "avg_fta": 22.0, "avg_tov": 10.0, "avg_reb": 35.0}
    weak = {"avg_fgm": 22.0, "avg_fga": 65.0, "avg_fg3m": 6.0, "avg_fg3a": 22.0,
            "avg_ftm": 10.0, "avg_fta": 15.0, "avg_tov": 16.0, "avg_reb": 25.0}
    result = run_monte_carlo(strong, weak, n_runs=2000)
    # Stronger team should win more than 55% of the time with a clear advantage
    assert result["win_pct_own"] > 0.55


@pytest.mark.asyncio
async def test_simulate_endpoint_no_matchup(client: AsyncClient, auth_headers: dict):
    import uuid
    resp = await client.post(
        f"/api/v1/matchups/{uuid.uuid4()}/simulate",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_simulate_endpoint(client: AsyncClient, auth_headers: dict, monkeypatch):
    """Simulate endpoint with LLM mocked to avoid openai dependency."""
    import app.services.llm as llm_module

    async def _mock_keys(*args, **kwargs):
        return [{"title": "Key 1", "description": "Test key", "weight": 0.8,
                 "target_metric": "fg_pct", "target_value": 0.45}]

    monkeypatch.setattr(llm_module, "generate_keys_to_victory", _mock_keys)

    create_resp = await client.post(
        "/api/v1/matchups",
        json={"name": "Sim Matchup Mocked"},
        headers=auth_headers,
    )
    matchup_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/matchups/{matchup_id}/simulate",
        params={"n_runs": 100},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "win_pct_own" in data
    assert "keys" in data
    assert len(data["keys"]) > 0
