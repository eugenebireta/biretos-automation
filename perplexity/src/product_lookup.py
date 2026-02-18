"""
Высокоуровневая обертка вокруг PerplexityClient для получения данных о продукте.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from dotenv import load_dotenv

from .page_screenshot import screenshot_product_page
from .perplexity_client import PerplexityClient
from .reliable_photo_finder import ReliablePhotoFinder
from .screenshot_uploader import upload_screenshot_to_cloud


_ENV_LOADED = False


def _ensure_env_loaded() -> None:
    global _ENV_LOADED  # noqa: PLW0603 - простая защита от повторной загрузки
    if not _ENV_LOADED:
        load_dotenv()  # предпочитаем local .env рядом с проектом
        _ENV_LOADED = True


def _extract_candidate_urls_from_raw(raw: Any) -> List[str]:
    """
    Достаёт URL страниц товаров, которые Perplexity указал как источники (citations, annotations).
    """

    if not isinstance(raw, dict):
        return []

    urls: List[str] = []

    citations = raw.get("citations")
    if isinstance(citations, list):
        for item in citations:
            if isinstance(item, str):
                urls.append(item)

    choices = raw.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if not isinstance(message, dict):
                continue
            annotations = message.get("annotations")
            if not isinstance(annotations, list):
                continue
            for annotation in annotations:
                if not isinstance(annotation, dict):
                    continue
                payload = annotation.get("url_citation")
                if not isinstance(payload, dict):
                    continue
                url = payload.get("url")
                if isinstance(url, str):
                    urls.append(url)

    seen: set[str] = set()
    unique_urls: List[str] = []
    for url in urls:
        normalized = url.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_urls.append(normalized)

    return unique_urls


async def lookup_product(brand: str, pn: str) -> Dict[str, Any]:
    """
    Загружает .env, инициализирует клиента Perplexity и выполняет поиск.
    """

    _ensure_env_loaded()
    api_key = os.getenv("OPENROUTER_API_KEY", "")

    client = PerplexityClient(api_key=api_key or "")
    safe_brand = (brand or "").strip()
    safe_pn = (pn or "").strip()

    result = await client.lookup(brand=safe_brand, part_number=safe_pn)

    image_url = result.get("image_url")
    image_is_valid = False

    if image_url:
        try:
            image_is_valid = await ReliablePhotoFinder.validate_external_image_url(
                image_url
            )
        except Exception:
            image_is_valid = False

    finder = ReliablePhotoFinder()
    candidate_urls: List[str] = []

    if not image_is_valid:
        result["image_url"] = None

        raw_payload = result.get("raw") or {}
        candidate_urls = _extract_candidate_urls_from_raw(raw_payload)
        if candidate_urls:
            page_image = await finder.find_image_from_pages(
                urls=candidate_urls,
                part_number=safe_pn,
                brand=safe_brand,
                model=result.get("model"),
            )
            if page_image:
                result["image_url"] = page_image
                return result

        fallback_image = await finder.find_image(
            brand=safe_brand,
            part_number=safe_pn,
            model=result.get("model"),
        )
        if fallback_image:
            result["image_url"] = fallback_image

    if not result.get("image_url") and candidate_urls:
        prioritized_pages = finder._prioritize_page_urls(candidate_urls, safe_pn)
        page_url = prioritized_pages[0] if prioritized_pages else None
        if page_url:
            try:
                local_png = await screenshot_product_page(
                    url=page_url,
                    file_prefix=f"{safe_brand}_{safe_pn}",
                )
                if local_png:
                    cloud_url = upload_screenshot_to_cloud(local_png)
                    if cloud_url:
                        result["image_url"] = cloud_url
                    try:
                        os.remove(local_png)
                    except OSError:
                        pass
            except Exception:
                pass

    return result

