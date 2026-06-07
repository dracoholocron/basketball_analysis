# API Reference

## Interactive Docs

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

All endpoints require a Bearer token obtained from `POST /api/v1/auth/token`.

## Base URL

```
http://localhost:8000/api/v1
```

## Authentication

```http
POST /auth/token
Content-Type: application/x-www-form-urlencoded

username=coach@team.com&password=yourpassword
```

Returns `{ "access_token": "...", "token_type": "bearer" }`.

Include in all requests:
```http
Authorization: Bearer <access_token>
```

## Key Endpoints

### Matchups

| Method | Path | Description |
|--------|------|-------------|
| GET | `/matchups` | List all matchups |
| POST | `/matchups` | Create matchup |
| GET | `/matchups/upcoming` | Upcoming matchups sorted by date |
| GET | `/matchups/{id}` | Get matchup detail |
| DELETE | `/matchups/{id}` | Delete matchup |
| PATCH | `/matchups/{id}/clock` | Update game clock state |
| PATCH | `/matchups/{id}/timeouts` | Update timeout usage |
| GET | `/matchups/{id}/prep-status` | 5-step weekly prep progress |
| GET | `/matchups/{id}/simulation` | Latest simulation for matchup |
| POST | `/matchups/{id}/simulate` | Run Monte Carlo simulation |
| GET | `/matchups/{id}/scouting-report` | Get scouting report |
| POST | `/matchups/{id}/scouting-report` | Generate scouting report |
| GET | `/matchups/{id}/situational-adjustments` | List If→Then adjustments |
| POST | `/matchups/{id}/situational-adjustments` | Generate adjustments |
| GET | `/matchups/{id}/live-keys-status` | Real-time key status |
| POST | `/matchups/{id}/halftime-resim` | Halftime Monte Carlo + LLM adjustments |
| GET | `/matchups/{id}/event-heatmap` | Shot heatmap and stats |
| PATCH | `/matchups/{id}/notes` | Update game plan notes |

### Game Events

| Method | Path | Description |
|--------|------|-------------|
| GET | `/matchups/{id}/events` | List events (paginated) |
| POST | `/matchups/{id}/events` | Create game event |
| DELETE | `/matchups/{id}/events/{event_id}` | Delete event |

### Keys to Victory

| Method | Path | Description |
|--------|------|-------------|
| PATCH | `/keys/{key_id}` | Toggle key active/inactive |
| PATCH | `/keys/{key_id}/priority` | Set/unset as priority (max 3) |
| POST | `/matchups/{id}/keys-impact` | Calculate adjusted win pct |

### Plays

| Method | Path | Description |
|--------|------|-------------|
| GET | `/plays` | List plays (filters: category, pace, matchup_id) |
| POST | `/plays` | Create play |
| GET | `/plays/{id}` | Get play |
| PUT | `/plays/{id}` | Update play (auto-sets v2 if frames key present) |
| DELETE | `/plays/{id}` | Delete play |
| POST | `/plays/import-pdf` | Import play from PDF file upload |

### Jobs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/jobs` | List analysis jobs |
| GET | `/jobs/{id}` | Get job detail |
| GET | `/jobs/{id}/tracks` | Presigned URL for tracks JSONL |
| GET | `/jobs/{id}/source-video` | Presigned URL for source video |

### Training Sessions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/training-sessions` | List sessions |
| POST | `/training-sessions` | Create session |
| GET | `/training-sessions/{id}` | Get session detail |
| DELETE | `/training-sessions/{id}` | Delete session |
| POST | `/training-sessions/{id}/upload` | Upload video clip |
| POST | `/training-sessions/{id}/analyze` | Enqueue pose analysis |
| GET | `/training-sessions/{id}/keypoints` | Get pose keypoints |
| GET | `/training-sessions/{id}/metrics` | Get shooting form metrics |

## Pagination

Most list endpoints accept `skip` and `limit` query params:
```
GET /matchups?skip=0&limit=20
```

## Error Responses

| Status | Meaning |
|--------|---------|
| 400 | Bad request (validation error or business rule violation) |
| 401 | Missing or invalid auth token |
| 403 | Insufficient role permissions |
| 404 | Resource not found |
| 422 | Pydantic validation error (check request body) |
| 500 | Internal server error (check logs) |
