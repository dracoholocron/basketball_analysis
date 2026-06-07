# LLM Integration

## Overview

The platform uses Large Language Models (LLMs) for three features:
1. **Scouting Reports** — analyze opponent box score stats
2. **Situational Adjustments** — generate If→Then game plan rules
3. **Halftime Adjustments** — generate locker-room adjustments at halftime

## Configuration

| Environment Variable | Description |
|---------------------|-------------|
| `OPENAI_API_KEY` | API key for OpenAI cloud (leave empty for Ollama) |
| `OPENAI_BASE_URL` | Base URL override (use `http://ollama:11434/v1` for local) |
| `LLM_MODEL` | Model name: `gpt-4o-mini` (cloud), `llama3` or `mistral` (local) |

## Using Ollama (Local LLM)

```bash
# Pull and run Ollama
docker run -d --name ollama -p 11434:11434 ollama/ollama
docker exec ollama ollama pull llama3

# Set in .env:
OPENAI_BASE_URL=http://ollama:11434/v1
OPENAI_API_KEY=ollama  # dummy value
LLM_MODEL=llama3
```

## LLM Service (`api/app/services/llm.py`)

### `generate_scouting_report(opponent_stats, matchup_name, own_stats)`

Generates a structured scouting report. Output:
```json
{
  "tldr": "...",
  "key_tendencies": ["...", "..."],
  "player_spotlights": [{"name": "...", "note": "..."}],
  "vulnerabilities": ["...", "..."],
  "recommendations": ["...", "..."]
}
```

### `generate_situational_adjustments(scouting_report, own_strengths)`

Generates 3-5 If→Then coaching rules. Output:
```json
[
  {"situation": "Opponent goes on a 6-0 run", "adjustment": "Call timeout...", "priority": 1}
]
```

### `generate_halftime_adjustments(pre_game_keys, h1_stats, h2_projected, win_pct_change, coach_mode)`

Generates 2-3 halftime adjustments. Parameters:
- `pre_game_keys`: list of Keys to Victory dicts
- `h1_stats`: first-half stats dict
- `win_pct_change`: delta since pre-game simulation
- `coach_mode`: if True, generates short huddle-speak without rationale

Output:
```json
[
  {"adjustment": "Push the pace", "rationale": "Transition efficiency is high", "priority": "HIGH"}
]
```

## Fallback Behavior

All LLM calls are wrapped in try/except. On failure:
- Scouting report: returns a generic template
- Adjustments: returns empty list (UI shows "Generate with AI" button)
- Halftime: returns empty list (UI skips adjustment section)

The app is fully functional without a working LLM — it just won't show AI-generated text.

## Prompt Engineering Notes

- Prompts include explicit JSON output instructions with schema validation
- Temperature: 0.3-0.5 (lower = more consistent, less creative)
- Max tokens: 1000-2000 depending on endpoint
- System prompts include basketball coaching context
