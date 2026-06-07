"""LLM service adapter for scouting reports and game key generation.

Supports OpenAI API (and OpenAI-compatible servers like Ollama).
Configure via environment variables:
    LLM_PROVIDER: openai | ollama (default: ollama)
    LLM_BASE_URL: base URL (default: http://localhost:11434/v1 for ollama)
    LLM_API_KEY: API key (default: "ollama" for local)
    LLM_MODEL: model name (default: qwen2.5:7b for ollama, gpt-4o for openai)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _get_client():
    """Return an OpenAI-compatible client based on environment config."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise RuntimeError(
            "openai package is required for LLM features. "
            "Install it with: pip install openai"
        )

    provider = os.getenv("LLM_PROVIDER", "ollama").lower()

    if provider == "openai":
        return AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY", ""),
        )
    else:
        # Ollama (or any OpenAI-compatible local server)
        return AsyncOpenAI(
            base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.getenv("LLM_API_KEY", "ollama"),
        )


def _get_model() -> str:
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider == "openai":
        return os.getenv("LLM_MODEL", "gpt-4o")
    return os.getenv("LLM_MODEL", "qwen2.5:7b")


async def generate_scouting_report(
    matchup_name: str,
    own_team_name: str,
    opponent_team_name: str,
    opponent_stats: dict[str, Any],
    video_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a scouting report using the LLM.

    Returns a dict with keys: team_identity, strengths, weaknesses,
    mvp_players, game_keys_offensive, game_keys_defensive.
    """
    client = _get_client()
    model = _get_model()

    video_section = ""
    if video_metrics:
        video_section = f"""
Video Analysis Data (measured by computer vision):
{json.dumps(video_metrics, indent=2)}
"""

    prompt = f"""You are an expert basketball coach analyst. Generate a scouting report for the following matchup.

Matchup: {matchup_name}
Our Team: {own_team_name}
Opponent: {opponent_team_name}

Opponent Statistics:
{json.dumps(opponent_stats, indent=2)}
{video_section}

Return a JSON object with these exact keys (no markdown, pure JSON):
{{
  "team_identity": "2-3 sentence description of their playing style and identity",
  "strengths": ["strength 1", "strength 2", "strength 3", "strength 4"],
  "weaknesses": ["weakness 1", "weakness 2", "weakness 3"],
  "mvp_players": [
    {{"name": "Player Name", "jersey": "#X", "summary": "Why they're dangerous and how to guard them"}},
    {{"name": "Player Name", "jersey": "#X", "summary": "..."}},
    {{"name": "Player Name", "jersey": "#X", "summary": "..."}}
  ],
  "game_keys_offensive": [
    "Offensive key 1",
    "Offensive key 2",
    "Offensive key 3"
  ],
  "game_keys_defensive": [
    "Defensive key 1",
    "Defensive key 2",
    "Defensive key 3"
  ]
}}"""

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1500,
        )
        content = response.choices[0].message.content or "{}"
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content)
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        return {
            "team_identity": f"Scouting report generation failed: {e}",
            "strengths": [],
            "weaknesses": [],
            "mvp_players": [],
            "game_keys_offensive": [],
            "game_keys_defensive": [],
        }


async def generate_keys_to_victory(
    simulation_summary: dict[str, Any],
    matchup_name: str,
) -> list[dict[str, Any]]:
    """Generate Keys to Victory from simulation results."""
    client = _get_client()
    model = _get_model()

    prompt = f"""You are an expert basketball analyst. Based on the following Monte Carlo simulation results for {matchup_name}, generate 5-6 actionable Keys to Victory.

Simulation Results:
{json.dumps(simulation_summary, indent=2)}

Return a JSON array of keys (no markdown, pure JSON):
[
  {{
    "title": "Short title (max 6 words)",
    "description": "Actionable description of what the team needs to do",
    "target_metric": "metric_name",
    "target_value": 0.0,
    "weight": 0.8
  }}
]

weight is 0-1 indicating how impactful this key is to winning.
target_metric should be one of: fg_pct, fg3_pct, reb, ast, tov, pts, pace
target_value is the target number/percentage to achieve."""

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000,
        )
        content = response.choices[0].message.content or "[]"
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content)
    except Exception as e:
        logger.error(f"Keys generation failed: {e}")
        return []


async def generate_halftime_adjustments(
    pre_game_keys: list[dict],
    h1_stats: dict,
    h2_projected: dict,
    win_pct_change: float,
    coach_mode: bool = False,
) -> list[dict]:
    """Generate 2-3 halftime adjustments based on H1 performance vs pre-game plan."""
    client = _get_client()
    model = _get_model()

    tone_instruction = ""
    if coach_mode:
        tone_instruction = "\nUSE HUDDLE-SPEAK: short imperative phrases, no technical jargon, no decimals. Each adjustment ≤ 5 words."

    prompt = f"""You are a basketball coach giving halftime adjustments. Based on first-half performance vs the pre-game plan, give 2-3 SHORT actionable adjustments.{tone_instruction}

Pre-game Keys to Victory:
{json.dumps(pre_game_keys, indent=2)}

First Half Stats:
{json.dumps(h1_stats, indent=2)}

Win probability change: {win_pct_change:+.1%}

Return a JSON array (no markdown, pure JSON):
[
  {{
    "adjustment": "SHORT imperative sentence",
    "rationale": "1 sentence why",
    "priority": "HIGH"
  }}
]

priority is HIGH/MEDIUM/LOW. Focus on what is most impactful for the second half."""

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=600,
        )
        content = (response.choices[0].message.content or "[]").strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content)
    except Exception as e:
        logger.error(f"Halftime adjustments generation failed: {e}")
        return [
            {"adjustment": "Protect the ball", "rationale": "Minimize turnovers in the second half.", "priority": "HIGH"},
            {"adjustment": "Attack the glass", "rationale": "Win the rebounding battle to extend possessions.", "priority": "MEDIUM"},
        ]


async def generate_situational_adjustments(
    matchup_name: str,
    scouting_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate If→Then situational adjustments via LLM."""
    client = _get_client()
    model = _get_model()

    prompt = f"""You are an expert basketball head coach. For the matchup "{matchup_name}", generate 6-8 concrete situational adjustments based on the scouting context.

Scouting Context:
{json.dumps(scouting_context, indent=2)}

Return a JSON array (no markdown, pure JSON):
[
  {{
    "situation": "If they run pick-and-roll with their center",
    "adjustment": "Then drop the big to take away the roll and trust your guard on the pop",
    "priority": 1
  }}
]

priority is 1 (highest) to 8 (lowest). Focus on real game situations: defensive sets, offensive schemes, late-game scenarios, special situations."""

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=1200,
        )
        content = response.choices[0].message.content or "[]"
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content)
    except Exception as e:
        logger.error(f"Situational adjustments generation failed: {e}")
        return []
