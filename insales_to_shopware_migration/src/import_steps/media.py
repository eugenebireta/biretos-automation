from __future__ import annotations

import io
import os
import uuid
from typing import Any, Dict, List

import requests
from PIL import Image

from clients import ShopwareClient, ShopwareClientError
from import_steps import ProductImportState, StepState

MAX_MEDIA_SIZE = int(0.95 * 1024 * 1024)  # ~0.95 MB to satisfy nginx 1 MB cap


def run(
    client: ShopwareClient,
    registry: Any,
    snapshot_product: Dict[str, Any],
    state: ProductImportState,
    context: Dict[str, Any],
) -> ProductImportState:
    images: List[Dict[str, Any]] = snapshot_product.get("images") or []
    if not images:
        state.set_step("media", StepState.SUCCESS, "No images in snapshot")
        return state

    dry_run: bool = context.get("dry_run", True)
    max_media: int = context.get("max_media", 10)

    if dry_run:
        state.set_step("media", StepState.SUCCESS, f"Dry-run: images={len(images)}")
        return state

    if not state.product_id:
        state.set_step("media", StepState.ERROR, "product_id missing after skeleton")
        return state

    deleted_media = client.delete_all_product_media(state.product_id)
    media_folder_id = context.get("media_folder_id") or client.get_product_media_folder_id()
    product_media_ids: List[str] = []

    for position, image in enumerate(images[:max_media]):
        url = (
            image.get("original_url")
            or image.get("url")
            or image.get("external_id")
        )
        if not url:
            continue

        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            state.errors.append(f"MEDIA: failed to download {url}: {exc}")
            continue

        filename = _generate_filename(state.sku, position, url)
        content = resp.content
        content_type = resp.headers.get("Content-Type", "image/jpeg")

        compressed = _compress_image(content, force=True)
        if compressed:
            content = compressed
            content_type = "image/jpeg"

        media_id = client.create_media(media_folder_id)
        try:
            _upload_with_retry(client, media_id, content, filename, content_type)
            product_media_id = client.create_product_media(state.product_id, media_id, position=position)
            if product_media_id:
                product_media_ids.append(product_media_id)
        except Exception as exc:
            state.errors.append(f"MEDIA: upload error {filename}: {exc}")

    if product_media_ids:
        client.set_product_cover(state.product_id, product_media_ids[0])
        detail = f"Images uploaded: {len(product_media_ids)}"
        if deleted_media:
            detail = f"{detail}, deleted old: {deleted_media}"
        state.set_step("media", StepState.SUCCESS, detail)
    else:
        state.set_step("media", StepState.FALSE, "Failed to upload images")

    return state


def _generate_filename(sku: str, position: int, url: str) -> str:
    base = os.path.basename(url.split("?")[0]) or "image.jpg"
    _, ext = os.path.splitext(base)
    if not ext:
        ext = ".jpg"
    return f"{sku}_{position}_{uuid.uuid4().hex}{ext}"


def _compress_image(content: bytes, max_attempts: int = 6, force: bool = False) -> bytes | None:
    if not force and len(content) <= MAX_MEDIA_SIZE:
        return None
    try:
        image = Image.open(io.BytesIO(content))
    except Exception:
        return None

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    elif image.mode == "RGBA":
        image = image.convert("RGB")

    quality = 90
    width, height = image.size

    for _ in range(max_attempts):
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        data = buffer.getvalue()
        if len(data) <= MAX_MEDIA_SIZE:
            return data
        if quality > 50:
            quality -= 10
        else:
            width = max(1, int(width * 0.8))
            height = max(1, int(height * 0.8))
            image = image.resize((width, height), Image.LANCZOS)

    return None


def _upload_with_retry(
    client: ShopwareClient,
    media_id: str,
    content: bytes,
    filename: str,
    content_type: str,
) -> None:
    try:
        client.upload_media_blob(media_id, content, filename, content_type=content_type)
        return
    except ShopwareClientError as exc:
        message = str(exc)
        if "CONTENT__MEDIA_DUPLICATED_FILE_NAME" in message:
            new_name = f"{uuid.uuid4().hex}_{filename}"
            client.upload_media_blob(media_id, content, new_name, content_type=content_type)
            return
        if "Request Entity Too Large" in message:
            compressed = _compress_image(content, max_attempts=8, force=True)
            if compressed:
                client.upload_media_blob(media_id, compressed, filename, content_type="image/jpeg")
                return
        raise
