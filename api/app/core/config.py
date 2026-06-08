"""API-level configuration via pydantic-settings."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class APISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://basketball:basketball@db:5432/basketball",
        description="Async SQLAlchemy database URL",
    )

    # Redis (Celery broker + backend)
    redis_url: str = Field(
        default="redis://redis:6379/0",
        description="Redis connection URL",
    )

    # MinIO / S3
    minio_endpoint: str = Field(default="minio:9000")
    # Public endpoint used to rewrite presigned URLs for browser access.
    # Should be set to the hostname:port accessible from the user's browser.
    minio_public_endpoint: str = Field(default="localhost:9000")
    minio_access_key: str = Field(default="minioadmin")
    minio_secret_key: str = Field(default="minioadmin")
    minio_bucket_videos: str = Field(default="videos")
    minio_bucket_outputs: str = Field(default="outputs")
    minio_bucket_stubs: str = Field(default="stubs")
    minio_secure: bool = Field(default=False)

    # Auth
    secret_key: str = Field(
        default="CHANGE_ME_IN_PRODUCTION_USE_STRONG_SECRET",
        description="JWT signing secret — override with BA_SECRET_KEY env var",
    )
    access_token_expire_minutes: int = Field(default=60 * 8)

    # App
    debug: bool = Field(default=False)
    api_prefix: str = Field(default="/api/v1")


settings = APISettings()
