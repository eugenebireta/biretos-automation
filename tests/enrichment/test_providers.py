from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from providers import (
    ClaudeChatAdapter,
    RateLimiter,
    get_enrichment_model_alias,
)


class _TextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _DummyResponse:
    def __init__(self, text: str):
        self.content = [_TextBlock(text)]


class _RecordingMessagesAPI:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _DummyResponse(self.response_text)


class _RecordingClient:
    def __init__(self, response_text: str):
        self.messages = _RecordingMessagesAPI(response_text)


def _write_secrets(path: Path) -> None:
    path.write_text("ANTHROPIC_API_KEY=test-key\n", encoding="utf-8")


def test_get_enrichment_model_alias_reads_yaml(tmp_path):
    config_path = tmp_path / "enrichment_models.yaml"
    config_path.write_text(
        "\n".join(
            [
                "text:",
                "  provider: anthropic",
                "  model: claude-haiku-4-5",
                "vision:",
                "  provider: anthropic",
                "  model: claude-sonnet-4-6",
            ]
        ),
        encoding="utf-8",
    )

    assert get_enrichment_model_alias("text", config_path) == "claude-haiku-4-5"
    assert get_enrichment_model_alias("vision", config_path) == "claude-sonnet-4-6"


def test_claude_adapter_translates_text_messages_and_records_metadata(tmp_path):
    secrets_path = tmp_path / ".env.providers"
    _write_secrets(secrets_path)
    dummy_client = _RecordingClient('{"ok": true}')

    adapter = ClaudeChatAdapter(
        secrets_path=secrets_path,
        client_factory=lambda _api_key: dummy_client,
        rate_limiter=RateLimiter(
            requests_per_minute=50,
            burst=5,
            retry_backoff_seconds=[0],
            max_retries=0,
        ),
    )

    content = adapter.complete(
        model="claude-haiku-4-5",
        messages=[
            {"role": "system", "content": "Return JSON only"},
            {"role": "user", "content": "extract the price"},
        ],
        temperature=0,
    )

    assert content == '{"ok": true}'
    call = dummy_client.messages.calls[0]
    assert call["model"] == "claude-haiku-4-5-20251001"
    assert call["system"] == "Return JSON only"
    assert call["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "extract the price"}]}
    ]
    assert adapter.last_call_metadata["provider"] == "anthropic"
    assert adapter.last_call_metadata["model_alias"] == "claude-haiku-4-5"
    assert adapter.last_call_metadata["model_resolved"] == "claude-haiku-4-5-20251001"
    assert adapter.last_call_metadata["error_class"] is None


def test_claude_adapter_translates_image_data_uri_for_vision(tmp_path):
    secrets_path = tmp_path / ".env.providers"
    _write_secrets(secrets_path)
    dummy_client = _RecordingClient('{"verdict": "KEEP"}')

    adapter = ClaudeChatAdapter(
        secrets_path=secrets_path,
        client_factory=lambda _api_key: dummy_client,
        rate_limiter=RateLimiter(
            requests_per_minute=50,
            burst=5,
            retry_backoff_seconds=[0],
            max_retries=0,
        ),
    )

    image_b64 = base64.b64encode(b"test-image").decode()
    adapter.complete(
        model="claude-sonnet-4-6",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "validate image"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                ],
            }
        ],
        max_completion_tokens=80,
    )

    content_blocks = dummy_client.messages.calls[0]["messages"][0]["content"]
    assert content_blocks[0] == {"type": "text", "text": "validate image"}
    assert content_blocks[1] == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": image_b64,
        },
    }
    assert dummy_client.messages.calls[0]["max_tokens"] == 80


def test_rate_limiter_delays_when_burst_limit_is_exceeded():
    now = 0.0
    sleeps: list[float] = []

    def monotonic() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    limiter = RateLimiter(
        requests_per_minute=50,
        burst=2,
        retry_backoff_seconds=[0.0],
        max_retries=0,
        monotonic_fn=monotonic,
        sleep_fn=sleep,
    )

    limiter.acquire()
    limiter.acquire()
    limiter.acquire()

    assert sleeps
    assert sleeps[0] >= 1.0
