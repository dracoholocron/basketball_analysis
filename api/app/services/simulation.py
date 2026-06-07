"""Monte Carlo basketball game simulation engine.

Algorithm: possession-by-possession model using team averages.
Each team's offense faces the other team's defense for N possessions per game.
"""
from __future__ import annotations

import math
import random
import statistics
from typing import Any


def simulate_possession(
    fg_pct: float,
    fg3_rate: float,
    fg3_pct: float,
    ft_rate: float,
    ft_pct: float,
    tov_rate: float,
    oreb_rate: float,
) -> float:
    """Simulate a single offensive possession. Returns points scored."""
    if random.random() < tov_rate:
        return 0.0

    if random.random() < oreb_rate and random.random() < fg_pct:
        pass  # second chance handled in next iteration

    if random.random() < fg3_rate:
        if random.random() < fg3_pct:
            return 3.0
        if random.random() < ft_rate * 0.1:
            return sum(1.0 if random.random() < ft_pct else 0.0 for _ in range(3))
        return 0.0
    else:
        if random.random() < fg_pct:
            if random.random() < 0.05:
                bonus = 1.0 if random.random() < ft_pct else 0.0
                return 2.0 + bonus
            return 2.0
        if random.random() < ft_rate * 0.15:
            return sum(1.0 if random.random() < ft_pct else 0.0 for _ in range(2))
        return 0.0


def _extract_rates(stats: dict[str, Any]) -> dict[str, float]:
    """Extract shooting rates from aggregated stats dict."""
    fga = stats.get("avg_fga", 40.0) or 40.0
    fgm = stats.get("avg_fgm", 15.0) or 15.0
    fg3a = stats.get("avg_fg3a", 15.0) or 15.0
    fg3m = stats.get("avg_fg3m", 5.0) or 5.0
    ftm = stats.get("avg_ftm", 10.0) or 10.0
    fta = stats.get("avg_fta", 14.0) or 14.0
    avg_tov = stats.get("avg_tov", 12.0) or 12.0
    avg_oreb = stats.get("avg_reb", 20.0) or 20.0

    return {
        "fg_pct": fgm / fga if fga > 0 else 0.43,
        "fg3_rate": fg3a / fga if fga > 0 else 0.37,
        "fg3_pct": fg3m / fg3a if fg3a > 0 else 0.33,
        "ft_rate": fta / fga if fga > 0 else 0.25,
        "ft_pct": ftm / fta if fta > 0 else 0.72,
        "tov_rate": avg_tov / 70 if avg_tov else 0.15,
        "oreb_rate": avg_oreb / 40 if avg_oreb else 0.25,
    }


def simulate_game(
    own_rates: dict[str, float],
    opp_rates: dict[str, float],
    possessions_per_team: int = 70,
) -> dict[str, Any]:
    """Simulate a single game. Returns score + per-possession features for logistic regression."""
    own_pts_list = [simulate_possession(**own_rates) for _ in range(possessions_per_team)]
    opp_pts_list = [simulate_possession(**opp_rates) for _ in range(possessions_per_team)]

    own_pts = sum(own_pts_list)
    opp_pts = sum(opp_pts_list)

    # Compute realized features for this game
    made_2 = sum(1 for p in own_pts_list if p == 2.0 or (p > 2 and p < 3))
    made_3 = sum(1 for p in own_pts_list if p == 3.0)
    shots = made_2 + made_3
    realized_fg_pct = shots / possessions_per_team if possessions_per_team > 0 else 0
    realized_fg3_pct = made_3 / max(1, round(possessions_per_team * own_rates["fg3_rate"]))
    realized_tov = sum(1 for p in own_pts_list if p == 0.0) / possessions_per_team
    realized_oreb = own_rates["oreb_rate"] * random.gauss(1.0, 0.2)

    opp_made_2 = sum(1 for p in opp_pts_list if p == 2.0 or (p > 2 and p < 3))
    opp_made_3 = sum(1 for p in opp_pts_list if p == 3.0)
    opp_shots = opp_made_2 + opp_made_3
    opp_fg_pct = opp_shots / possessions_per_team if possessions_per_team > 0 else 0

    return {
        "own": own_pts,
        "opp": opp_pts,
        # Features for logistic regression
        "own_fg_pct": realized_fg_pct,
        "own_fg3_pct": realized_fg3_pct,
        "own_tov_rate": realized_tov,
        "own_oreb_rate": max(0.0, realized_oreb),
        "opp_fg_pct": opp_fg_pct,
        "score_diff": own_pts - opp_pts,
    }


def compute_key_drivers(
    runs: list[dict[str, Any]],
    wins: list[int],
) -> list[dict[str, Any]]:
    """Run logistic regression on simulation runs to find real key drivers.

    Returns list of driver dicts sorted by |coefficient| descending.
    Uses pure-Python implementation to avoid sklearn dependency in runtime.
    """
    feature_names = ["own_fg_pct", "own_fg3_pct", "own_tov_rate", "own_oreb_rate", "opp_fg_pct"]

    # Compute means and stds for standardization
    stats: dict[str, dict[str, float]] = {}
    for fn in feature_names:
        vals = [r.get(fn, 0.0) for r in runs]
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / len(vals)
        std = math.sqrt(variance) if variance > 0 else 1.0
        stats[fn] = {"mean": mean, "std": std}

    # Standardize features
    X = []
    for r in runs:
        row = [(r.get(fn, 0.0) - stats[fn]["mean"]) / stats[fn]["std"] for fn in feature_names]
        X.append(row)

    y = wins

    # Simple logistic regression via gradient descent
    n_features = len(feature_names)
    coefs = [0.0] * n_features
    bias = 0.0
    lr = 0.1
    n_epochs = 200

    for _ in range(n_epochs):
        grad_coefs = [0.0] * n_features
        grad_bias = 0.0
        for xi, yi in zip(X, y):
            log_odds = bias + sum(coefs[j] * xi[j] for j in range(n_features))
            pred = 1.0 / (1.0 + math.exp(-max(-500, min(500, log_odds))))
            err = pred - yi
            for j in range(n_features):
                grad_coefs[j] += err * xi[j]
            grad_bias += err
        n = len(X)
        coefs = [coefs[j] - lr * grad_coefs[j] / n for j in range(n_features)]
        bias -= lr * grad_bias / n

    # Build driver list
    drivers = []
    for i, fn in enumerate(feature_names):
        drivers.append({
            "feature_name": fn,
            "coefficient": coefs[i],
            "feature_mean": stats[fn]["mean"],
            "feature_std": stats[fn]["std"],
            "direction": "positive" if coefs[i] > 0 else "negative",
        })

    # Sort by |coefficient| descending
    drivers.sort(key=lambda d: abs(d["coefficient"]), reverse=True)
    return drivers[:6]


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-500, min(500, x))))


def compute_adjusted_win_pct(
    base_log_odds: float,
    active_keys: list[dict[str, Any]],
    target_values: dict[str, float] | None = None,
) -> float:
    """Compute adjusted win probability based on active key toggles.

    Each active key contributes coef * (target - mean) / std to log-odds.
    """
    delta = 0.0
    for key in active_keys:
        coef = key.get("coefficient") or 0.0
        mean = key.get("feature_mean") or 0.0
        std = key.get("feature_std") or 1.0
        fn = key.get("feature_name", "")
        if target_values and fn in target_values:
            target = target_values[fn]
        elif key.get("target_value") is not None:
            target = key["target_value"]
        else:
            # Default: push toward 1 std improvement in the positive direction
            target = mean + std if coef > 0 else mean - std
        delta += coef * (target - mean) / std

    return sigmoid(base_log_odds + delta)


def run_monte_carlo(
    own_stats: dict[str, Any],
    opp_stats: dict[str, Any],
    n_runs: int = 1000,
    possessions: int = 70,
) -> dict[str, Any]:
    """Run n_runs simulated games and return aggregated results + per-run features."""
    own_rates = _extract_rates(own_stats)
    opp_rates = _extract_rates(opp_stats)

    results = [simulate_game(own_rates, opp_rates, possessions) for _ in range(n_runs)]

    own_scores = [r["own"] for r in results]
    opp_scores = [r["opp"] for r in results]
    wins = [1 if r["own"] > r["opp"] else 0 for r in results]
    win_count = sum(wins)

    # Logistic regression on features
    key_drivers = compute_key_drivers(results, wins)

    # Compute base log-odds from win_pct
    win_pct = win_count / n_runs
    win_pct_clamped = max(0.001, min(0.999, win_pct))
    base_log_odds = math.log(win_pct_clamped / (1 - win_pct_clamped))

    # Compact runs_data for storage (only store features, not scores to save space)
    runs_data = [
        {
            "own_fg_pct": round(r.get("own_fg_pct", 0), 4),
            "own_fg3_pct": round(r.get("own_fg3_pct", 0), 4),
            "own_tov_rate": round(r.get("own_tov_rate", 0), 4),
            "own_oreb_rate": round(r.get("own_oreb_rate", 0), 4),
            "opp_fg_pct": round(r.get("opp_fg_pct", 0), 4),
            "win": wins[i],
        }
        for i, r in enumerate(results)
    ]

    return {
        "n_runs": n_runs,
        "win_pct_own": win_pct,
        "win_pct_opp": 1.0 - win_pct,
        "avg_score_own": statistics.mean(own_scores),
        "avg_score_opp": statistics.mean(opp_scores),
        "score_range_own_low": statistics.quantiles(own_scores, n=10)[0],
        "score_range_own_high": statistics.quantiles(own_scores, n=10)[-1],
        "score_range_opp_low": statistics.quantiles(opp_scores, n=10)[0],
        "score_range_opp_high": statistics.quantiles(opp_scores, n=10)[-1],
        "own_rates": own_rates,
        "opp_rates": opp_rates,
        "key_drivers": key_drivers,
        "base_log_odds": base_log_odds,
        "runs_data": runs_data,
    }
