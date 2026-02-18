from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple
from urllib.parse import quote_plus, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag


class ReliablePhotoFinder:
    """
    Поиск реальных HD-фотографий только на проверенных сайтах ZAPI-поставщиков.
    """

    _IMAGE_EXT_PATTERN = re.compile(r"\.(?:jpe?g|png|webp)(?:\?.*)?$", re.IGNORECASE)
    _SIZE_ATTRS_WIDTH = (
        "width",
        "data-width",
        "data-original-width",
        "data-large_image_width",
    )
    _SIZE_ATTRS_HEIGHT = (
        "height",
        "data-height",
        "data-original-height",
        "data-large_image_height",
    )
    _USER_AGENT = "ReliablePhotoFinder/1.0 (+https://github.com/biretos)"
    _MIN_WIDTH = 500
    _MIN_HEIGHT = 500
    _MIN_BYTES = 90 * 1024

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self._site_configs = self._build_site_configs()
        self._last_source: Optional[str] = None

    @property
    def last_source(self) -> Optional[str]:
        return self._last_source

    async def find_image(
        self, brand: str, part_number: str, model: Optional[str] = None
    ) -> Optional[str]:
        self._last_source = None

        normalized_pn = (part_number or "").strip()
        if not normalized_pn:
            return None

        queries = self._build_queries(normalized_pn, brand or "", model or "")

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers=self._default_headers,
            follow_redirects=True,
        ) as client:
            for site in self._site_configs:
                image_url = await self._search_site(
                    client=client,
                    site_config=site,
                    part_number=normalized_pn,
                    queries=queries,
                )
                if image_url:
                    self._last_source = site["domain"]
                    return image_url

        return None

    async def find_image_from_pages(
        self,
        urls: List[str],
        part_number: str,
        brand: str = "",
        model: Optional[str] = None,
    ) -> Optional[str]:
        """
        Использует уже известные страницы товаров (например, из Perplexity citations)
        и пытается извлечь валидное фото.
        """

        prioritized = self._prioritize_page_urls(urls, part_number)
        if not prioritized:
            return None

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers=self._default_headers,
            follow_redirects=True,
        ) as client:
            for page_url in prioritized:
                html = await self._fetch_html(client, page_url)
                if not html:
                    continue

                domain = urlparse(page_url).netloc.lower()
                image_url: Optional[str] = None

                if "dc66.ru" in domain:
                    image_url = self._extract_product_image_dc66(
                        html, page_url, part_number
                    )
                elif "cloudelectric.com" in domain:
                    image_url = self._extract_product_image_cloudelectric(
                        html, page_url, part_number
                    )
                elif "sourcefy.com" in domain:
                    image_url = self._extract_product_image_sourcefy(
                        html, page_url, part_number
                    )
                elif "tvh.com" in domain:
                    image_url = self._extract_product_image_tvh(
                        html, page_url, part_number
                    )
                elif "liftpartswarehouse.com" in domain:
                    image_url = self._extract_product_image_liftpartswarehouse(
                        html, page_url, part_number
                    )

                if not image_url:
                    candidates = self._extract_image_candidates(
                        html,
                        page_url,
                        part_number=part_number,
                        model=model or "",
                    )
                    for candidate in candidates:
                        if await self._validate_image_url(client, candidate):
                            self._last_source = domain
                            return candidate

                if image_url and await self._validate_image_url(client, image_url):
                    self._last_source = domain
                    return image_url

        return None

    async def _search_site(
        self,
        client: httpx.AsyncClient,
        site_config: dict,
        part_number: str,
        queries: List[str],
    ) -> Optional[str]:
        templates = site_config.get("search_urls", [])

        pn_trimmed = (part_number or "").strip()
        pn_lower = pn_trimmed.lower()
        encoded_pn = quote_plus(pn_trimmed)
        encoded_pn_lower = quote_plus(pn_lower)

        for query in queries:
            encoded_query = quote_plus(query)
            for template in templates:
                search_url = template.format(
                    query=encoded_query,
                    part_number=encoded_pn,
                    part_number_lower=encoded_pn_lower,
                )
                html = await self._fetch_html(client, search_url)
                if not html:
                    continue

                candidates = self._extract_image_candidates(
                    html, search_url, part_number=part_number
                )
                for candidate in candidates:
                    if await self._validate_image_url(client, candidate):
                        return candidate
        return None

    async def _fetch_html(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> Optional[str]:
        try:
            response = await client.get(url)
        except httpx.HTTPError:
            return None

        if response.status_code >= 400:
            return None

        return response.text

    def _extract_image_candidates(
        self,
        html: str,
        base_url: str,
        part_number: str = "",
        model: str = "",
    ) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        candidates: List[Tuple[int, int, str]] = []
        seen: set[str] = set()

        pn_norm = self._normalize_key(part_number)
        model_norm = self._normalize_key(model)
        domain = urlparse(base_url).netloc.lower()

        for index, tag in enumerate(soup.find_all("img")):
            normalized = self._resolve_image_url(tag, base_url)

            if not normalized or normalized in seen:
                continue

            if self._looks_like_logo(normalized, tag):
                continue

            if self._looks_like_banner(normalized):
                continue

            score = self._score_candidate(
                url=normalized,
                tag=tag,
                domain=domain,
                pn_norm=pn_norm,
                model_norm=model_norm,
            )

            if score <= 0:
                continue

            candidates.append((score, index, normalized))
            seen.add(normalized)

        candidates.sort(key=lambda item: (-item[0], item[1]))
        return [candidate[2] for candidate in candidates]

    def _resolve_image_url(self, tag: Tag, base_url: str) -> Optional[str]:
        """
        Определяет «лучшую» ссылку на изображение для тега <img>.
        Сперва берёт src/srcset, затем при необходимости пытается перейти
        от уменьшенной версии (resize_cache) к оригиналу из <a href="...">.
        """

        src = self._get_preferred_src(tag)
        normalized = self._normalize_url(base_url, src)

        if not normalized:
            return None

        if "resize_cache" in normalized:
            parent = tag.parent
            if isinstance(parent, Tag):
                href = parent.get("href")
                original = self._normalize_url(base_url, href)
                if original and self._IMAGE_EXT_PATTERN.search(original):
                    normalized = original

        return normalized

    def _get_preferred_src(self, tag: Tag) -> Optional[str]:
        srcset = tag.get("srcset") or tag.get("data-srcset")
        if isinstance(srcset, str):
            best = self._pick_from_srcset(srcset)
            if best:
                return best

        for attr in (
            "data-large_image",
            "data-src",
            "data-original",
            "data-lazy",
            "data-image",
            "src",
        ):
            value = tag.get(attr)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _estimate_area(self, tag: Tag) -> int:
        width = self._extract_dimension(tag, self._SIZE_ATTRS_WIDTH)
        height = self._extract_dimension(tag, self._SIZE_ATTRS_HEIGHT)
        if width and height:
            return width * height
        return 0

    def _looks_like_logo(self, url: str, tag: Tag) -> bool:
        """
        Эвристика для отсеивания логотипов и служебных картинок.
        Не идеально, но сильно снижает шанс получить «заглушку» вместо фото товара.
        """

        url_lower = url.lower()
        text_parts = []
        for attr in ("alt", "title", "data-alt", "data-title"):
            value = tag.get(attr)
            if isinstance(value, str):
                text_parts.append(value)
        text = " ".join(text_parts).lower()

        logo_keywords = (
            "logo",
            "логотип",
            "brand",
            "placeholder",
            "icon",
            "sprite",
            "no_photo",
            "noimage",
            "nophoto",
            "default",
        )
        logo_paths = (
            "brand_overview",
            "brand-logo",
            "logo_",
            "/logos/",
            "/icons/",
            "/sprites/",
            "/placeholder/",
            "/no_photo/",
        )

        if any(word in url_lower for word in logo_keywords):
            return True
        if any(fragment in url_lower for fragment in logo_paths):
            return True
        if any(word in text for word in logo_keywords):
            return True

        width = self._extract_dimension(tag, self._SIZE_ATTRS_WIDTH)
        height = self._extract_dimension(tag, self._SIZE_ATTRS_HEIGHT)
        if width and height:
            # Маленькие почти квадратные изображения очень часто оказываются логотипами.
            if width <= 150 and height <= 150:
                aspect = width / height if height else 0
                if 0.7 <= aspect <= 1.3:
                    return True

        return False

    @staticmethod
    def _normalize_key(value: str) -> str:
        return (value or "").lower().replace("-", "").replace(" ", "").replace("_", "")

    def _context_contains_key(self, tag: Tag, key_norm: str) -> bool:
        if not key_norm or len(key_norm) < 3:
            return False

        nodes = [tag]
        parent = tag.parent
        steps = 0
        while parent is not None and steps < 3:
            if isinstance(parent, Tag):
                nodes.append(parent)
            parent = parent.parent
            steps += 1

        text_chunks: List[str] = []
        for node in nodes:
            if isinstance(node, Tag):
                txt = node.get_text(separator=" ", strip=True)
                if txt:
                    text_chunks.append(txt)

        context = " ".join(text_chunks)
        context_norm = self._normalize_key(context)
        return key_norm in context_norm

    @staticmethod
    def _looks_like_banner(url: str) -> bool:
        url_lower = url.lower()
        filename = url_lower.split("/")[-1].split("?")[0]

        bad_keywords = (
            "banner",
            "hero",
            "promo",
            "promotion",
            "untitled",
            "design",
            "placeholder",
            "ads",
            "advert",
            "marketing",
            "campaign",
            "generic",
            "default",
            "thumb",
            "thumbnail",
        )

        if any(f"/{word}/" in url_lower for word in ("banners", "ads", "marketing", "promo")):
            return True

        return any(word in filename for word in bad_keywords)

    def _score_candidate(
        self,
        url: str,
        tag: Tag,
        domain: str,
        pn_norm: str,
        model_norm: str,
    ) -> int:
        score = 0

        area = self._estimate_area(tag)
        score += min(area // 1000, 2000)

        url_clean = self._normalize_key(url)
        filename = url.split("/")[-1].split("?")[0].lower()
        filename_clean = self._normalize_key(filename)

        if pn_norm and len(pn_norm) >= 3:
            if pn_norm in url_clean:
                score += 600
            if pn_norm in filename_clean:
                score += 400

        if model_norm and len(model_norm) >= 3:
            if model_norm in url_clean:
                score += 300

        if pn_norm and self._context_contains_key(tag, pn_norm):
            score += 800
        if model_norm and self._context_contains_key(tag, model_norm):
            score += 400

        trusted = ("dc66.ru", "cloudelectric.com", "sourcefy.com")
        if any(d in domain for d in trusted):
            score += 300

        suspicious = ("/ads/", "/banners/", "/marketing/", "/promo/")
        if any(x in url.lower() for x in suspicious):
            score -= 800

        return score

    def _extract_dimension(self, tag: Tag, attributes: Iterable[str]) -> Optional[int]:
        for attr in attributes:
            value = tag.get(attr)
            if not isinstance(value, str):
                continue
            match = re.search(r"(\d+)", value)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue
        return None

    def _normalize_url(self, base_url: str, candidate: Optional[str]) -> Optional[str]:
        if not candidate:
            return None

        candidate = candidate.strip()
        if not candidate or candidate.startswith("data:"):
            return None

        normalized = urljoin(base_url, candidate)
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"}:
            return None

        return normalized

    def _pick_from_srcset(self, srcset: str) -> Optional[str]:
        best_url: Optional[str] = None
        best_score = -1

        for entry in srcset.split(","):
            item = entry.strip()
            if not item:
                continue

            parts = item.split()
            url = parts[0]
            descriptor = parts[1] if len(parts) > 1 else ""
            score = self._descriptor_score(descriptor)

            if score > best_score:
                best_score = score
                best_url = url

        return best_url

    @staticmethod
    def _descriptor_score(descriptor: str) -> int:
        descriptor = descriptor.strip().lower()
        if descriptor.endswith("w"):
            try:
                return int(descriptor[:-1])
            except ValueError:
                return 0
        if descriptor.endswith("x"):
            try:
                return int(float(descriptor[:-1]) * 1000)
            except ValueError:
                return 0
        return 0

    async def _validate_image_url(
        self, client: httpx.AsyncClient, url: str
    ) -> bool:
        """
        Проверяет, что URL ссылается на живое изображение:
        - HTTP 200
        - Content-Type: image/*
        - Размер не меньше _MIN_BYTES
        - Разрешение не меньше _MIN_WIDTH x _MIN_HEIGHT (для JPEG/PNG)
        """

        if not self._IMAGE_EXT_PATTERN.search(url):
            return False

        # HEAD — быстрый фильтр по статусу и Content-Length, если он есть.
        try:
            head_response = await client.head(url)
        except httpx.HTTPError:
            head_response = None

        if head_response is not None:
            if not self._is_valid_image_response(head_response):
                return False

            content_length = head_response.headers.get("Content-Length")
            if content_length:
                try:
                    size = int(content_length)
                    if size < self._MIN_BYTES:
                        return False
                except ValueError:
                    # Игнорируем некорректный заголовок и проверяем размер по фактическим данным.
                    pass

        # Полный GET для проверки фактического размера и разрешения.
        try:
            response = await client.get(url)
        except httpx.HTTPError:
            return False

        if not self._is_valid_image_response(response):
            return False

        data = response.content or b""
        if len(data) < self._MIN_BYTES:
            return False

        width, height = self._probe_image_size(data)
        if width is not None and height is not None:
            if width < self._MIN_WIDTH or height < self._MIN_HEIGHT:
                return False

        return True

    @staticmethod
    def _is_valid_image_response(response: httpx.Response) -> bool:
        if response.status_code != 200:
            return False

        content_type = response.headers.get("Content-Type", "")
        return isinstance(content_type, str) and content_type.lower().startswith("image/")

    @staticmethod
    def _probe_image_size(data: bytes) -> Tuple[Optional[int], Optional[int]]:
        """
        Пытается определить размеры изображения (width, height) по байтам файла.
        Поддерживаются самые распространённые форматы: JPEG и PNG.
        """

        if not data:
            return None, None

        # PNG: сигнатура + IHDR-чанк.
        if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
            width = int.from_bytes(data[16:20], "big")
            height = int.from_bytes(data[20:24], "big")
            return width, height

        # JPEG: ищем SOF-маркер.
        if data.startswith(b"\xFF\xD8"):
            i = 2
            data_len = len(data)
            while i < data_len:
                # Ищем начало маркера.
                while i < data_len and data[i] != 0xFF:
                    i += 1
                while i < data_len and data[i] == 0xFF:
                    i += 1
                if i >= data_len:
                    break

                marker = data[i]
                i += 1

                # Маркеры SOI/EOI не содержат длину.
                if marker in (0xD8, 0xD9):
                    continue

                if i + 2 > data_len:
                    break
                length = int.from_bytes(data[i : i + 2], "big")
                if length < 2 or i + length > data_len:
                    break

                # SOF0, SOF1, SOF2 и др. — содержат размеры.
                if marker in {
                    0xC0,
                    0xC1,
                    0xC2,
                    0xC3,
                    0xC5,
                    0xC6,
                    0xC7,
                    0xC9,
                    0xCA,
                    0xCB,
                    0xCD,
                    0xCE,
                    0xCF,
                }:
                    if i + 7 <= data_len:
                        # length (2 байта) уже прочитали, далее:
                        # 1 байт precision, 2 байта height, 2 байта width.
                        height = int.from_bytes(data[i + 3 : i + 5], "big")
                        width = int.from_bytes(data[i + 5 : i + 7], "big")
                        return width, height
                    break

                i += length

        # Формат не распознан.
        return None, None

    def _prioritize_page_urls(
        self,
        urls: Iterable[str],
        part_number: str,
    ) -> List[str]:
        """
        Сортирует URL по приоритету доверенных доменов и наличию партномера.
        """

        priority_map = {
            "dc66.ru": 0,
            "www.dc66.ru": 0,
            "tvh.com": 1,
            "www.tvh.com": 1,
            "liftpartswarehouse.com": 2,
            "www.liftpartswarehouse.com": 2,
            "forklift-international.com": 3,
            "www.forklift-international.com": 3,
            "forkliftparts.com": 3,
            "www.forkliftparts.com": 3,
            "fmxcontrols.com": 4,
            "www.fmxcontrols.com": 4,
            "curtisswrightds.com": 5,
            "www.curtisswrightds.com": 5,
            "zapigroup.com": 6,
            "www.zapigroup.com": 6,
        }

        pn_normalized = (part_number or "").lower().replace("-", "").replace(" ", "")
        seen: set[str] = set()
        scored: List[Tuple[int, int, str]] = []

        for index, url in enumerate(urls):
            if not isinstance(url, str):
                continue
            candidate = url.strip()
            if not candidate or candidate in seen:
                continue

            parsed = urlparse(candidate)
            if parsed.scheme not in {"http", "https"}:
                continue

            domain = parsed.netloc.lower()
            base_score = priority_map.get(domain, 100)
            score = base_score

            url_for_match = candidate.lower().replace("-", "").replace(" ", "")
            if pn_normalized and pn_normalized in url_for_match:
                score -= 1

            scored.append((score, index, candidate))
            seen.add(candidate)

        scored.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in scored]

    def _build_queries(self, part_number: str, brand: str, model: str) -> List[str]:
        queries: List[str] = []

        def _append(value: str) -> None:
            if value and value not in queries:
                queries.append(value)

        _append(part_number.strip())
        _append(f"{brand.strip()} {part_number}".strip())
        _append(f"{part_number} {model.strip()}".strip())
        _append(f"{brand.strip()} {model.strip()} {part_number}".strip())

        return [query for query in queries if query]

    @property
    def _default_headers(self) -> dict:
        return {
            "User-Agent": self._USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    @classmethod
    async def validate_external_image_url(
        cls,
        url: str,
        timeout: float = 10.0,
    ) -> bool:
        """
        Публичная проверка произвольного URL изображения:
        - HTTP 200
        - Content-Type начинается с image/
        Используется для валидации ссылок, пришедших от Perplexity.
        """

        finder = cls(timeout=timeout)
        async with httpx.AsyncClient(
            timeout=finder.timeout,
            headers=finder._default_headers,
            follow_redirects=True,
        ) as client:
            return await finder._validate_image_url(client, url)

    def _extract_product_image_dc66(
        self,
        html: str,
        base_url: str,
        part_number: str = "",
    ) -> Optional[str]:
        """
        Пытается извлечь главное фото с карточки товара dc66.ru:
        - сначала og:image
        - затем изображения внутри слайдера (swiper-slide)
        """

        soup = BeautifulSoup(html, "html.parser")
        pn_norm = self._normalize_key(part_number)

        meta = soup.find("meta", property="og:image")
        if meta:
            candidate = self._normalize_url(base_url, meta.get("content"))
            if candidate:
                return candidate

        for node in soup.find_all(["li", "a"], class_="swiper-slide"):
            img = node.find("img")
            if not img:
                continue
            candidate = self._resolve_image_url(img, base_url)
            if not candidate:
                continue

            if pn_norm and len(pn_norm) >= 3:
                url_clean = self._normalize_key(candidate)
                if pn_norm not in url_clean and not self._context_contains_key(img, pn_norm):
                    continue

            return candidate

        return None

    def _extract_product_image_cloudelectric(
        self,
        html: str,
        base_url: str,
        part_number: str = "",
    ) -> Optional[str]:
        """
        Извлекает фото товара с cloudelectric.com:
        - сначала og:image
        - затем блоки product-image или main-image
        """

        soup = BeautifulSoup(html, "html.parser")
        pn_norm = self._normalize_key(part_number)

        meta = soup.find("meta", property="og:image")
        if meta:
            candidate = self._normalize_url(base_url, meta.get("content"))
            if candidate:
                return candidate

        selectors = [
            ("div", {"class": "product-image-container"}),
            ("div", {"class": "product-image"}),
            ("div", {"class": "product-img-box"}),
            ("div", {"id": "main-image"}),
        ]

        for name, attrs in selectors:
            container = soup.find(name, attrs=attrs)
            if not container:
                continue
            img = container.find("img")
            if img:
                candidate = self._resolve_image_url(img, base_url)
                if not candidate:
                    continue

                if pn_norm and len(pn_norm) >= 3:
                    url_clean = self._normalize_key(candidate)
                    if pn_norm not in url_clean and not self._context_contains_key(img, pn_norm):
                        continue

                return candidate

        img = soup.find("img", class_="attachment-shop_single")
        if img:
            candidate = self._resolve_image_url(img, base_url)
            if candidate:
                if pn_norm and len(pn_norm) >= 3:
                    url_clean = self._normalize_key(candidate)
                    if pn_norm not in url_clean and not self._context_contains_key(img, pn_norm):
                        return None
                return candidate

        return None

    def _extract_product_image_sourcefy(
        self,
        html: str,
        base_url: str,
        part_number: str = "",
    ) -> Optional[str]:
        """
        Извлекает фото товара с sourcefy.com (WooCommerce):
        - og:image
        - img.wp-post-image, img.attachment-shop_single и т.п.
        """

        soup = BeautifulSoup(html, "html.parser")
        pn_norm = self._normalize_key(part_number)

        meta = soup.find("meta", property="og:image")
        if meta:
            candidate = self._normalize_url(base_url, meta.get("content"))
            if candidate:
                return candidate

        img = soup.find("img", class_="wp-post-image")
        if img:
            candidate = self._resolve_image_url(img, base_url)
            if candidate:
                if pn_norm and len(pn_norm) >= 3:
                    url_clean = self._normalize_key(candidate)
                    if pn_norm not in url_clean and not self._context_contains_key(img, pn_norm):
                        return None
                return candidate

        for class_name in [
            "attachment-shop_single",
            "woocommerce-main-image",
            "woocommerce-product-gallery__image",
        ]:
            node = soup.find("img", class_=class_name)
            if node:
                candidate = self._resolve_image_url(node, base_url)
                if candidate:
                    if pn_norm and len(pn_norm) >= 3:
                        url_clean = self._normalize_key(candidate)
                        if pn_norm not in url_clean and not self._context_contains_key(node, pn_norm):
                            continue
                    return candidate

        gallery = soup.find("figure", class_="woocommerce-product-gallery__wrapper")
        if gallery:
            img = gallery.find("img")
            if img:
                candidate = self._resolve_image_url(img, base_url)
                if candidate:
                    if pn_norm and len(pn_norm) >= 3:
                        url_clean = self._normalize_key(candidate)
                        if pn_norm not in url_clean and not self._context_contains_key(img, pn_norm):
                            return None
                    return candidate

        return None

    def _extract_product_image_tvh(
        self,
        html: str,
        base_url: str,
        part_number: str = "",
    ) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        pn_norm = self._normalize_key(part_number)

        meta = soup.find("meta", property="og:image")
        if meta:
            candidate = self._normalize_url(base_url, meta.get("content"))
            if candidate:
                return candidate

        selectors = [
            "div.product-image img",
            "div.product-media img",
            "div.tvh-product-image img",
            "div.product-main__image img",
        ]

        for selector in selectors:
            node = soup.select_one(selector)
            if not node or not isinstance(node, Tag):
                continue
            candidate = self._resolve_image_url(node, base_url)
            if not candidate:
                continue

            if pn_norm and len(pn_norm) >= 3:
                url_clean = self._normalize_key(candidate)
                if pn_norm not in url_clean and not self._context_contains_key(node, pn_norm):
                    continue

            return candidate

        return None

    def _extract_product_image_liftpartswarehouse(
        self,
        html: str,
        base_url: str,
        part_number: str = "",
    ) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        pn_norm = self._normalize_key(part_number)

        meta = soup.find("meta", property="og:image")
        if meta:
            candidate = self._normalize_url(base_url, meta.get("content"))
            if candidate:
                return candidate

        selectors = [
            "div.product-image-container img",
            "div.productView-image img",
            "img.product-main-image",
            "div.product-img-box img",
        ]

        for selector in selectors:
            node = soup.select_one(selector)
            if not node or not isinstance(node, Tag):
                continue
            candidate = self._resolve_image_url(node, base_url)
            if not candidate:
                continue

            if pn_norm and len(pn_norm) >= 3:
                url_clean = self._normalize_key(candidate)
                if pn_norm not in url_clean and not self._context_contains_key(node, pn_norm):
                    continue

            return candidate

        return None

    @staticmethod
    def _build_site_configs() -> List[dict]:
        return [
            {
                "name": "Domcar (dc66.ru)",
                "domain": "dc66.ru",
                "search_urls": [
                    # Прямая попытка выйти на карточку контроллера ZAPI по партномеру.
                    # Например: https://dc66.ru/catalog/kontrollery-zapi/kontroller-zapi-fz5127/
                    "https://dc66.ru/catalog/kontrollery-zapi/kontroller-zapi-{part_number_lower}/",
                    # Резервный вариант — поиск по сайту, если доступен.
                    "https://dc66.ru/search/?q={query}",
                ],
            },
            {
                "name": "TVH Parts",
                "domain": "tvh.com",
                "search_urls": [
                    "https://www.tvh.com/en-us/search?q={query}",
                    "https://www.tvh.com/en-gb/search?q={query}",
                ],
            },
            {
                "name": "LiftPartsWarehouse",
                "domain": "liftpartswarehouse.com",
                "search_urls": [
                    "https://www.liftpartswarehouse.com/SearchResults.asp?Search={query}",
                ],
            },
            {
                "name": "Forklift International",
                "domain": "forklift-international.com",
                "search_urls": [
                    "https://www.forklift-international.com/search?q={query}",
                    "https://www.forkliftparts.com/search?q={query}",
                ],
            },
            {
                "name": "FMX Controls",
                "domain": "fmxcontrols.com",
                "search_urls": [
                    "https://fmxcontrols.com/?s={query}",
                ],
            },
            {
                "name": "Curtiss-Wright PG Drives",
                "domain": "curtisswrightds.com",
                "search_urls": [
                    "https://www.curtisswrightds.com/search?search_api_fulltext={query}",
                ],
            },
        ]
