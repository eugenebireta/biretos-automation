"""Tests for gemini_provider.py — DDG search, Gemini extraction, vision, rate limiter."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from gemini_provider import (
    AdaptiveRateLimiter,
    GeminiChatAdapter,
    GeminiSearchAdapter,
    PRICE_EXTRACTION_SCHEMA,
    VISION_VERDICT_SCHEMA,
    _cache_key,
    _extract_grounding_urls,
    _extract_json_from_text,
    _save_to_cache,
    _load_from_cache,
    search_ddg,
)


# ── Rate limiter tests ────────────────────────────────────────────────────────

class TestAdaptiveRateLimiter:
    def test_acquire_enforces_min_interval(self):
        calls = []
        clock = [0.0]

        def monotonic():
            return clock[0]

        def sleep(seconds):
            calls.append(seconds)
            clock[0] += seconds

        rl = AdaptiveRateLimiter(rpm=15, sleep_fn=sleep, monotonic_fn=monotonic)
        rl.acquire()
        assert rl.daily_plain == 1

        # Second call should sleep
        rl.acquire()
        assert len(calls) >= 1
        assert calls[0] == pytest.approx(4.0, abs=0.1)
        assert rl.daily_plain == 2

    def test_grounded_tracks_separately(self):
        rl = AdaptiveRateLimiter(
            rpm=100,
            sleep_fn=lambda s: None,
            monotonic_fn=time.monotonic,
        )
        rl.acquire(grounded=True)
        rl.acquire(grounded=False)
        assert rl.daily_grounded == 1
        assert rl.daily_plain == 1

    def test_report_429_increases_backoff(self):
        slept = []
        rl = AdaptiveRateLimiter(
            rpm=100,
            sleep_fn=lambda s: slept.append(s),
            monotonic_fn=time.monotonic,
        )
        rl.report_429()
        assert rl._consecutive_429 == 1
        assert len(slept) == 1
        assert slept[0] >= 10.0

    def test_report_success_resets_429(self):
        rl = AdaptiveRateLimiter(
            rpm=100,
            sleep_fn=lambda s: None,
            monotonic_fn=time.monotonic,
        )
        rl._consecutive_429 = 3
        rl.report_success()
        assert rl._consecutive_429 == 0

    def test_get_stats(self):
        rl = AdaptiveRateLimiter(
            rpm=100,
            sleep_fn=lambda s: None,
            monotonic_fn=time.monotonic,
        )
        rl.acquire(grounded=True)
        rl.acquire(grounded=False)
        rl.acquire(grounded=False)
        stats = rl.get_stats()
        assert stats["daily_plain"] == 2
        assert stats["daily_grounded"] == 1
        assert stats["consecutive_429"] == 0


# ── JSON extraction tests ─────────────────────────────────────────────────────

class TestExtractJsonFromText:
    def test_plain_json(self):
        assert _extract_json_from_text('{"a": 1}') == {"a": 1}

    def test_json_in_markdown_fence(self):
        text = "Here is the result:\n```json\n{\"verdict\": \"KEEP\"}\n```"
        assert _extract_json_from_text(text) == {"verdict": "KEEP"}

    def test_json_with_preamble(self):
        text = "The product was found.\n{\"found\": true, \"price\": 42.5}"
        assert _extract_json_from_text(text) == {"found": True, "price": 42.5}

    def test_trailing_comma(self):
        text = '{"a": 1, "b": 2,}'
        assert _extract_json_from_text(text) == {"a": 1, "b": 2}

    def test_invalid_json(self):
        assert _extract_json_from_text("not json at all") is None


# ── Cache tests ───────────────────────────────────────────────────────────────

class TestCache:
    def test_round_trip(self, tmp_path, monkeypatch):
        import gemini_provider as gp
        monkeypatch.setattr(gp, "_CACHE_DIR", tmp_path / "cache")

        data = {"verdict": "KEEP", "reason": "test"}
        _save_to_cache("vision", "PN123", "abc", data)
        loaded = _load_from_cache("vision", "PN123", "abc")
        assert loaded == data

    def test_cache_miss(self, tmp_path, monkeypatch):
        import gemini_provider as gp
        monkeypatch.setattr(gp, "_CACHE_DIR", tmp_path / "empty")
        assert _load_from_cache("x", "y", "z") is None


# ── DDG search adapter tests ─────────────────────────────────────────────────

class TestGeminiSearchAdapter:
    def test_search_returns_serpapi_format(self):
        adapter = GeminiSearchAdapter()
        mock_results = [
            {"href": "https://example.com/product", "title": "Product", "body": "desc"},
            {"href": "https://other.com/item", "title": "Item", "body": "snippet"},
        ]

        with patch("gemini_provider.search_ddg", return_value=[
            {"url": "https://example.com/product", "title": "Product", "snippet": "desc", "source_type": "other", "engine": "duckduckgo"},
            {"url": "https://other.com/item", "title": "Item", "snippet": "snippet", "source_type": "other", "engine": "duckduckgo"},
        ]):
            result = adapter.search(params={"q": "test query", "num": 5})

        assert "organic_results" in result
        assert len(result["organic_results"]) == 2
        assert result["organic_results"][0]["link"] == "https://example.com/product"

    def test_empty_query(self):
        adapter = GeminiSearchAdapter()
        result = adapter.search(params={"q": ""})
        assert result == {"organic_results": []}

    def test_region_mapping(self):
        adapter = GeminiSearchAdapter()
        with patch("gemini_provider.search_ddg", return_value=[]) as mock:
            adapter.search(params={"q": "test", "gl": "ru"})
            mock.assert_called_once_with("test", max_results=5, region="ru-ru")


# ── Chat adapter tests ───────────────────────────────────────────────────────

class TestGeminiChatAdapter:
    def test_metadata_on_success(self, monkeypatch):
        adapter = GeminiChatAdapter(api_key="fake-key")

        mock_response = MagicMock()
        mock_response.text = '{"verdict": "KEEP", "reason": "product visible"}'

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        adapter._client = mock_client

        # Bypass rate limiter
        import gemini_provider as gp
        monkeypatch.setattr(gp, "_rate_limiter", AdaptiveRateLimiter(
            rpm=1000, sleep_fn=lambda s: None, monotonic_fn=time.monotonic,
        ))

        result = adapter.complete(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": "test"}],
            temperature=0,
        )
        assert "KEEP" in result
        assert adapter.last_call_metadata["provider"] == "gemini"
        assert adapter.last_call_metadata["error_class"] is None

    def test_handles_image_url_content(self, monkeypatch):
        adapter = GeminiChatAdapter(api_key="fake-key")

        mock_response = MagicMock()
        mock_response.text = '{"verdict": "KEEP"}'

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        adapter._client = mock_client

        import gemini_provider as gp
        monkeypatch.setattr(gp, "_rate_limiter", AdaptiveRateLimiter(
            rpm=1000, sleep_fn=lambda s: None, monotonic_fn=time.monotonic,
        ))

        # Test with mixed text+image content
        messages = [{"role": "user", "content": [
            {"type": "text", "text": "analyze this"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/"}},
        ]}]

        result = adapter.complete(
            model="gemini-2.5-flash",
            messages=messages,
        )
        assert result == '{"verdict": "KEEP"}'


# ── Grounding URL extraction tests ───────────────────────────────────────────

class TestGroundingUrlExtraction:
    def test_extracts_from_metadata(self):
        web = MagicMock()
        web.uri = "https://example.com/page"

        chunk = MagicMock()
        chunk.web = web

        gm = MagicMock()
        gm.grounding_chunks = [chunk]
        gm.grounding_supports = []

        cand = MagicMock()
        cand.grounding_metadata = gm

        response = MagicMock()
        response.candidates = [cand]

        urls = _extract_grounding_urls(response)
        assert urls == ["https://example.com/page"]

    def test_deduplicates_urls(self):
        web = MagicMock()
        web.uri = "https://example.com/page"

        chunk = MagicMock()
        chunk.web = web

        gm = MagicMock()
        gm.grounding_chunks = [chunk, chunk]
        gm.grounding_supports = []

        cand = MagicMock()
        cand.grounding_metadata = gm

        response = MagicMock()
        response.candidates = [cand]

        urls = _extract_grounding_urls(response)
        assert urls == ["https://example.com/page"]

    def test_falls_back_to_regex(self):
        response = MagicMock()
        response.candidates = []
        response.text = "Found at https://store.com/product and https://other.com/item"

        urls = _extract_grounding_urls(response)
        assert "https://store.com/product" in urls
        assert "https://other.com/item" in urls


# ── Schema validation tests ───────────────────────────────────────────────────

class TestSchemas:
    def test_price_schema_has_required_fields(self):
        required = PRICE_EXTRACTION_SCHEMA["required"]
        assert "pn_found" in required
        assert "pn_exact_confirmed" in required
        assert "price_status" in required
        assert "price_confidence" in required

    def test_vision_schema_has_verdict(self):
        required = VISION_VERDICT_SCHEMA["required"]
        assert "verdict" in required
        assert "reason" in required
