# Runbooks

## Restart All Services

```bash
docker compose restart
```

## Restart Single Service

```bash
docker compose restart api
docker compose restart cpu-worker
docker compose restart gpu-worker
```

## Run Database Migration

```bash
# Check current version
docker exec basketball-api alembic current

# Apply all pending migrations
docker exec basketball-api alembic upgrade head

# Rollback one migration
docker exec basketball-api alembic downgrade -1
```

## Backup PostgreSQL

```bash
# Create backup
docker exec basketball-postgres pg_dump -U postgres basketball > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore from backup
docker exec -i basketball-postgres psql -U postgres basketball < backup_20250101_120000.sql
```

## Backup MinIO Data

```bash
# Using MinIO client
docker exec basketball-minio mc mirror local/basketball-iq /backup/minio/
```

## Scale Workers

```bash
# Add 2 more CPU workers
docker compose up -d --scale cpu-worker=3

# Check worker count
docker compose ps | grep worker
```

## Rotate JWT Secret Key

1. Generate a new key: `openssl rand -hex 32`
2. Update `.env`: `SECRET_KEY=<new-key>`
3. Restart API: `docker compose restart api`
4. **Note**: All existing tokens become invalid; all users must log in again

## Clear Task Queue

```bash
# Flush all pending Celery tasks
docker exec basketball-api celery -A app.worker.celery_app purge -f
```

## View API Logs

```bash
docker logs basketball-api --tail 100 -f
```

## View Worker Logs

```bash
docker logs basketball-cpu-worker --tail 100 -f
docker logs basketball-gpu-worker --tail 100 -f
```

## Healthcheck

```bash
curl http://localhost:8000/health
# Expected: {"status":"ok","database":"connected","version":"..."}
```

## Force-Regenerate Scouting Report

Via API:
```bash
curl -X POST http://localhost:8000/api/v1/matchups/<matchup_id>/scouting-report?force=true \
  -H "Authorization: Bearer <token>"
```

## Reprocess Failed Job

```bash
# In Python/shell
curl -X POST http://localhost:8000/api/v1/games/<game_id>/analyze \
  -H "Authorization: Bearer <token>"
```

## Add a New Admin User

```bash
docker exec basketball-api python -c "
from app.core.database import sync_engine
from app.core.security import hash_password
from app.models.user import User, UserRole
import uuid

with sync_engine.connect() as conn:
    conn.execute(
        'INSERT INTO users (id, email, hashed_password, role, is_active, organization_id) VALUES (...)'
    )
"
# Alternatively use the seed script
docker exec basketball-api python seed.py
```
