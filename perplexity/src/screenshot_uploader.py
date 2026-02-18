from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Optional

import boto3


def upload_screenshot_to_cloud(local_path: str) -> Optional[str]:
    """
    Загружает PNG/JPEG в S3-совместимое хранилище и возвращает публичный URL.

    Требуемые переменные окружения:
        SCREENSHOT_S3_BUCKET
        SCREENSHOT_S3_ACCESS_KEY
        SCREENSHOT_S3_SECRET_KEY
        SCREENSHOT_PUBLIC_URL (https://cdn.example.com/screenshots/)
    Опционально:
        SCREENSHOT_S3_ENDPOINT (для R2/B2)
        SCREENSHOT_S3_REGION
    """

    if not local_path or not Path(local_path).exists():
        return None

    bucket = os.getenv("SCREENSHOT_S3_BUCKET")
    access_key = os.getenv("SCREENSHOT_S3_ACCESS_KEY")
    secret_key = os.getenv("SCREENSHOT_S3_SECRET_KEY")
    public_base = os.getenv("SCREENSHOT_PUBLIC_URL")
    endpoint = os.getenv("SCREENSHOT_S3_ENDPOINT")
    region = os.getenv("SCREENSHOT_S3_REGION")

    if not all([bucket, access_key, secret_key, public_base]):
        return None

    session = boto3.session.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    s3 = session.client("s3", endpoint_url=endpoint)

    key = os.path.basename(local_path)
    content_type, _ = mimetypes.guess_type(local_path)
    extra_args = {
        "ACL": "public-read",
        "ContentType": content_type or "image/png",
    }

    with open(local_path, "rb") as file_obj:
        s3.upload_fileobj(file_obj, bucket, key, ExtraArgs=extra_args)

    return public_base.rstrip("/") + "/" + key


