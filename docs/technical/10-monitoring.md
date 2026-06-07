# Monitoring

## Health Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Basic liveness check |
| `GET /health/db` | Database connectivity check |

Example healthy response:
```json
{"status": "ok", "database": "connected", "version": "1.0.0"}
```

## Logs

### API Logs

```bash
# Follow live
docker logs basketball-api -f

# Last 500 lines
docker logs basketball-api --tail 500

# Filter for errors
docker logs basketball-api 2>&1 | grep -i error
```

Log format: `[TIMESTAMP] [LEVEL] [PATH] [STATUS] [DURATION]`

### Worker Logs

```bash
docker logs basketball-cpu-worker -f
docker logs basketball-gpu-worker -f
```

## Celery Monitoring (Flower)

Add Flower to `docker-compose.yml` for a web-based task monitor:

```yaml
flower:
  image: mher/flower
  command: celery flower --broker=redis://redis:6379/0
  ports:
    - "5555:5555"
  depends_on:
    - redis
```

Access at `http://localhost:5555`.

## Database Metrics

Check active connections:
```sql
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';
```

Check table sizes:
```sql
SELECT
  schemaname, tablename,
  pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC;
```

## MinIO Metrics

View storage usage in MinIO Console (`http://localhost:9001`):
- Buckets → basketball-iq → Usage

## Alerting

For production deployments, configure alerts on:
- API health check failures (check every 30s)
- Worker queue depth > 50 tasks
- GPU worker offline for > 5 minutes
- Database connection failures

Use tools like Prometheus + Grafana, Datadog, or simple cron-based `curl` health checks.

## Log Retention

By default, Docker logs are stored on the host. For production:
```yaml
# docker-compose.yml
logging:
  driver: "json-file"
  options:
    max-size: "100m"
    max-file: "5"
```

Or route to a centralized log service (CloudWatch, Papertrail, Loki).
