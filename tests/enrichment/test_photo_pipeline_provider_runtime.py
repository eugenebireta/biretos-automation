"""Tests for photo_pipeline provider runtime behavior without API keys."""
from __future__ import annotations

import os
import sys

import pytest

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

import photo_pipeline


@pytest.fixture(autouse=True)
def _reset_provider_adapters():
    photo_pipeline.reset_chat_completion_adapter()
    photo_pipeline.reset_search_provider_adapter()
    yield
    photo_pipeline.reset_chat_completion_adapter()
    photo_pipeline.reset_search_provider_adapter()


class DummyAdapter:
    def __init__(self, content: str):
        self._content = content
        self.calls: list[dict] = []

    def complete(self, *, model: str, messages: list[dict], **api_kwargs) -> str:
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "api_kwargs": api_kwargs,
            }
        )
        return self._content


class DummySearchAdapter:
    def __init__(self):
        self.calls: list[dict] = []

    def search(self, *, params: dict) -> dict:
        self.calls.append(dict(params))
        query = params.get("q") or params.get("text") or ""
        if "00020211" in query and params.get("gl") == "us":
            return {
                "organic_results": [
                    {
                        "link": "https://www.newark.com/honeywell/00020211",
                        "title": "Honeywell 00020211 Temperature Sensor",
                        "snippet": "Honeywell 00020211 exact match",
                    }
                ]
            }
        return {"organic_results": []}


def test_call_gpt_uses_injected_adapter_and_logs_parsed_json(monkeypatch):
    adapter = DummyAdapter('{"ok": true, "source": "dummy"}')
    records: list[dict] = []
    monkeypatch.setattr(photo_pipeline, "shadow_log", lambda **kwargs: records.append(kwargs))

    content = photo_pipeline.call_gpt(
        task_type="price_extraction",
        pn="00020211",
        brand="Honeywell",
        messages=[{"role": "user", "content": "extract"}],
        adapter=adapter,
        temperature=0,
    )

    assert content == '{"ok": true, "source": "dummy"}'
    assert adapter.calls == [
        {
            "model": photo_pipeline.PRICE_LLM_MODEL,
            "messages": [{"role": "user", "content": "extract"}],
            "api_kwargs": {"temperature": 0},
        }
    ]
    assert records[0]["parse_success"] is True
    assert records[0]["response_parsed"] == {"ok": True, "source": "dummy"}


def test_call_gpt_requires_openai_key_only_at_call_time(monkeypatch):
    monkeypatch.setattr(photo_pipeline, "client", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not configured"):
        photo_pipeline.call_gpt(
            task_type="price_extraction",
            pn="00020211",
            brand="Honeywell",
            messages=[{"role": "user", "content": "extract"}],
            adapter=photo_pipeline.OpenAIChatCompletionsAdapter(),
        )


def test_step2_us_price_skips_search_without_serpapi_key(monkeypatch):
    calls: list[dict] = []

    class DummySearch:
        def __init__(self, params):
            calls.append(dict(params))

        def get_dict(self):
            return {"organic_results": []}

    monkeypatch.setattr(photo_pipeline, "serpapi_key", "")
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    monkeypatch.setattr(photo_pipeline, "GoogleSearch", DummySearch)
    monkeypatch.setattr(photo_pipeline.time, "sleep", lambda *_args, **_kwargs: None)

    candidates = photo_pipeline.step2_us_price("00020211", "Temperature Sensor")

    assert candidates == []
    assert calls == []


def test_step2_us_price_uses_injected_search_adapter_without_serpapi_key(monkeypatch):
    adapter = DummySearchAdapter()

    monkeypatch.setattr(photo_pipeline, "serpapi_key", "")
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    monkeypatch.setattr(photo_pipeline.time, "sleep", lambda *_args, **_kwargs: None)
    photo_pipeline.set_search_provider_adapter(adapter)

    candidates = photo_pipeline.step2_us_price("00020211", "Temperature Sensor")

    assert candidates == [
        {
            "url": "https://www.newark.com/honeywell/00020211",
            "snippet": "Honeywell 00020211 exact match",
            "title": "Honeywell 00020211 Temperature Sensor",
            "source_type": "authorized_distributor",
            "source_tier": "authorized",
            "source_weight": pytest.approx(0.90),
            "engine": "google_us",
        }
    ]
    assert [call.get("engine") for call in adapter.calls] == ["google", "yandex", "google"]
