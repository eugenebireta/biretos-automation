from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright


async def screenshot_product_page(
    url: str,
    out_dir: str = "screenshots",
    file_prefix: Optional[str] = None,
) -> Optional[str]:
    """
    Делает скриншот карточки товара и возвращает путь к PNG.

    Требует:
        pip install playwright
        playwright install chromium
    """

    if not url:
        return None

    safe_prefix = (file_prefix or "product").strip().replace(" ", "_").replace("/", "_")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    filename = f"{safe_prefix}.png"
    output_path = os.path.join(out_dir, filename)

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await page.set_viewport_size({"width": 1280, "height": 720})

            # Можно попытаться найти блок с карточкой товара и снимать его точечно.
            for selector in [
                ".product-detail",
                ".product-info-main",
                ".product",
                ".single-product",
                ".entry-content",
            ]:
                element = await page.query_selector(selector)
                if element:
                    await element.screenshot(path=output_path)
                    break
            else:
                await page.screenshot(path=output_path, full_page=True)

            await browser.close()
    except Exception:
        return None

    return output_path


