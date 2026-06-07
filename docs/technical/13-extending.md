# Extending the Platform

## Adding a New API Endpoint

1. **Create or update the router file** in `api/app/routers/`
2. **Add Pydantic schemas** (request/response models) at the top of the router or in `api/app/schemas/`
3. **Add ORM logic** using `AsyncSession` with `select()` statements
4. **Register the router** in `api/app/main.py`:
   ```python
   from .routers import my_new_router
   app.include_router(my_new_router.router, prefix=_prefix)
   ```
5. **Write tests** in `api/tests/test_my_feature.py`
6. **Add the frontend API function** in `frontend/src/lib/api.ts`

## Adding a New Database Model

1. **Create the model** in `api/app/models/my_model.py`:
   ```python
   from sqlalchemy.orm import Mapped, mapped_column
   from ..core.database import Base
   
   class MyModel(Base):
       __tablename__ = "my_models"
       id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
       name: Mapped[str] = mapped_column(String(200), nullable=False)
   ```

2. **Export it** from `api/app/models/__init__.py`

3. **Create an Alembic migration**:
   ```bash
   docker exec basketball-api alembic revision --autogenerate -m "add_my_model"
   docker exec basketball-api alembic upgrade head
   ```

4. **Write the CRUD router and schemas**

## Adding a New Sport Type

1. Add the sport name as an option in the game config UI (Play Builder, Game Tracker matchup config)
2. Update `SPORT_CONFIGS` dict in the frontend (if applicable) with period count and time
3. Optionally add sport-specific event types to `SHOT_TYPES` in the Game Tracker

## Adding a New Key Type (Metric Target)

`metric_targets` in `KeyToVictory` is a JSONB field with flexible schema:
```json
[
  {"type": "per_team", "metric": "three_point_attempts", "target": 25, "compare": "lt"},
  {"type": "per_player", "player_jersey": "23", "metric": "points", "target": 20, "compare": "gt"}
]
```

To add a new metric type:
1. Add the metric name to the `METRIC_NAMES` lookup in the live keys computation (`get_live_keys_status`)
2. Update `buildLiveStats()` in the game event processing to compute the new metric
3. Update the Event Heatmap page to display the new metric type

## Adding a Celery Task

1. Add the task function to `api/app/worker/tasks.py` (CPU) or `api/app/worker/gpu_tasks.py` (GPU):
   ```python
   @celery_app.task(bind=True, name="app.worker.tasks.my_new_task")
   def my_new_task(self, param: str):
       # task logic
       pass
   ```

2. If routing to GPU queue, add to `task_routes` in `celery_app.py`

3. Enqueue from a router:
   ```python
   my_new_task.apply_async(args=[param_value], queue="default")
   ```

## Adding a New Page (Frontend)

1. Create `frontend/src/app/my-page/page.tsx` with `"use client"` directive
2. Wrap with `AppShell` for consistent layout
3. Add auth guard: redirect to `/login` on 401 errors
4. Add to sidebar `NAV_ITEMS` in `frontend/src/components/layout/Sidebar.tsx`
5. Add Playwright E2E test in `frontend/tests/e2e/`

## Environment Variable Pattern

Never hardcode values. Always use:
```python
# Backend
from ..core.config import settings
value = settings.MY_SETTING

# Frontend
const value = process.env.NEXT_PUBLIC_MY_SETTING
```

Add new backend settings to `api/app/core/config.py` (Pydantic Settings class).
Add frontend env vars to `.env.local` (must start with `NEXT_PUBLIC_` to be browser-accessible).
