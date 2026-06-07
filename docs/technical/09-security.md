# Security

## Authentication

- **JWT tokens** signed with `SECRET_KEY` using `HS256` algorithm
- Tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default 24 hours)
- No refresh token mechanism currently — users re-authenticate after expiry
- Passwords hashed with **bcrypt** (via `passlib`)

## Authorization (Role-Based Access Control)

Four roles:
| Role | Permissions |
|------|-------------|
| `admin` | Full access to all endpoints and admin panel |
| `coach` | Read/write game data, simulations, scouting, plays |
| `analyst` | Read-only on game data, write on reports |
| `viewer` | Read-only on non-sensitive pages |

Roles are enforced via the `require_role(*roles)` dependency injected into FastAPI routes.

## Multi-Tenancy

- Each user belongs to an **organization**
- All data is scoped by `organization_id`
- Users can only access resources within their organization
- The `get_current_user` dependency automatically injects `organization_id` for filtering

Example:
```python
async def list_matchups(db, current_user=Depends(get_current_user)):
    result = await db.execute(
        select(Matchup).where(Matchup.organization_id == current_user.organization_id)
    )
```

## CORS

The FastAPI app is configured with CORS middleware:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # from env var
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

In production, set `ALLOWED_ORIGINS` to your specific frontend domain.

## Secrets Management

- All secrets passed via environment variables (never hardcoded)
- `.env` file is gitignored
- In production, use Docker secrets or a secret manager (AWS Secrets Manager, HashiCorp Vault)

## MinIO Security

- MinIO bucket is **private** (not public)
- Video URLs are generated as **presigned URLs** with 1-hour expiry
- Access credentials stored in environment variables

## API Key Recommendations

- Rotate `SECRET_KEY` every 90 days
- Use a dedicated service account for MinIO (not root credentials)
- Set `OPENAI_API_KEY` with minimal scopes if using OpenAI

## Known Limitations

- No MFA (multi-factor authentication) — planned for future release
- Session invalidation requires token expiry (no blacklist mechanism)
- Admin users have organization-wide access but not cross-organization
