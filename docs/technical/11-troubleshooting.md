# Troubleshooting

## Error Catalog

### Backend

| Error | Likely Cause | Fix |
|-------|-------------|-----|
| `asyncpg.exceptions.ConnectionDoesNotExistError` | DB connection lost | Restart API; check PostgreSQL health |
| `alembic.util.exc.CommandError: Can't locate revision` | Missing migration file | Run `alembic upgrade head` inside container |
| `celery.exceptions.MaxRetriesExceededError` | Task failed after retries | Check worker logs; may be GPU OOM or DB issue |
| `403 Forbidden on /api/v1/matchups` | Insufficient role | Check user.role in DB; must be admin or coach |
| `422 Unprocessable Entity` | Pydantic validation fail | Check request body; use `/docs` to validate format |
| `500 Internal Server Error on halftime-resim` | LLM service down | Check `OPENAI_API_KEY` or Ollama availability |
| `S3 connection refused on MinIO upload` | MinIO not running | `docker compose up minio -d` |

### Frontend

| Error | Likely Cause | Fix |
|-------|-------------|-----|
| "Session expired" on every page load | Invalid/expired JWT cookie | Clear cookies and log in again |
| Game Tracker shows "No matchups found" | No matchups in organization | Create a matchup in Game Day |
| Play Builder export PDF is blank | No canvas elements | Add at least one player or arrow before exporting |
| Video overlay canvas not syncing | `requestVideoFrameCallback` not supported | Use Chrome 86+ or Firefox 132+ |
| Training analysis stuck at "analyzing" | GPU worker offline | Restart `basketball-gpu-worker` container |

### Database

| Issue | Fix |
|-------|-----|
| Migration fails: `column already exists` | Migration was partially applied; check `alembic_version` table |
| `JSONB operator does not exist` | SQLite in tests doesn't support JSONB; use PostgreSQL for production |
| Connection pool exhausted | Increase `pool_size` in SQLAlchemy config or reduce concurrent requests |

## Docker Issues

### Container won't start

```bash
docker compose logs <service-name>
```

Look for port conflicts (5432, 6379, 9000, 8000, 4000).

### GPU worker crash on startup

```bash
docker logs basketball-gpu-worker
# Common: "CUDA not available" → Check nvidia-container-toolkit installation
nvidia-smi  # Should show GPU info
```

### MinIO bucket doesn't exist

```bash
# Connect to MinIO console at localhost:9001
# Or via CLI:
docker exec basketball-minio mc alias set local http://localhost:9000 $MINIO_ACCESS_KEY $MINIO_SECRET_KEY
docker exec basketball-minio mc mb local/basketball-iq
```

## Performance Issues

### Slow scouting report generation

- LLM calls can take 10-30 seconds
- Consider switching to a lighter model (`gpt-3.5-turbo` or `llama3:8b`)
- Cache results are stored in DB; re-generating is optional

### High memory usage on GPU worker

- Reduce `--concurrency` to 1 for GPU tasks
- Use smaller YOLOv8 variant (`yolov8n-pose` instead of `yolov8x-pose`)

### Frontend hydration errors in Next.js

Usually caused by server/client HTML mismatch. Check for dynamic content rendered conditionally without `useEffect`. The `CoachModeContext` and `useSearchParams` are properly wrapped in `Suspense` boundaries.
