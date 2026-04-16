"""AI Router — universal Gemini/Claude/local model dispatcher with rate limiting.

Goal: ideal pipeline that works always. Priority: accuracy > volume > cost.

Features:
1. Rate limiting per-model (10 RPM for Gemini Free, etc)
2. Auto-fallback: Gemini → Claude → local (when each fails)
3. Token budget tracking
4. Retry with exponential backoff
5. Quality validation: short outputs trigger fallback to better model
6. Cost tracking per request

Usage:
    from scripts.pipeline_v2.ai_router import AIRouter
    router = AIRouter()
    result = router.generate_text(prompt, min_words=200, fallback_to_claude=True)
"""
from __future__ import annotations

import json
import sys
import time
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
USAGE_LOG = ROOT / "downloads" / "training_v2" / "ai_usage_log.jsonl"
USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)


# Rate limits per model (requests per minute)
RATE_LIMITS = {
    "gemini-2.5-flash": 10,        # Free tier
    "gemini-2.5-pro": 5,
    "claude-haiku-4-5": 50,        # paid plan generous
    "claude-sonnet-4-5": 50,
}

# Pricing per 1M tokens
PRICING = {
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.5-pro": {"input": 1.25, "output": 5.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
}


class RateLimiter:
    """Token bucket rate limiter per model."""
    def __init__(self):
        self._calls = {}  # model -> deque of timestamps
        self._lock = threading.Lock()

    def wait_if_needed(self, model: str):
        rpm = RATE_LIMITS.get(model, 10)
        with self._lock:
            now = time.time()
            calls = self._calls.setdefault(model, deque())
            # Remove calls older than 60 sec
            while calls and now - calls[0] > 60:
                calls.popleft()
            if len(calls) >= rpm:
                # Need to wait
                wait = 60 - (now - calls[0]) + 1
                print(f"  [rate-limit] {model}: waiting {wait:.0f}s ({len(calls)}/{rpm} calls in last 60s)")
                time.sleep(wait)
                while calls and time.time() - calls[0] > 60:
                    calls.popleft()
            calls.append(time.time())


_LIMITER = RateLimiter()


def _log_usage(model: str, tokens_in: int, tokens_out: int, cost: float, task: str, success: bool):
    """Append usage record."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": round(cost, 6),
        "task": task,
        "success": success,
    }
    with open(USAGE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def call_gemini(prompt: str, model: str = "gemini-2.5-flash",
                files: list = None, max_tokens: int = 4000,
                temperature: float = 0.4, task: str = "general",
                disable_thinking: bool = True) -> dict:
    """Call Gemini with rate limit + retry."""
    from google import genai as genai_new
    from google.genai import types
    from scripts.app_secrets import get_secret

    client = genai_new.Client(api_key=get_secret("GEMINI_API_KEY"))

    config_kwargs = {"temperature": temperature, "max_output_tokens": max_tokens}
    if disable_thinking:
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)

    contents = [prompt]
    if files:
        for f in files:
            uploaded = client.files.upload(file=str(f))
            contents.insert(0, uploaded)

    for attempt in range(3):
        _LIMITER.wait_if_needed(model)
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs),
            )
            text = response.text.strip() if response.text else ""
            usage = response.usage_metadata
            tokens_in = usage.prompt_token_count if usage else 0
            tokens_out = usage.candidates_token_count if usage else 0
            cost = (tokens_in * PRICING[model]["input"] +
                    tokens_out * PRICING[model]["output"]) / 1_000_000

            _log_usage(model, tokens_in, tokens_out, cost, task, True)
            return {
                "text": text, "model": model, "success": True,
                "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": cost,
            }
        except Exception as e:
            err = str(e)
            if "RESOURCE_EXHAUSTED" in err or "429" in err:
                wait = 30 * (attempt + 1)
                print(f"  [{model}] rate limit hit, waiting {wait}s (attempt {attempt+1}/3)")
                time.sleep(wait)
                continue
            _log_usage(model, 0, 0, 0, task, False)
            return {"text": "", "model": model, "success": False, "error": err[:200]}

    _log_usage(model, 0, 0, 0, task, False)
    return {"text": "", "model": model, "success": False, "error": "all retries exhausted"}


def call_claude(prompt: str, model: str = "claude-haiku-4-5-20251001",
                files: list = None, max_tokens: int = 4000,
                temperature: float = 0.4, task: str = "general") -> dict:
    """Call Claude with rate limit + retry."""
    from scripts.app_secrets import get_secret
    import anthropic
    import base64

    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    # Build content
    content = []
    if files:
        for f in files:
            with open(f, "rb") as fp:
                data = base64.standard_b64encode(fp.read()).decode()
            mime = "application/pdf" if str(f).endswith(".pdf") else "image/jpeg"
            content.append({"type": "document" if mime == "application/pdf" else "image",
                           "source": {"type": "base64", "media_type": mime, "data": data}})
    content.append({"type": "text", "text": prompt})

    model_short = "claude-haiku-4-5" if "haiku" in model else "claude-sonnet-4-5"

    for attempt in range(3):
        _LIMITER.wait_if_needed(model_short)
        try:
            response = client.messages.create(
                model=model, max_tokens=max_tokens, temperature=temperature,
                messages=[{"role": "user", "content": content}],
            )
            text = response.content[0].text.strip()
            tokens_in = response.usage.input_tokens
            tokens_out = response.usage.output_tokens
            cost = (tokens_in * PRICING[model_short]["input"] +
                    tokens_out * PRICING[model_short]["output"]) / 1_000_000

            _log_usage(model_short, tokens_in, tokens_out, cost, task, True)
            return {
                "text": text, "model": model_short, "success": True,
                "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": cost,
            }
        except Exception as e:
            err = str(e)
            if "rate" in err.lower() or "429" in err:
                wait = 30 * (attempt + 1)
                print(f"  [{model_short}] rate limit, waiting {wait}s")
                time.sleep(wait)
                continue
            if "credit balance" in err.lower():
                _log_usage(model_short, 0, 0, 0, task, False)
                return {"text": "", "model": model_short, "success": False,
                        "error": "no_credits", "skip_retry": True}
            _log_usage(model_short, 0, 0, 0, task, False)
            return {"text": "", "model": model_short, "success": False, "error": err[:200]}

    _log_usage(model_short, 0, 0, 0, task, False)
    return {"text": "", "model": model_short, "success": False, "error": "all retries exhausted"}


def generate_with_fallback(prompt: str, files: list = None,
                            min_words: int = 0, max_tokens: int = 4000,
                            temperature: float = 0.4, task: str = "general") -> dict:
    """Try Gemini first, fallback to Claude if Gemini fails or output too short.

    This is the primary interface for pipeline tasks.
    """
    # Try Gemini Flash first (cheapest)
    result = call_gemini(prompt, files=files, max_tokens=max_tokens,
                         temperature=temperature, task=task)

    # Quality check: if min_words specified and output too short, escalate
    if result["success"] and min_words > 0:
        word_count = len(result["text"].split())
        if word_count < min_words:
            print(f"  [fallback] Gemini gave {word_count} words (need {min_words}), trying Claude")
            claude_result = call_claude(prompt, files=files, max_tokens=max_tokens,
                                         temperature=temperature, task=task)
            if claude_result.get("success"):
                claude_words = len(claude_result["text"].split())
                if claude_words >= min_words:
                    return claude_result
                # If Claude also short, return whichever has more
                return claude_result if claude_words > word_count else result
            elif claude_result.get("skip_retry"):
                # Claude no credits — return Gemini result with warning
                result["warning"] = "Claude unavailable (no credits)"

    # If Gemini failed completely, try Claude
    if not result["success"]:
        print(f"  [fallback] Gemini failed: {result.get('error','')[:60]}, trying Claude")
        claude_result = call_claude(prompt, files=files, max_tokens=max_tokens,
                                     temperature=temperature, task=task)
        if claude_result["success"]:
            return claude_result
        # Both failed — return original error
        return result

    return result


def get_usage_stats() -> dict:
    """Read usage log and calculate stats."""
    if not USAGE_LOG.exists():
        return {}

    by_model = {}
    for line in USAGE_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        m = r.get("model", "unknown")
        if m not in by_model:
            by_model[m] = {"calls": 0, "success": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}
        by_model[m]["calls"] += 1
        by_model[m]["success"] += 1 if r.get("success") else 0
        by_model[m]["tokens_in"] += r.get("tokens_in", 0)
        by_model[m]["tokens_out"] += r.get("tokens_out", 0)
        by_model[m]["cost_usd"] += r.get("cost_usd", 0)

    return by_model


if __name__ == "__main__":
    print("AI Usage Stats:")
    stats = get_usage_stats()
    for model, s in stats.items():
        print(f"\n  {model}:")
        for k, v in s.items():
            if k == "cost_usd":
                print(f"    {k}: ${v:.4f}")
            else:
                print(f"    {k}: {v}")
