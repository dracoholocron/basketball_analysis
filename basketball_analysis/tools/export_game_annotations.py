#!/usr/bin/env python3
"""Export a game's manual annotations (ball clicks, hoop boxes, court landmarks,
team exemplars, jerseys, names) from the local dev DB to ONE JSON file, so the
pipeline can be run standalone elsewhere (e.g. a RunPod GPU benchmark) with the
exact same inputs the worker would use.

Runs on the HOST next to the dev docker-compose stack (shells `docker compose
exec db psql`). Usage:

  python basketball_analysis/tools/export_game_annotations.py --game <game_id> \\
      --out annotations.json
"""
from __future__ import annotations

import argparse
import json
import subprocess


def _psql(sql: str, db_user: str, db_name: str) -> str:
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "db",
         "psql", "-U", db_user, "-d", db_name, "-t", "-A", "-c", sql],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def _json_or_none(raw: str):
    raw = (raw or "").strip()
    if not raw or raw == "null":
        return None
    return json.loads(raw)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True, help="game UUID")
    ap.add_argument("--out", default="annotations.json")
    ap.add_argument("--db-user", default="basketball")
    ap.add_argument("--db-name", default="basketball")
    args = ap.parse_args()
    g = args.game

    def q(sql: str) -> str:
        return _psql(sql, args.db_user, args.db_name)

    data = {
        "game_id": g,
        "ball_points": _json_or_none(
            q(f"SELECT points::text FROM ball_annotations WHERE game_id='{g}'")),
        "hoop_boxes": _json_or_none(
            q(f"SELECT hoops::text FROM hoop_annotations WHERE game_id='{g}'")),
        "manual_landmarks": _json_or_none(
            q(f"SELECT landmarks::text FROM game_annotations WHERE game_id='{g}'")),
        "camera_motion": q(
            f"SELECT COALESCE(camera_motion,'static') FROM game_annotations WHERE game_id='{g}'"
        ) or "static",
        "team_exemplars": _json_or_none(
            q(f"SELECT team_exemplars::text FROM game_annotations WHERE game_id='{g}'")),
        "team1_jersey": q(
            f"SELECT home_team1_jersey FROM games WHERE id='{g}'") or "white shirt",
        "team2_jersey": q(
            f"SELECT away_team2_jersey FROM games WHERE id='{g}'") or "dark blue shirt",
        "team1_name": q(
            f"SELECT t.name FROM teams t JOIN games gm ON gm.home_team_id=t.id WHERE gm.id='{g}'") or None,
        "team2_name": q(
            f"SELECT t.name FROM teams t JOIN games gm ON gm.away_team_id=t.id WHERE gm.id='{g}'") or None,
    }

    with open(args.out, "w") as f:
        json.dump(data, f, indent=1)

    print(f"Wrote {args.out}:")
    for k, v in data.items():
        n = len(v) if isinstance(v, (list, dict)) else v
        print(f"  {k}: {n}")


if __name__ == "__main__":
    main()
