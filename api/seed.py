"""
Idempotent database seed script.

Creates:
  - Organization  "Test School"      (slug: test-school)
  - User          admin@test.com     (role: admin)
  - Season        "2026"
  - Team          "Home Team"        (white shirt)
  - Team          "Away Team"        (dark blue shirt)

Run inside the api container:
    docker compose exec api python scripts/seed.py

Or locally (needs BA_DATABASE_URL pointing to a running DB):
    python scripts/seed.py

All credentials can be overridden via env vars:
    SEED_ADMIN_EMAIL, SEED_ADMIN_PASS, SEED_ORG_NAME, SEED_ORG_SLUG
"""
from __future__ import annotations

import asyncio
import os
import sys

# Allow running from repo root, scripts/ or api/ directory
_here = os.path.dirname(os.path.abspath(__file__))
# When run from scripts/, the api app is one level up
for _candidate in [
    os.path.join(_here, "..", "api"),   # scripts/seed.py -> ../api
    _here,                               # api/seed.py -> already in api/
]:
    _candidate = os.path.abspath(_candidate)
    if os.path.isdir(os.path.join(_candidate, "app")):
        sys.path.insert(0, _candidate)
        break

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings as api_settings
from app.core.security import hash_password
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.season import Season
from app.models.team import Team

# --------------------------------------------------------------------------- #
# Seed parameters (overridable via env vars)
# --------------------------------------------------------------------------- #
ADMIN_EMAIL = os.environ.get("SEED_ADMIN_EMAIL", "admin@test.com")
ADMIN_PASS = os.environ.get("SEED_ADMIN_PASS", "Test1234!")
ORG_NAME = os.environ.get("SEED_ORG_NAME", "Test School")
ORG_SLUG = os.environ.get("SEED_ORG_SLUG", "test-school")


async def seed() -> None:
    engine = create_async_engine(api_settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # ── Organization ────────────────────────────────────────────────────
        result = await db.execute(
            select(Organization).where(Organization.slug == ORG_SLUG)
        )
        org = result.scalar_one_or_none()
        if org is None:
            org = Organization(name=ORG_NAME, slug=ORG_SLUG)
            db.add(org)
            await db.flush()
            print(f"[+] Created Organization  '{org.name}'  id={org.id}")
        else:
            print(f"[=] Organization exists   '{org.name}'  id={org.id}")

        # ── Admin user ──────────────────────────────────────────────────────
        result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                organization_id=org.id,
                email=ADMIN_EMAIL,
                hashed_password=hash_password(ADMIN_PASS),
                full_name="Admin User",
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(user)
            await db.flush()
            print(f"[+] Created User          '{user.email}'  id={user.id}")
        else:
            print(f"[=] User exists           '{user.email}'  id={user.id}")

        # ── Season ──────────────────────────────────────────────────────────
        result = await db.execute(
            select(Season).where(
                Season.organization_id == org.id, Season.year == "2026"
            )
        )
        season = result.scalar_one_or_none()
        if season is None:
            season = Season(
                organization_id=org.id,
                name="Season 2026",
                year="2026",
            )
            db.add(season)
            await db.flush()
            print(f"[+] Created Season        '{season.name}'  id={season.id}")
        else:
            print(f"[=] Season exists         '{season.name}'  id={season.id}")

        # ── Teams ────────────────────────────────────────────────────────────
        for team_name, jersey_desc in [
            ("Home Team", "white shirt"),
            ("Away Team", "dark blue shirt"),
        ]:
            result = await db.execute(
                select(Team).where(
                    Team.organization_id == org.id, Team.name == team_name
                )
            )
            team = result.scalar_one_or_none()
            if team is None:
                team = Team(
                    organization_id=org.id,
                    name=team_name,
                    jersey_description=jersey_desc,
                    level="secundaria",
                )
                db.add(team)
                await db.flush()
                print(f"[+] Created Team          '{team.name}'  id={team.id}")
            else:
                print(f"[=] Team exists           '{team.name}'  id={team.id}")

        await db.commit()

    print()
    print("─" * 60)
    print("Seed complete. Use these values in E2E tests / curl commands:")
    print(f"  ADMIN_EMAIL    = {ADMIN_EMAIL}")
    print(f"  ADMIN_PASS     = {ADMIN_PASS}")
    print(f"  ORG_ID         = {org.id}")
    print(f"  SEASON_ID      = {season.id}")
    print("─" * 60)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
