"""Manual E2E validation script — upload video, poll job to completion."""
import httpx, time, sys, os

BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")
EMAIL = os.environ.get("E2E_ADMIN_EMAIL", "admin@test.com")
PASS = os.environ.get("E2E_ADMIN_PASS", "Test1234!")
ORG_ID = os.environ.get("E2E_ORG_ID", "44d4cc94-7bdf-427e-b093-8a7aad958acb")
VIDEO = os.environ.get("E2E_VIDEO", "samples/test_clip.mp4")

token_r = httpx.post(f"{BASE}/api/v1/auth/token", data={"username": EMAIL, "password": PASS})
assert token_r.status_code == 200, f"Login failed: {token_r.text}"
TOKEN = token_r.json()["access_token"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# Create season
s = httpx.post(
    f"{BASE}/api/v1/seasons",
    json={"organization_id": ORG_ID, "name": "Manual E2E 2026", "year": "2026"},
    headers=HEADERS,
)
season_id = s.json()["id"]
print(f"Season: {season_id}")

# Create game
g = httpx.post(
    f"{BASE}/api/v1/games",
    json={"season_id": season_id, "court_level": "primaria", "is_half_court": False},
    headers=HEADERS,
)
game_id = g.json()["id"]
print(f"Game: {game_id}")

# Upload video
with open(VIDEO, "rb") as f:
    r = httpx.post(
        f"{BASE}/api/v1/games/{game_id}/video",
        files={"file": ("test.mp4", f, "video/mp4")},
        headers=HEADERS,
        timeout=30,
    )
assert r.status_code == 202, f"Upload failed: {r.text}"
job_id = r.json()["id"]
print(f"Job: {job_id}  status: {r.json()['status']}")

# Poll
for i in range(120):
    time.sleep(5)
    j = httpx.get(f"{BASE}/api/v1/jobs/{job_id}", headers=HEADERS).json()
    status = j["status"]
    stage = j.get("current_stage", "?")
    pct = j.get("progress_pct", "?")
    print(f"  [{(i+1)*5}s] status={status} stage={stage} progress={pct}%")
    if status in ("done", "failed"):
        if status == "failed":
            print(f"ERROR: {j.get('error_message', '')}")
            sys.exit(1)
        print("\nJob DONE!")
        break
else:
    print("Timeout after 10 minutes")
    sys.exit(1)

# Fetch metrics
m = httpx.get(f"{BASE}/api/v1/games/{game_id}/metrics", headers=HEADERS)
print(f"\nMetrics status: {m.status_code}")
if m.status_code == 200:
    import json
    print(json.dumps(m.json(), indent=2)[:500])
else:
    print(m.text[:200])
