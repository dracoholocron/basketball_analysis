# Local Development

## Requirements

- Windows 10/11 with WSL2, or Linux/macOS
- Python 3.11
- Node.js 20
- Docker Desktop (for PostgreSQL, Redis, MinIO)

## WSL2 Setup (Windows)

```bash
# In PowerShell as Admin
wsl --install
wsl --set-default-version 2

# After reboot, in WSL2 Ubuntu terminal:
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip
```

## Python Backend Setup

```bash
cd api/
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start infrastructure
docker compose up postgres redis minio -d

# Run migrations
alembic upgrade head

# Start API
uvicorn app.main:app --reload --port 8000
```

## Frontend Setup

```bash
cd frontend/
node --version  # should be 20.x
npm install
npm run dev     # starts on port 4000
```

## GPU Worker (Linux only)

```bash
# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker

# Install ultralytics
pip install ultralytics

# Start GPU worker
celery -A app.worker.celery_app worker -Q gpu --concurrency 1
```

## Running Tests

```bash
# Backend (in api/)
pytest

# Frontend E2E (requires running app)
cd frontend/
npm run test:e2e
```

## Environment

Copy `.env.example` to `.env` and set:
- `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/basketball`
- `REDIS_URL=redis://localhost:6379/0`
- `MINIO_ENDPOINT=localhost:9000`
- `SECRET_KEY=<generate with openssl rand -hex 32>`

## Port Reference

| Service | Port |
|---------|------|
| Next.js frontend | 4000 |
| FastAPI backend | 8000 |
| PostgreSQL | 5432 |
| Redis | 6379 |
| MinIO API | 9000 |
| MinIO Console | 9001 |
