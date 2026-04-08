"""research_providers.py — Web-search-capable research providers for research_runner.py.

Extends the existing provider interface with two web-grounded providers:
1. GeminiResearchProvider — Gemini Flash with Google Search grounding (cheap, fast)
2. ClaudeWebSearchProvider — Claude Sonnet with web_search tool (fallback for low confidence)

Strategy: Gemini first (cheap), Claude only if Gemini returns low confidence.

Provider interface: call(prompt: str) -> (response_text: str, model: str, cost_usd: float)

API keys loaded from auditor_system/config/.env.auditors (same as gemini_price_scout.py).
Budget tracked via research_runner.py budget_tracking.json.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

_ROOT = Path(_scripts_dir).parent
_SECRETS_PATH = _ROOT / "auditor_system" / "config" / ".env.auditors"

GEMINI_FLASH_MODEL = "gemini-2.5-flash"
CLAUDE_SONNET_MODEL = "claude-sonnet-4-6-20250514"

# Rough cost estimates (USD per call at ~3k tokens in + ~1.5k out)
_GEMINI_FLASH_COST = 0.004   # Flash with grounding
_CLAUDE_SONNET_COST = 0.05   # Sonnet with web_search


def _load_secrets() -> dict[str, str]:
    """Load API keys from .env.auditors (same as gemini_price_scout.py)."""
    try:
        from dotenv import dotenv_values
        if _SECRETS_PATH.exists():
            return dict(dotenv_values(str(_SECRETS_PATH)))
    except ImportError:
        pass
    # Fallback: environment variables
    return {
        "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", ""),
        "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
    }


def build_research_prompt(packet: dict) -> str:
    """Build a web-search-optimised research prompt from a research packet.

    Compatible with both Gemini grounding and Claude web_search.
    Designed to produce structured JSON output for industrial B2B products.
    """
    pn = packet.get("entity_id", packet.get("pn", ""))
    brand = packet.get("brand_hint", packet.get("brand", "unknown"))
    questions = packet.get("questions_to_resolve", [])
    priority = packet.get("priority", "medium")

    questions_text = "\n".join(f"- {q}" for q in questions[:8]) if questions else "- What is this product?"

    return f"""Research this industrial B2B product using web search. Priority: {priority}.

Brand: {brand}
Part Number: {pn}

Search for the EXACT part number "{pn}" from brand "{brand}".

Find and verify:
{questions_text}

IMPORTANT SEARCH INSTRUCTIONS:
- Search for exact part number "{pn}" combined with "{brand}"
- Check manufacturer website, authorized distributors, datasheets
- If price found: specify currency, unit basis (per piece / per box / per pack)
- If photo found: give exact direct image URL (not page URL)
- If specs found: list key technical specifications
- If not found online: say explicitly "not found" — do NOT guess or hallucinate

Return ONLY valid JSON (no markdown, no explanation outside JSON):
{{
  "identity_confirmed": true or false,
  "brand": "brand name",
  "title_ru": "product name in Russian",
  "description_ru": "short description in Russian (1-2 sentences)",
  "category_suggestion": "product category",
  "price_assessment": "admissible_public_price" or "no_public_price" or "ambiguous_offer",
  "price_value": null or {{"amount": 12.50, "currency": "EUR", "unit_basis": "piece", "source_url": "https://..."}},
  "photo_url": null or "https://... (direct image URL)",
  "specs": {{}},
  "key_findings": ["finding 1", "finding 2"],
  "ambiguities": ["ambiguity if any"],
  "sources": [{{"url": "https://...", "type": "manufacturer or distributor or datasheet", "supports": ["identity", "price"]}}],
  "confidence": "high" or "medium" or "low",
  "confidence_notes": "why this confidence level"
}}"""


class GeminiResearchProvider:
    """Research via Gemini Flash with Google Search grounding.

    Uses same API pattern as gemini_price_scout.py:query_gemini().
    Cheap (~$0.004/call), has real web access.
    """

    def __init__(self, api_key: Optional[str] = None):
        secrets = _load_secrets()
        self._api_key = api_key or secrets.get("GEMINI_API_KEY", "")

    @property
    def name(self) -> str:
        return "gemini_grounding"

    @property
    def cost_tier(self) -> str:
        return "low"

    def call(self, prompt: str) -> tuple[str, str, float]:
        """Returns (response_text, model_name, cost_usd)."""
        if not self._api_key:
            raise RuntimeError("GEMINI_API_KEY not set")

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise RuntimeError("google-genai package not installed: pip install google-genai")

        client = genai.Client(api_key=self._api_key)
        try:
            response = client.models.generate_content(
                model=GEMINI_FLASH_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.1,
                    max_output_tokens=3000,
                ),
            )
            text = response.text or ""
            return text, GEMINI_FLASH_MODEL, _GEMINI_FLASH_COST
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {e}") from e


class ClaudeWebSearchProvider:
    """Research via Claude Sonnet with web_search tool.

    Used as fallback when Gemini returns low confidence.
    More expensive (~$0.05/call) but often more thorough.
    """

    def __init__(self, api_key: Optional[str] = None):
        secrets = _load_secrets()
        self._api_key = api_key or secrets.get("ANTHROPIC_API_KEY", "")

    @property
    def name(self) -> str:
        return "claude_web_search"

    @property
    def cost_tier(self) -> str:
        return "medium"

    def call(self, prompt: str) -> tuple[str, str, float]:
        """Returns (response_text, model_name, cost_usd)."""
        if not self._api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package not installed: pip install anthropic")

        client = anthropic.Anthropic(api_key=self._api_key)
        try:
            response = client.messages.create(
                model=CLAUDE_SONNET_MODEL,
                max_tokens=3000,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
                messages=[{"role": "user", "content": prompt}],
            )
            text_parts = []
            for block in response.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
            text = "\n".join(text_parts)
            return text, CLAUDE_SONNET_MODEL, _CLAUDE_SONNET_COST
        except Exception as e:
            raise RuntimeError(f"Claude API error: {e}") from e


def _confidence_rank(conf: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(str(conf).lower(), 0)


def _parse_json_from_text(text: str) -> Optional[dict]:
    """Extract JSON from model response text."""
    import re
    text = text.strip()
    # Strip markdown code blocks
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if match:
            text = match.group(1)

    # Find first { and last }
    brace = text.find("{")
    if brace >= 0:
        text = text[brace:]
    last = text.rfind("}")
    if last >= 0:
        text = text[:last + 1]

    # Fix trailing commas
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)

    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


class WebSearchResearchOrchestrator:
    """Multi-provider orchestrator: Gemini first, Claude fallback.

    Strategy:
    - Try Gemini grounding (cheap, has web access)
    - If result confidence == "high": done
    - If result confidence == "medium": return (don't waste money on Claude)
    - If result confidence == "low" or Gemini failed: try Claude web_search
    - Return best result

    Budget: Gemini: ~$0.004/call, Claude: ~$0.05/call
    Worst case for 50 SKU: (0.004 + 0.05) * 50 = $2.70 (well within $10/day)
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
    ):
        self._gemini = GeminiResearchProvider(api_key=gemini_api_key)
        self._claude = ClaudeWebSearchProvider(api_key=anthropic_api_key)

    def research_packet(
        self, packet: dict, check_budget_fn=None
    ) -> dict:
        """Research a packet using available providers.

        Returns result dict with provider, confidence, and parsed findings.
        Never raises — exceptions are captured in result["error"].
        """
        from research_runner import BudgetExceeded

        prompt = build_research_prompt(packet)
        pn = packet.get("entity_id", packet.get("pn", "?"))
        best_result: Optional[dict] = None
        best_confidence = 0

        for provider in [self._gemini, self._claude]:
            if check_budget_fn:
                try:
                    check_budget_fn(estimated_cost=provider.__class__.__name__ == "ClaudeWebSearchProvider" and _CLAUDE_SONNET_COST or _GEMINI_FLASH_COST)
                except BudgetExceeded:
                    raise

            try:
                response_text, model, cost = provider.call(prompt)
                parsed = _parse_json_from_text(response_text)
            except BudgetExceeded:
                raise
            except Exception as e:
                log.warning(f"Provider {provider.name} failed for {pn}: {e}")
                continue

            if not parsed:
                log.debug(f"Provider {provider.name}: could not parse JSON for {pn}")
                continue

            confidence = parsed.get("confidence", "low")
            conf_rank = _confidence_rank(confidence)

            result = {
                "provider": provider.name,
                "model": model,
                "cost_usd": cost,
                "response_raw": response_text,
                "final_recommendation": parsed,
                "confidence": confidence,
            }

            if conf_rank > best_confidence:
                best_result = result
                best_confidence = conf_rank

            # Don't continue to Claude if Gemini already gave high or medium
            if conf_rank >= 2:
                break

        if best_result is None:
            return {
                "error": "all providers failed or returned unparseable response",
                "pn": pn,
                "final_recommendation": {"confidence": "low"},
            }

        return best_result


if __name__ == "__main__":
    print("research_providers.py — web search research providers")
    print(f"Providers available: GeminiResearchProvider, ClaudeWebSearchProvider")
    print(f"Gemini Flash cost: ~${_GEMINI_FLASH_COST:.3f}/call")
    print(f"Claude Sonnet cost: ~${_CLAUDE_SONNET_COST:.3f}/call")
    print(f"Worst case 50 SKU: ~${(_GEMINI_FLASH_COST + _CLAUDE_SONNET_COST) * 50:.2f}")
    print(f"\nSecrets file: {_SECRETS_PATH}")
    secrets = _load_secrets()
    print(f"GEMINI_API_KEY set: {'Yes' if secrets.get('GEMINI_API_KEY') else 'No'}")
    print(f"ANTHROPIC_API_KEY set: {'Yes' if secrets.get('ANTHROPIC_API_KEY') else 'No'}")
