"""
MinIO / S3-compatible storage service.

Buckets:
- videos:   raw uploaded videos
- outputs:  annotated output videos
- stubs:    pipeline stub cache files
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import BinaryIO

import boto3
from botocore.exceptions import ClientError

from ..core.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=f"{'https' if settings.minio_secure else 'http'}://{settings.minio_endpoint}",
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
        )
        self._ensure_buckets()

    def _ensure_buckets(self) -> None:
        for bucket in [
            settings.minio_bucket_videos,
            settings.minio_bucket_outputs,
            settings.minio_bucket_stubs,
        ]:
            try:
                self._client.head_bucket(Bucket=bucket)
            except ClientError:
                self._client.create_bucket(Bucket=bucket)
                logger.info("Created bucket: %s", bucket)

    def upload_file(
        self,
        file_obj: BinaryIO,
        bucket: str,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        self._client.upload_fileobj(
            file_obj,
            bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        logger.debug("Uploaded s3://%s/%s", bucket, key)
        return key

    def upload_local_file(self, local_path: str, bucket: str, key: str) -> str:
        with open(local_path, "rb") as f:
            return self.upload_file(f, bucket, key)

    def download_file(self, bucket: str, key: str, dest_path: str) -> None:
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(bucket, key, dest_path)
        logger.debug("Downloaded s3://%s/%s → %s", bucket, key, dest_path)

    def get_presigned_url(
        self,
        bucket: str,
        key: str,
        expiry: int = 3600,
        public: bool = False,
    ) -> str:
        """Generate a presigned GET URL.

        When *public=True*, the internal docker hostname in the URL is replaced
        with ``settings.minio_public_endpoint`` so the URL is reachable from
        outside the Docker network (e.g. a browser).
        """
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiry,
        )
        if public:
            url = url.replace(
                settings.minio_endpoint,
                settings.minio_public_endpoint,
                1,
            )
        return url

    def delete_object(self, bucket: str, key: str) -> None:
        self._client.delete_object(Bucket=bucket, Key=key)


# Module-level singleton
_storage: StorageService | None = None


def get_storage() -> StorageService:
    global _storage
    if _storage is None:
        _storage = StorageService()
    return _storage
