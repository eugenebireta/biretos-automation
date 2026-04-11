"""cloud_uploader.py — S3-compatible cloud uploader for catalog photo assets.

Supports any S3-compatible storage (AWS S3, MinIO, Yandex Object Storage,
Selectel, Cloudflare R2, etc.) via boto3 with custom endpoint_url.

Safe by default: if credentials or bucket not configured, runs in dry-run
mode and returns predictable placeholder URLs. Never uploads silently.

Environment variables:
    S3_ENDPOINT_URL     — e.g. https://storage.yandexcloud.net
    S3_BUCKET_NAME      — e.g. biretos-catalog
    S3_ACCESS_KEY       — access key id
    S3_SECRET_KEY       — secret access key
    S3_REGION           — optional, e.g. ru-central1 (default: us-east-1)
    S3_PUBLIC_BASE_URL  — optional, e.g. https://cdn.biretos.ru
                          If set, public URL = {base}/{object_key}
                          If not set, uses {endpoint}/{bucket}/{key}
    S3_DRY_RUN          — "true" forces dry run even with credentials set

Usage:
    from cloud_uploader import S3Uploader
    uploader = S3Uploader.from_env()
    result = uploader.upload_file(local_path, object_key)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class UploadResult:
    """Result of a single upload operation."""
    object_key: str
    local_path: str
    upload_mode: str      # "dry_run" | "uploaded" | "error"
    public_url: str = ""
    error: str = ""
    size_kb: int = 0


class S3Uploader:
    """S3-compatible uploader with safe dry-run default."""

    def __init__(
        self,
        *,
        endpoint_url: str = "",
        bucket_name: str = "",
        access_key: str = "",
        secret_key: str = "",
        region: str = "us-east-1",
        public_base_url: str = "",
        dry_run: bool = True,
    ):
        self.endpoint_url = endpoint_url.rstrip("/")
        self.bucket_name = bucket_name
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.public_base_url = public_base_url.rstrip("/")
        self.dry_run = dry_run
        self._client = None

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "S3Uploader":
        """Create uploader from environment variables.

        Falls back to dry-run if any required credential is missing.
        """
        if env_file:
            try:
                from dotenv import load_dotenv
                load_dotenv(env_file)
            except ImportError:
                pass

        endpoint = os.environ.get("S3_ENDPOINT_URL", "").strip()
        bucket = os.environ.get("S3_BUCKET_NAME", "").strip()
        access = os.environ.get("S3_ACCESS_KEY", "").strip()
        secret = os.environ.get("S3_SECRET_KEY", "").strip()
        region = os.environ.get("S3_REGION", "us-east-1").strip()
        base_url = os.environ.get("S3_PUBLIC_BASE_URL", "").strip()
        force_dry = os.environ.get("S3_DRY_RUN", "").strip().lower() in ("true", "1", "yes")

        has_creds = bool(endpoint and bucket and access and secret)

        if force_dry or not has_creds:
            if not has_creds:
                log.info("S3 credentials not fully configured — using dry-run mode")
            else:
                log.info("S3_DRY_RUN=true — forced dry-run mode")
            return cls(dry_run=True, bucket_name=bucket or "dry-run-bucket",
                       public_base_url=base_url)

        return cls(
            endpoint_url=endpoint,
            bucket_name=bucket,
            access_key=access,
            secret_key=secret,
            region=region,
            public_base_url=base_url,
            dry_run=False,
        )

    @property
    def mode(self) -> str:
        return "dry_run" if self.dry_run else "live"

    def _get_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
            )
        return self._client

    def _build_public_url(self, object_key: str) -> str:
        """Build public URL for the uploaded object."""
        if self.public_base_url:
            return f"{self.public_base_url}/{object_key}"
        if self.endpoint_url:
            return f"{self.endpoint_url}/{self.bucket_name}/{object_key}"
        return f"https://{self.bucket_name}.s3.amazonaws.com/{object_key}"

    def _build_dry_run_url(self, object_key: str) -> str:
        """Build predictable placeholder URL for dry-run mode."""
        if self.public_base_url:
            return f"{self.public_base_url}/{object_key}"
        return f"https://{self.bucket_name}.example.com/{object_key}"

    def upload_file(
        self,
        local_path: str | Path,
        object_key: str,
        content_type: str = "image/jpeg",
    ) -> UploadResult:
        """Upload a single file. Returns UploadResult."""
        local = Path(local_path)
        size_kb = int(local.stat().st_size / 1024) if local.exists() else 0

        if not local.exists():
            return UploadResult(
                object_key=object_key,
                local_path=str(local),
                upload_mode="error",
                error=f"file_not_found: {local}",
            )

        if self.dry_run:
            url = self._build_dry_run_url(object_key)
            log.debug(f"WOULD UPLOAD {local.name} → {object_key}")
            return UploadResult(
                object_key=object_key,
                local_path=str(local),
                upload_mode="dry_run",
                public_url=url,
                size_kb=size_kb,
            )

        try:
            client = self._get_client()
            extra_args = {"ContentType": content_type}
            client.upload_file(
                str(local),
                self.bucket_name,
                object_key,
                ExtraArgs=extra_args,
            )
            url = self._build_public_url(object_key)
            log.info(f"UPLOADED {local.name} → {object_key}")
            return UploadResult(
                object_key=object_key,
                local_path=str(local),
                upload_mode="uploaded",
                public_url=url,
                size_kb=size_kb,
            )
        except Exception as e:
            log.error(f"UPLOAD FAILED {local.name}: {e}")
            return UploadResult(
                object_key=object_key,
                local_path=str(local),
                upload_mode="error",
                error=str(e),
                size_kb=size_kb,
            )

    def upload_batch(
        self,
        items: list[tuple[str | Path, str]],
    ) -> list[UploadResult]:
        """Upload a batch of (local_path, object_key) pairs."""
        return [self.upload_file(path, key) for path, key in items]
