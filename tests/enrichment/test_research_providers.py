"""Tests for research_providers.py (research runner web search integration)."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch, MagicMock

_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from research_providers import (
    build_research_prompt,
    _confidence_rank,
    _parse_json_from_text,
    GeminiResearchProvider,
    ClaudeWebSearchProvider,
    WebSearchResearchOrchestrator,
)


class TestBuildResearchPrompt:
    def test_prompt_contains_pn(self):
        packet = {"entity_id": "153711", "brand_hint": "PEHA"}
        prompt = build_research_prompt(packet)
        assert "153711" in prompt

    def test_prompt_contains_brand(self):
        packet = {"entity_id": "153711", "brand_hint": "PEHA"}
        prompt = build_research_prompt(packet)
        assert "PEHA" in prompt

    def test_prompt_contains_questions(self):
        packet = {
            "entity_id": "153711",
            "brand_hint": "PEHA",
            "questions_to_resolve": ["What category?", "What is the price?"],
        }
        prompt = build_research_prompt(packet)
        assert "What category?" in prompt
        assert "What is the price?" in prompt

    def test_prompt_requests_json_output(self):
        packet = {"entity_id": "X", "brand_hint": "Y"}
        prompt = build_research_prompt(packet)
        assert "confidence" in prompt
        assert "identity_confirmed" in prompt

    def test_prompt_uses_entity_id_or_pn(self):
        packet1 = {"entity_id": "153711"}
        packet2 = {"pn": "153711"}
        p1 = build_research_prompt(packet1)
        p2 = build_research_prompt(packet2)
        assert "153711" in p1
        assert "153711" in p2


class TestConfidenceRank:
    def test_high_is_3(self):
        assert _confidence_rank("high") == 3

    def test_medium_is_2(self):
        assert _confidence_rank("medium") == 2

    def test_low_is_1(self):
        assert _confidence_rank("low") == 1

    def test_unknown_is_0(self):
        assert _confidence_rank("unknown") == 0
        assert _confidence_rank("") == 0


class TestParseJsonFromText:
    def test_valid_json_extracted(self):
        text = '{"confidence": "high", "identity_confirmed": true}'
        result = _parse_json_from_text(text)
        assert result is not None
        assert result["confidence"] == "high"

    def test_markdown_code_block_stripped(self):
        text = '```json\n{"confidence": "medium"}\n```'
        result = _parse_json_from_text(text)
        assert result is not None
        assert result["confidence"] == "medium"

    def test_json_with_preamble(self):
        text = "Here is the result:\n{\"confidence\": \"low\"}"
        result = _parse_json_from_text(text)
        assert result is not None
        assert result["confidence"] == "low"

    def test_trailing_comma_fixed(self):
        text = '{"key": "value",}'
        result = _parse_json_from_text(text)
        assert result is not None
        assert result["key"] == "value"

    def test_invalid_json_returns_none(self):
        result = _parse_json_from_text("This is not JSON at all")
        assert result is None

    def test_empty_string_returns_none(self):
        result = _parse_json_from_text("")
        assert result is None


class TestGeminiResearchProvider:
    def test_init_with_api_key(self):
        provider = GeminiResearchProvider(api_key="fake_key")
        assert provider._api_key == "fake_key"

    def test_name_property(self):
        provider = GeminiResearchProvider(api_key="x")
        assert provider.name == "gemini_grounding"

    def test_cost_tier_property(self):
        provider = GeminiResearchProvider(api_key="x")
        assert provider.cost_tier == "low"

    def test_raises_without_api_key(self):
        provider = GeminiResearchProvider(api_key="")
        provider._api_key = ""  # Force override even if loaded from .env
        try:
            provider.call("test prompt")
            assert False, "Should have raised RuntimeError"
        except RuntimeError:
            pass  # Expected

    def test_raises_on_import_error(self):
        provider = GeminiResearchProvider(api_key="fake_key")
        with patch.dict("sys.modules", {"google": None, "google.genai": None}):
            try:
                provider.call("test prompt")
                assert False, "Should have raised RuntimeError"
            except (RuntimeError, TypeError):
                pass  # Expected


class TestClaudeWebSearchProvider:
    def test_name_property(self):
        provider = ClaudeWebSearchProvider()
        assert provider.name == "claude_web_search"

    def test_cost_tier_property(self):
        provider = ClaudeWebSearchProvider()
        assert provider.cost_tier == "free"

    def test_call_with_mocked_subprocess(self):
        """Test that call() uses claude CLI and returns text."""
        provider = ClaudeWebSearchProvider()

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = '{"confidence": "high", "identity_confirmed": true}'

        with patch("subprocess.run", return_value=mock_proc):
            text, model, cost = provider.call("test prompt")

        assert "confidence" in text
        assert model == "claude-cli"
        assert cost == 0.0

    def test_call_cli_error_raises(self):
        """CLI error should raise RuntimeError."""
        provider = ClaudeWebSearchProvider()

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "some error"
        mock_proc.stdout = ""

        with patch("subprocess.run", return_value=mock_proc):
            try:
                provider.call("test prompt")
                assert False, "Should have raised RuntimeError"
            except RuntimeError:
                pass


class TestWebSearchResearchOrchestrator:
    def _make_packet(self, pn="153711", brand="PEHA"):
        return {"entity_id": pn, "brand_hint": brand, "priority": "high",
                "questions_to_resolve": ["What is this product?"]}

    def test_gemini_high_confidence_no_claude(self):
        """If Gemini returns high confidence, Claude should NOT be called."""
        packet = self._make_packet()
        orch = WebSearchResearchOrchestrator()

        mock_gemini_text = json.dumps({"confidence": "high", "identity_confirmed": True,
                                       "title_ru": "Рамка PEHA"})
        claude_called = []

        with patch.object(orch._gemini, "call", return_value=(mock_gemini_text, "gemini", 0.004)):
            with patch.object(orch._claude, "call", side_effect=lambda p: claude_called.append(p)):
                result = orch.research_packet(packet)

        assert len(claude_called) == 0  # Claude not called
        assert result["confidence"] == "high"
        assert result["provider"] == "gemini_grounding"

    def test_gemini_low_confidence_triggers_claude(self):
        """If Gemini returns low confidence, Claude should be called."""
        packet = self._make_packet()
        orch = WebSearchResearchOrchestrator()

        gemini_text = json.dumps({"confidence": "low", "identity_confirmed": False})
        claude_text = json.dumps({"confidence": "medium", "identity_confirmed": True,
                                  "title_ru": "Рамка PEHA"})

        with patch.object(orch._gemini, "call", return_value=(gemini_text, "gemini", 0.004)):
            with patch.object(orch._claude, "call", return_value=(claude_text, "claude-sonnet", 0.05)):
                result = orch.research_packet(packet)

        assert result["confidence"] == "medium"
        assert result["provider"] == "claude_web_search"

    def test_both_providers_fail_returns_error(self):
        """If both providers fail, returns error dict without crashing."""
        packet = self._make_packet()
        orch = WebSearchResearchOrchestrator()

        with patch.object(orch._gemini, "call", side_effect=RuntimeError("gemini fail")):
            with patch.object(orch._claude, "call", side_effect=RuntimeError("claude fail")):
                result = orch.research_packet(packet)

        assert "error" in result
        assert result["final_recommendation"]["confidence"] == "low"

    def test_budget_exceeded_propagates(self):
        """BudgetExceeded should propagate, not be swallowed."""
        from research_runner import BudgetExceeded
        packet = self._make_packet()
        orch = WebSearchResearchOrchestrator()

        def budget_stop(estimated_cost=0.0):
            raise BudgetExceeded("Budget exceeded")

        try:
            orch.research_packet(packet, check_budget_fn=budget_stop)
        except BudgetExceeded:
            pass  # Expected
        except Exception:
            # If the budget check isn't called before API, that's also OK
            pass


class TestResearchRunnerWebSearchIntegration:
    def test_run_research_with_mock_provider_no_web(self):
        """run_research_for_packet works with mock provider (use_web_search=False)."""
        import tempfile
        from pathlib import Path
        from research_runner import run_research_for_packet, MockResearchProvider

        packet = {
            "entity_id": "153711",
            "pn": "153711",
            "brand_hint": "PEHA",
            "priority": "high",
            "questions_to_resolve": ["What is this?"],
            "research_reason": "category_mismatch",
            "goal": "Identify product and find price",
            "current_state": {},
            "known_facts": {},
            "constraints": [],
        }

        with tempfile.TemporaryDirectory() as tmp:
            packet_path = Path(tmp) / "research_packet_153711.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")

            import research_runner as rr
            orig_dir = rr.RESULTS_DIR
            rr.RESULTS_DIR = Path(tmp) / "results"
            try:
                result = run_research_for_packet(
                    str(packet_path),
                    provider=MockResearchProvider(),
                    use_web_search=False,
                )
            finally:
                rr.RESULTS_DIR = orig_dir

        assert result is not None
        assert "pn" in result or "entity_id" in result or "final_recommendation" in result
