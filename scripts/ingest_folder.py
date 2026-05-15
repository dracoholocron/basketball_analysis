"""
Batch ingest script — queue all .mp4 / .avi / .mov videos in a folder as games.

Usage:
    python scripts/ingest_folder.py \\
        --folder "C:\\videos\\input" \\
        --season-id <UUID> \\
        --court-level fiba_juvenil \\
        [--api-url http://localhost:8000] \\
        [--email admin@test.com] \\
        [--password Test1234!] \\
        [--jersey1 "white shirt"] \\
        [--jersey2 "dark blue shirt"] \\
        [--dry-run]

After queueing, run with --poll to wait and print final statuses.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("httpx is required: pip install httpx")
    sys.exit(1)

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def login(client: httpx.Client, email: str, password: str) -> str:
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def create_game(client: httpx.Client, token: str, payload: dict) -> dict:
    resp = client.post(
        "/api/v1/games",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


def upload_video(client: httpx.Client, token: str, game_id: str, video_path: Path) -> dict:
    with video_path.open("rb") as f:
        resp = client.post(
            f"/api/v1/games/{game_id}/video",
            files={"file": (video_path.name, f, "video/mp4")},
            headers={"Authorization": f"Bearer {token}"},
            timeout=300.0,
        )
    resp.raise_for_status()
    return resp.json()


def get_job(client: httpx.Client, token: str, job_id: str) -> dict:
    resp = client.get(
        f"/api/v1/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


def poll_all(client: httpx.Client, token: str, jobs: list[dict], interval: int = 15) -> None:
    print("\nPolling job statuses (Ctrl+C to stop)...")
    pending = {j["job_id"]: j for j in jobs}
    while pending:
        time.sleep(interval)
        done_ids = []
        for job_id, info in pending.items():
            try:
                job = get_job(client, token, job_id)
                status = job["status"]
                pct = job.get("progress_pct", 0)
                stage = job.get("current_stage", "")
                print(f"  [{info['video']}] {status} {pct}% — {stage}")
                if status in ("done", "failed"):
                    done_ids.append(job_id)
                    if status == "done":
                        print(f"    DONE -> game {info['game_id']}")
                    else:
                        print(f"    FAILED: {job.get('error_message', 'unknown error')}")
            except Exception as exc:
                print(f"  [{info['video']}] poll error: {exc}")
        for j in done_ids:
            del pending[j]
    print("\nAll jobs finished.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch ingest videos from a folder")
    parser.add_argument("--folder", required=True, help="Path to folder with video files")
    parser.add_argument("--season-id", required=True, help="Season UUID (from seed or admin UI)")
    parser.add_argument("--court-level", default="fiba_juvenil",
                        choices=["nba", "fiba_juvenil", "primaria", "mini_basket"])
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--email", default="admin@test.com")
    parser.add_argument("--password", default="Test1234!")
    parser.add_argument("--jersey1", default="white shirt", help="Team 1 jersey description")
    parser.add_argument("--jersey2", default="dark blue shirt", help="Team 2 jersey description")
    parser.add_argument("--is-half-court", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="List videos without uploading")
    parser.add_argument("--poll", action="store_true", help="Wait and poll until all jobs finish")
    parser.add_argument("--out", default=None, help="Write queued job info to JSON file")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"ERROR: folder not found: {folder}")
        sys.exit(1)

    videos = sorted([p for p in folder.iterdir() if p.suffix.lower() in VIDEO_EXTS])
    if not videos:
        print(f"No video files found in {folder}")
        sys.exit(0)

    print(f"Found {len(videos)} video(s) in {folder}:")
    for v in videos:
        size_mb = v.stat().st_size / 1_048_576
        print(f"  {v.name}  ({size_mb:.1f} MB)")

    if args.dry_run:
        print("\nDry run — no uploads performed.")
        return

    print(f"\nLogging in to {args.api_url} as {args.email}…")
    client = httpx.Client(base_url=args.api_url, timeout=60.0)
    try:
        token = login(client, args.email, args.password)
        print("  Authenticated OK")
    except Exception as exc:
        print(f"  Login failed: {exc}")
        sys.exit(1)

    queued: list[dict] = []
    for video in videos:
        print(f"\nProcessing: {video.name}")
        try:
            game = create_game(client, token, {
                "season_id": args.season_id,
                "location": video.stem,
                "court_level": args.court_level,
                "is_half_court": args.is_half_court,
                "home_team1_jersey": args.jersey1,
                "away_team2_jersey": args.jersey2,
            })
            print(f"  Created game: {game['id']}")
            job = upload_video(client, token, game["id"], video)
            print(f"  Queued job:   {job['id']}  (status: {job['status']})")
            queued.append({
                "video": video.name,
                "game_id": game["id"],
                "job_id": job["id"],
                "status": job["status"],
            })
        except httpx.HTTPStatusError as exc:
            print(f"  HTTP error: {exc.response.status_code} — {exc.response.text[:200]}")
        except Exception as exc:
            print(f"  Error: {exc}")

    print(f"\n{len(queued)}/{len(videos)} video(s) queued successfully.")

    if args.out:
        Path(args.out).write_text(json.dumps(queued, indent=2))
        print(f"Job info written to {args.out}")

    if args.poll and queued:
        poll_all(client, token, queued)
    else:
        print("\nTip: re-run with --poll to wait for results, or check http://localhost:3000/jobs")


if __name__ == "__main__":
    main()
