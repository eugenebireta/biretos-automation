"""
providers/gemini_auditor.py — Google Gemini API (google-genai SDK).

Replaces OpenAI auditor. Role: CRITIC (first-pass review).

SPEC §20.8 compliance:
  API key passed directly — NEVER via os.environ.
  Uses dotenv_values() from .env.auditors, never load_dotenv().

Uses google-genai SDK (google.genai), NOT deprecated google.generativeai.
JSON extracted from text response (Gemini does not guarantee structured output).
"""
from __future__ import annotations

import logging
import re
from typing import Any

from ..hard_shell.contracts import AuditVerdict, TaskPack
from ..hard_shell.schema_validator import validate_and_parse
from .base import AuditorProvider
from .openai_auditor import _build_system_prompt, _build_user_prompt

logger = logging.getLogger(__name__)


class GeminiAuditor(AuditorProvider):
    """
    Auditor using Google Gemini API (google-genai SDK).
    API key passed directly — NOT from os.environ (SPEC §20.8).

    Response parsing: JSON extracted from text with markdown fence fallback.
    """

    auditor_id = "gemini"

    def __init__(
        self,
        model: str = "gemini-3.1-pro-preview",
        api_key: str | None = None,
        max_output_tokens: int = 8192,
        temperature: float = 0.2,
    ):
        if not api_key:
            raise ValueError("GeminiAuditor: api_key is required (SPEC §20.8)")
        self.model = model
        self._api_key = api_key  # NEVER log (DNA §7)
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature

        # Lazy import — avoid hard dependency at module load
        from google import genai
        from google.genai import types
        self._client = genai.Client(api_key=api_key)
        self._types = types

    def _extract_json(self, text: str) -> str:
        """
        Extract JSON object from Gemini response text.
        Handles: raw JSON, markdown fences, prose+JSON, trailing commas.
        """
        text = text.strip()

        # Markdown code fence
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1)
        elif not text.startswith("{"):
            # Find first { to last }
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                text = text[start : end + 1]

        # Remove trailing commas (Gemini sometimes generates non-standard JSON)
        text = re.sub(r",\s*([\]}])", r"\1", text)
        return text

    async def _call(
        self,
        proposal: str,
        task: TaskPack,
        context: dict[str, Any],
        stage: str,
    ) -> AuditVerdict:
        system_prompt = _build_system_prompt(context)
        user_prompt = (
            _build_user_prompt(proposal, task, stage, context)
            + "\n\nReturn ONLY a JSON object matching the schema above. No prose outside JSON."
        )

        # Gemini combines system + user into a single contents list
        full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"

        logger.info(
            "gemini_auditor: calling API model=%s task_id=%s stage=%s",
            self.model, task.task_id, stage,
        )

        # google-genai SDK uses synchronous client.models.generate_content()
        # Wrap in asyncio executor for async compatibility
        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._client.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config=self._types.GenerateContentConfig(
                    temperature=self._temperature,
                    max_output_tokens=self._max_output_tokens,
                ),
            ),
        )

        raw_text = response.text if response.text else ""
        logger.info(
            "gemini_auditor: response received task_id=%s stage=%s len=%d",
            task.task_id, stage, len(raw_text),
        )

        json_text = self._extract_json(raw_text)
        try:
            verdict = validate_and_parse("gemini", json_text)
        except Exception:
            # Retry once with explicit JSON-only instruction if first attempt fails
            logger.warning("gemini_auditor: parse failed, retrying with strict JSON prompt task_id=%s", task.task_id)
            retry_prompt = (
                "You must respond with ONLY a valid JSON object, nothing else.\n"
                "No markdown, no prose, no code fences. Start your response with { and end with }.\n\n"
                + full_prompt
            )
            response2 = await loop.run_in_executor(
                None,
                lambda: self._client.models.generate_content(
                    model=self.model,
                    contents=retry_prompt,
                    config=self._types.GenerateContentConfig(
                        temperature=0.0,
                        max_output_tokens=self._max_output_tokens,
                    ),
                ),
            )
            raw_text = response2.text if response2.text else ""
            json_text = self._extract_json(raw_text)
            verdict = validate_and_parse("gemini", json_text)
        logger.info(
            "gemini_auditor: verdict=%s critical=%d warnings=%d task_id=%s",
            verdict.verdict.value, verdict.critical_count, verdict.warning_count, task.task_id,
        )
        return verdict

    async def critique(
        self,
        proposal: str,
        task: TaskPack,
        context: dict[str, Any],
    ) -> AuditVerdict:
        return await self._call(proposal, task, context, stage="proposal")

    async def final_audit(
        self,
        revised_proposal: str,
        task: TaskPack,
        context: dict[str, Any],
    ) -> AuditVerdict:
        return await self._call(revised_proposal, task, context, stage="revised_proposal")

    async def debate(
        self,
        proposal: str,
        task: TaskPack,
        context: dict[str, Any],
        peer_verdict: "AuditVerdict",
    ) -> AuditVerdict:
        """Round 2 debate: re-audit with visibility into peer's Round 1 verdict."""
        from ..debate import build_debate_context

        debate_ctx = build_debate_context(context, peer_verdict)
        return await self._call(proposal, task, debate_ctx, stage="debate")
