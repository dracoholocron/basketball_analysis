# Deployment

## Prerequisites

- Docker Engine 24+ and Docker Compose v2
- (Optional for GPU) NVIDIA Container Toolkit and CUDA 12.x drivers
- Minimum 8GB RAM; 16GB+ recommended for GPU worker

## Quick Start

```bash
git clone https://github.com/your-org/basketball-iq.git
cd basketball-iq
cp .env.example .env
# Edit .env with your values (see Environment Variables below)
docker compose up -d
```

Access the app at `http://localhost:4000`.

## Services

```yaml
services:
  postgres:    # Port 5432
  redis:       # Port 6379
  minio:       # Port 9000 (API), 9001 (Console)
  api:         # Port 8000 — FastAPI
  cpu-worker:  # No exposed port — Celery CPU queue
  gpu-worker:  # No exposed port — Celery GPU queue (requires NVIDIA)
  frontend:    # Port 4000 — Next.js
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://user:pass@postgres:5432/basketball` |
| `REDIS_URL` | Yes | `redis://redis:6379/0` |
| `SECRET_KEY` | Yes | JWT signing key (generate with `openssl rand -hex 32`) |
| `ALGORITHM` | No | JWT algorithm, default `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Default `1440` (24 hours) |
| `MINIO_ENDPOINT` | Yes | `minio:9000` |
| `MINIO_ACCESS_KEY` | Yes | MinIO access key |
| `MINIO_SECRET_KEY` | Yes | MinIO secret key |
| `MINIO_BUCKET` | No | Default `basketball-iq` |
| `OPENAI_API_KEY` | No | Required for cloud LLM; omit for Ollama |
| `OPENAI_BASE_URL` | No | Override for Ollama: `http://ollama:11434/v1` |
| `LLM_MODEL` | No | Default `gpt-4o-mini` or `llama3` for Ollama |
| `NEXT_PUBLIC_API_URL` | Yes | Public API URL: `http://localhost:8000` |

## Running Migrations

```bash
docker exec basketball-api alembic upgrade head
```

## Seeding Test Data

```bash
docker exec basketball-api python seed.py
```

## Scaling

To run multiple CPU workers:
```bash
docker compose up -d --scale cpu-worker=3
```

For GPU workers, ensure `nvidia-container-toolkit` is installed and the service has `deploy.resources.reservations.devices` configured.

## Health Checks

- API: `GET /health` → `{"status": "ok"}`
- Database: `GET /health/db` → includes DB connectivity
- MinIO: MinIO console at port 9001
