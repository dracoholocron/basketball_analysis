# Basketball Analytics Platform

Full-court (and half-court) basketball video analysis platform for primary and secondary schools.
Powered by YOLO + ByteTrack + FashionCLIP, served via FastAPI + Celery + Next.js, deployed on Docker Desktop + WSL2 + RTX 5070.

---

## Architecture

```
User → Caddy/Nginx → Next.js Frontend
                  → FastAPI (REST + JWT)
                        → PostgreSQL (metadata + metrics)
                        → Redis (Celery queue)
                        → MinIO (videos, outputs, stubs)
                        → Worker-GPU (Celery + CUDA 12.8)
                              → RTX 5070 (sm_120 Blackwell)
```

## Quick Start (dev)

### Prerequisites
- Docker Desktop with WSL2 backend
- NVIDIA driver ≥ 591 + `nvidia-container-toolkit`
- Git

```bash
# 1. Clone
git clone https://github.com/your-org/basketball_analytics.git
cd basketball_analytics

# 2. Configure secrets
cp .env.example .env
# Edit .env with your passwords / JWT secret

# 3. Start dev stack (no frontend / proxy)
docker compose --profile dev up -d --build

# 4. Run migrations
docker compose exec api alembic upgrade head

# 5. Smoke tests
docker compose exec api python -m pytest tests/smoke -v

# 6. Open API docs
# http://localhost:8000/docs
```

### GPU verification inside container
```bash
docker compose exec worker-gpu nvidia-smi
docker compose exec worker-gpu python -c "import torch; print(torch.cuda.get_device_name(0))"
```

## Models

Place the three `.pt` files into the `basketball_analysis/models/` directory (or the `models_data` Docker volume):
- `player_detector.pt`
- `ball_detector_model.pt`
- `court_keypoint_detector.pt`

### Track A — Dummy models (smoke / E2E tests in 5 minutes)

Downloads `yolov8n.pt` (COCO-general) and wires it as all three models.
Detection quality is low but the **full pipeline runs end-to-end** for tests.

```powershell
# Activate venv first
.\.venv\Scripts\Activate.ps1
.\scripts\build_dummy_models.ps1

# Tell the engine to accept COCO's "sports ball" class
$env:BA_DUMMY_MODELS = "true"
```

### Track B — Real models (train from Roboflow datasets)

Requires a Roboflow API key and ~3-4 hours on an RTX 5070.

```powershell
$env:ROBOFLOW_API_KEY = "your_key_here"
.\scripts\train_models.ps1        # all three models

# Individual models / quick smoke at 5 epochs:
.\scripts\train_models.ps1 -PlayerEpochs 5 -BallEpochs 5 -CourtEpochs 5
```

#### Training time reference — RTX 5070 12 GB

| Model | Dataset | Base model | Epochs | Batch | Estimated time |
|---|---|---|---|---|---|
| `player_detector.pt` | `basketball-players-fy4c2-vfsuv` v17 | `yolov5l6u.pt` | 100 | 8 | ~30–45 min |
| `ball_detector_model.pt` | `basketball-players-fy4c2-vfsuv` v17 | `yolov5l6u.pt` | 250 | auto | ~60–90 min |
| `court_keypoint_detector.pt` | `reloc2-den7l` v1 | `yolov8x-pose.pt` | 500 | 16 | ~60–90 min |
| **Total** | | | | | **~2.5–4 h** |

> **Note**: Player and ball detectors share the same Roboflow dataset
> (`workspace-5ujvu / basketball-players-fy4c2-vfsuv / v17`).  The dataset
> contains both a `Player` class and a `Ball` class, so both models are trained
> on the same download.  The court keypoints model uses a separate pose dataset
> (`fyp-3bwmg / reloc2-den7l / v1`).

Once training is done, unset dummy mode:
```powershell
Remove-Item Env:\BA_DUMMY_MODELS -ErrorAction SilentlyContinue
```

Use the helper script to copy models into the Docker volume:
```powershell
$env:BA_MODELS_SOURCE = "basketball_analysis\models"
.\scripts\fetch_models.ps1
```

## Court Profiles

| Level | Width | Height | Half-court |
|---|---|---|---|
| `nba` | 28.65 m | 15.24 m | No |
| `fiba_juvenil` | 26.0 m | 14.0 m | No |
| `primaria` | 24.0 m | 13.0 m | No |
| `mini_basket` | 22.0 m | 12.0 m | Yes |

Pass `court_level` when creating a game via the API or `--court_level` on the CLI.

## Running Tests

```bash
# Unit tests (no GPU, no models)
pytest tests/unit -m unit

# Integration tests (no GPU, uses synthetic video + stubs)
pytest tests/integration -m integration

# Smoke tests (requires installed packages only)
pytest tests/smoke -m smoke

# E2E (requires running stack)
API_BASE_URL=http://localhost:8000 \
E2E_ADMIN_EMAIL=admin@test.com \
E2E_ADMIN_PASS=password \
E2E_ORG_ID=<uuid> \
pytest tests/e2e -m e2e
```

## GPU Benchmark

```powershell
python bench/run_bench.py `
  --player_model basketball_analysis/models/player_detector.pt `
  --ball_model basketball_analysis/models/ball_detector_model.pt `
  --court_model basketball_analysis/models/court_keypoint_detector.pt `
  --n_frames 100 --batch_size 8 `
  --out bench/report.json `
  --update-baseline
```

#### Baseline — RTX 5070 12 GB (CUDA 12.8) — dummy models (yolov8n)

> **Note**: These numbers are with `yolov8n.pt` (COCO, 3 MB). Real models
> (`yolov5l6u.pt` + `yolov8x-pose.pt`) will be 3-5× slower but more accurate.

| Model | FPS | ms/frame |
|---|---|---|
| `player_detector.pt` (yolov8n) | 540 | 1.85 |
| `ball_detector_model.pt` (yolov8n) | 480 | 2.08 |
| `court_keypoint_detector.pt` (yolov8n-pose) | 446 | 2.24 |

After training real models, re-run with `--update-baseline` to store accurate numbers.

## SSH Deployment

```powershell
# On the Windows server
ssh user@your-server
cd C:\srv\basketball_platform

.\scripts\deploy.ps1 -Profile prod
```

## PyTorch / GPU Compatibility

The RTX 5070 uses Blackwell architecture (sm_120) and requires:
- PyTorch ≥ 2.7 with CUDA 12.8
- Install via: `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128`
- The worker Docker image (`pytorch/pytorch:2.7.0-cuda12.8-cudnn9-runtime`) ships the correct build.

## Project Structure

```
.
├── basketball_analysis/    # Core CV engine (YOLO + tracking + tactics)
│   ├── main.py             # CLI entry point & run_pipeline() function
│   ├── configs/            # Settings (pydantic-settings) + court profiles
│   ├── trackers/           # PlayerTracker, BallTracker
│   ├── team_assigner/      # TeamAssigner v2 (CLIP + HSV + majority vote)
│   ├── ball_aquisition/    # BallAquisitionDetector
│   ├── pass_and_interception_detector/
│   ├── tactical_view_converter/    # Homography + CourtProfile
│   ├── speed_and_distance_calculator/
│   ├── court_keypoint_detector/
│   ├── drawers/            # 8 cv2 overlay drawers
│   └── utils/              # video, bbox, stubs, court_mode_detector
├── api/                    # FastAPI service
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/        # auth, games, jobs, metrics, organizations, seasons, teams, players
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── schemas/        # Pydantic schemas
│   │   ├── services/       # storage (MinIO)
│   │   └── worker/         # Celery tasks
│   └── alembic/            # DB migrations
├── worker/                 # GPU worker Dockerfile
├── frontend/               # Next.js 14 + Tailwind + Recharts
├── tests/
│   ├── smoke/              # Import checks + /health
│   ├── unit/               # bbox, stubs, ball_acquisition, speed, homography
│   ├── integration/        # Synthetic video pipeline regression
│   └── e2e/                # HTTP full-flow tests
├── bench/                  # GPU FPS benchmark
├── scripts/                # deploy.ps1, fetch_models.ps1, build_dummy_models.ps1, train_models.ps1, seed.py
├── docker-compose.yml      # Multi-service stack (dev + prod profiles)
├── Caddyfile               # Reverse proxy config
└── .env.example
```
