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
from botocore.client import Config
from botocore.exceptions import ClientError

from ..core.config import settings

logger = logging.getLogger(__name__)

# Path-style addressing (bucket in the path, not the host) — required for MinIO and for
# a public S3 domain (virtual-host style would become bucket.s3.domain, which breaks).
_S3_CONFIG = Config(s3={"addressing_style": "path"})


class StorageService:
    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=f"{'https' if settings.minio_secure else 'http'}://{settings.minio_endpoint}",
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            config=_S3_CONFIG,
        )
        # Separate client bound to the PUBLIC endpoint, used only to SIGN browser-facing
        # presigned URLs so the signature matches the host the browser actually hits.
        # Falls back to the internal client when no distinct public endpoint is set.
        if settings.minio_public_endpoint and settings.minio_public_endpoint != settings.minio_endpoint:
            self._public_client = boto3.client(
                "s3",
                endpoint_url=f"{'https' if settings.minio_public_secure else 'http'}://{settings.minio_public_endpoint}",
                aws_access_key_id=settings.minio_access_key,
                aws_secret_access_key=settings.minio_secret_key,
                config=_S3_CONFIG,
            )
        else:
            self._public_client = self._client
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

    def upload_bytes(
        self,
        data: bytes,
        bucket: str,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        return self.upload_file(io.BytesIO(data), bucket, key, content_type=content_type)

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

        When *public=True*, the URL is signed with the PUBLIC-endpoint client so it is
        reachable from a browser AND its SigV4 signature is valid for that host (no
        fragile host string-replacement, which breaks the signature over HTTPS/a domain).
        """
        client = self._public_client if public else self._client
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiry,
        )

    def delete_object(self, bucket: str, key: str) -> None:
        self._client.delete_object(Bucket=bucket, Key=key)

    # ── Multipart upload (browser-direct, bypasses the 100MB tunnel request cap) ──
    # The browser uploads each part with a presigned PUT straight to the PUBLIC
    # endpoint (one request < part_size < 100MB). On completion the API gathers the
    # part ETags itself via list_parts (server-side state keyed by UploadId), so the
    # browser never needs to read the cross-origin ETag header (avoids a CORS
    # expose-headers dependency).
    def create_multipart_upload(
        self,
        bucket: str,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        resp = self._client.create_multipart_upload(
            Bucket=bucket, Key=key, ContentType=content_type
        )
        return resp["UploadId"]

    def presign_upload_part(
        self,
        bucket: str,
        key: str,
        upload_id: str,
        part_number: int,
        expiry: int = 3600,
    ) -> str:
        """Presigned PUT URL for one part, signed for the PUBLIC endpoint/host."""
        return self._public_client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": bucket,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=expiry,
        )

    def list_parts(self, bucket: str, key: str, upload_id: str) -> list[dict]:
        """Return uploaded parts as [{'PartNumber': n, 'ETag': '...'}], sorted."""
        parts: list[dict] = []
        marker = 0
        while True:
            resp = self._client.list_parts(
                Bucket=bucket, Key=key, UploadId=upload_id, PartNumberMarker=marker
            )
            for p in resp.get("Parts", []):
                parts.append({"PartNumber": p["PartNumber"], "ETag": p["ETag"]})
            if resp.get("IsTruncated"):
                marker = resp["NextPartNumberMarker"]
            else:
                break
        parts.sort(key=lambda x: x["PartNumber"])
        return parts

    def complete_multipart_upload(
        self,
        bucket: str,
        key: str,
        upload_id: str,
        parts: list[dict] | None = None,
    ) -> None:
        """Complete the upload. When *parts* is None the ETags are fetched server-side."""
        if parts is None:
            parts = self.list_parts(bucket, key, upload_id)
        if not parts:
            raise ValueError("No uploaded parts found for this multipart upload")
        self._client.complete_multipart_upload(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )

    def abort_multipart_upload(self, bucket: str, key: str, upload_id: str) -> None:
        try:
            self._client.abort_multipart_upload(
                Bucket=bucket, Key=key, UploadId=upload_id
            )
        except ClientError as exc:
            logger.warning("abort_multipart_upload failed for %s: %s", key, exc)


# Module-level singleton
_storage: StorageService | None = None


def get_storage() -> StorageService:
    global _storage
    if _storage is None:
        _storage = StorageService()
    return _storage
