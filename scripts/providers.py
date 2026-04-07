"""Provider adapters and config helpers for enrichment LLM calls."""
from __future__ import annotations

import base64
import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODELS_PATH = ROOT / "config" / "enrichment_models.yaml"
DEFAULT_SECRETS_PATH = ROOT / "config" / ".env.providers"

DEFAULT_TEXT_MODEL = "claude-haiku-4-5"
DEFAULT_VISION_MODEL = "claude-sonnet-4-6"

DEFAULT_RATE_LIMITS = {
    "requests_per_minute": 50,
    "burst": 5,
    "retry_backoff_seconds": [2, 4, 8],
    "max_retries": 3,
}

MODEL_ALIAS_RESOLUTION = {
    "claude-haiku-4-5": "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-opus-4-6": "claude-opus-4-6",
}

_DATA_URI_RE = re.compile(
    r"^data:(?P<media_type>[\w.+/-]+);base64,(?P<data>[A-Za-z0-9+/=\s]+)$"
)


def load_enrichment_models_config(path: Path = DEFAULT_MODELS_PATH) -> dict[str, Any]:
    """Load enrichment model config, falling back to safe defaults if absent."""
    if not path.exists():
        return {
            "text": {"provider": "anthropic", "model": DEFAULT_TEXT_MODEL},
            "vision": {"provider": "anthropic", "model": DEFAULT_VISION_MODEL},
            "rate_limits": {"anthropic": dict(DEFAULT_RATE_LIMITS)},
        }

    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to load enrichment_models.yaml") from exc

    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    raw.setdefault("text", {"provider": "anthropic", "model": DEFAULT_TEXT_MODEL})
    raw.setdefault("vision", {"provider": "anthropic", "model": DEFAULT_VISION_MODEL})
    raw.setdefault("rate_limits", {})
    raw["rate_limits"].setdefault("anthropic", dict(DEFAULT_RATE_LIMITS))
    return raw


def get_enrichment_model_alias(kind: str, path: Path = DEFAULT_MODELS_PATH) -> str:
    """Return the configured model alias for a task kind."""
    config = load_enrichment_models_config(path)
    kind_config = config.get(kind) or {}
    return str(
        kind_config.get(
            "model",
            DEFAULT_TEXT_MODEL if kind == "text" else DEFAULT_VISION_MODEL,
        )
    )


def get_anthropic_rate_limits(path: Path = DEFAULT_MODELS_PATH) -> dict[str, Any]:
    """Return Anthropic rate limits from config with sensible defaults."""
    config = load_enrichment_models_config(path)
    rate_limits = dict(DEFAULT_RATE_LIMITS)
    rate_limits.update((config.get("rate_limits") or {}).get("anthropic") or {})
    return rate_limits


def resolve_model_id(model_alias: str) -> str:
    """Resolve a stable API model id for logging and provider calls."""
    return MODEL_ALIAS_RESOLUTION.get(model_alias, model_alias)


def load_provider_secrets(path: Path = DEFAULT_SECRETS_PATH) -> dict[str, str]:
    """Load provider secrets via dotenv_values without polluting os.environ."""
    try:
        from dotenv import dotenv_values
    except ImportError as exc:
        raise RuntimeError("python-dotenv is required to load provider secrets") from exc

    if not path.exists():
        raise RuntimeError(
            f"Provider secrets file not found: {path}. Create config/.env.providers with ANTHROPIC_API_KEY."
        )

    secrets = dict(dotenv_values(str(path)))
    if not secrets.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(f"ANTHROPIC_API_KEY missing in {path}")
    return secrets


@dataclass
class RateLimiter:
    """Simple in-process rate limiter with bounded retry backoff."""

    requests_per_minute: int
    burst: int
    retry_backoff_seconds: list[float]
    max_retries: int
    monotonic_fn: Callable[[], float] = time.monotonic
    sleep_fn: Callable[[float], None] = time.sleep
    _request_timestamps: deque[float] = field(default_factory=deque)

    def acquire(self) -> None:
        """Throttle by RPM and short burst ceiling inside one process."""
        while True:
            now = self.monotonic_fn()

            while self._request_timestamps and now - self._request_timestamps[0] >= 60:
                self._request_timestamps.popleft()

            if (
                self.requests_per_minute > 0
                and len(self._request_timestamps) >= self.requests_per_minute
            ):
                sleep_for = max(0.0, 60 - (now - self._request_timestamps[0])) + 0.01
                self.sleep_fn(sleep_for)
                continue

            if (
                self.burst > 0
                and len(self._request_timestamps) >= self.burst
                and now - self._request_timestamps[-self.burst] < 1.0
            ):
                sleep_for = max(
                    0.0, 1.0 - (now - self._request_timestamps[-self.burst])
                ) + 0.01
                self.sleep_fn(sleep_for)
                continue

            self._request_timestamps.append(now)
            return

    def execute_with_backoff(
        self,
        func: Callable[..., Any],
        *args: Any,
        is_retriable: Callable[[Exception], bool] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute a call with bounded retry/backoff."""
        attempts = 0
        while True:
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                if not (is_retriable and is_retriable(exc)):
                    raise
                if attempts >= self.max_retries:
                    raise
                backoff = self.retry_backoff_seconds[
                    min(attempts, len(self.retry_backoff_seconds) - 1)
                ]
                self.sleep_fn(backoff)
                attempts += 1


def _is_retriable_anthropic_error(exc: Exception) -> bool:
    """Use typed Anthropic SDK exception names when available."""
    return exc.__class__.__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "OverloadedError",
        "RateLimitError",
    }


def _extract_text_block(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(part for part in parts if part)
    return str(content or "")


def _parse_data_uri(url: str) -> tuple[str, str]:
    match = _DATA_URI_RE.match(url.strip())
    if not match:
        raise ValueError("ClaudeChatAdapter supports only base64 data:image URIs")
    media_type = match.group("media_type")
    data = re.sub(r"\s+", "", match.group("data"))
    base64.b64decode(data, validate=True)
    return media_type, data


def _to_anthropic_content(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]

    if not isinstance(content, list):
        raise TypeError(f"Unsupported message content type: {type(content).__name__}")

    blocks: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            raise TypeError("Message blocks must be dicts")

        block_type = block.get("type")
        if block_type == "text":
            blocks.append({"type": "text", "text": str(block.get("text", ""))})
            continue

        if block_type == "image_url":
            image_url = block.get("image_url")
            if isinstance(image_url, dict):
                image_url = image_url.get("url", "")
            if not isinstance(image_url, str):
                raise TypeError("image_url block must contain a string URL")
            media_type, data = _parse_data_uri(image_url)
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": data,
                    },
                }
            )
            continue

        raise ValueError(f"Unsupported content block type: {block_type!r}")

    return blocks


def _to_anthropic_messages(
    messages: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []

    for message in messages:
        role = str(message.get("role", "user"))
        content = message.get("content", "")
        if role == "system":
            system_text = _extract_text_block(content).strip()
            if system_text:
                system_parts.append(system_text)
            continue
        if role not in {"user", "assistant"}:
            raise ValueError(f"Unsupported message role: {role!r}")
        converted.append({"role": role, "content": _to_anthropic_content(content)})

    return ("\n\n".join(system_parts) or None, converted)


class ClaudeChatAdapter:
    """Anthropic Messages API adapter for the photo pipeline seam."""

    provider = "anthropic"

    def __init__(
        self,
        *,
        model_config_path: Path = DEFAULT_MODELS_PATH,
        secrets_path: Path = DEFAULT_SECRETS_PATH,
        client_factory: Callable[[str], Any] | None = None,
        rate_limiter: RateLimiter | None = None,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._model_config_path = model_config_path
        self._secrets_path = secrets_path
        self._client_factory = client_factory
        self._client = None
        self._monotonic_fn = monotonic_fn
        if rate_limiter is None:
            rate_limiter = RateLimiter(
                monotonic_fn=monotonic_fn,
                **get_anthropic_rate_limits(model_config_path),
            )
        self._rate_limiter = rate_limiter
        self.last_call_metadata: dict[str, Any] = {}

    def _load_client(self) -> Any:
        if self._client is not None:
            return self._client

        secrets = load_provider_secrets(self._secrets_path)
        api_key = secrets["ANTHROPIC_API_KEY"]
        if self._client_factory is not None:
            self._client = self._client_factory(api_key)
            return self._client

        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("anthropic package is required for ClaudeChatAdapter") from exc

        self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def complete(self, *, model: str, messages: list[dict], **api_kwargs: Any) -> str:
        start = self._monotonic_fn()
        model_alias = model
        model_resolved = resolve_model_id(model_alias)
        system_prompt, anthropic_messages = _to_anthropic_messages(messages)

        max_tokens = int(
            api_kwargs.pop(
                "max_completion_tokens",
                api_kwargs.pop("max_tokens", 1024),
            )
        )
        temperature = api_kwargs.pop("temperature", 0)
        if "stop" in api_kwargs and "stop_sequences" not in api_kwargs:
            api_kwargs["stop_sequences"] = api_kwargs.pop("stop")

        request_kwargs = {
            "model": model_resolved,
            "max_tokens": max_tokens,
            "messages": anthropic_messages,
            "temperature": temperature,
            **api_kwargs,
        }
        if system_prompt:
            request_kwargs["system"] = system_prompt

        self._rate_limiter.acquire()

        try:
            response = self._rate_limiter.execute_with_backoff(
                self._load_client().messages.create,
                is_retriable=_is_retriable_anthropic_error,
                **request_kwargs,
            )
            content = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )
            latency_ms = int((self._monotonic_fn() - start) * 1000)
            self.last_call_metadata = {
                "provider": self.provider,
                "model_alias": model_alias,
                "model_resolved": model_resolved,
                "latency_ms": latency_ms,
                "error_class": None,
            }
            return content
        except Exception as exc:
            latency_ms = int((self._monotonic_fn() - start) * 1000)
            self.last_call_metadata = {
                "provider": self.provider,
                "model_alias": model_alias,
                "model_resolved": model_resolved,
                "latency_ms": latency_ms,
                "error_class": exc.__class__.__name__,
            }
            raise
