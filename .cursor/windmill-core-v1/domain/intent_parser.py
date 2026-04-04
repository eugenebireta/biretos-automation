"""
Intent parser — Phase 7.3.

Regex-only in Phase 7; llm_fn is injectable for future wiring.
parse_intent() is a pure function (no DB, no network).
"""
from __future__ import annotations

import hashlib
import re
import time
from typing import Callable, Dict, List, Optional, Tuple

from .nlu_models import (
    CONFIDENCE_HIGH,
    SUPPORTED_NLU_INTENTS,
    NLUConfig,
    NLUResult,
    ParsedIntent,
)

# ---------------------------------------------------------------------------
# Regex rule table
# ---------------------------------------------------------------------------

# Each rule: intent_type, patterns (any match = candidate),
# entity_extractors: list of (entity_name, [patterns]) — first match wins.

_REGEX_RULES: List[Dict] = [
    {
        "intent_type": "check_payment",
        "patterns": [
            r"провер[ие]ть?\s+платёж",
            r"провер[ие]ть?\s+(платёж|счёт|оплату|оплаты)",
            r"статус\s+(платежа|счёта|оплаты|оплат)",
            r"check\s+pay",
            r"invoice\s+status",
            r"payment\s+status",
            r"оплачен",
        ],
        "entity_extractors": [
            (
                "invoice_id",
                [
                    r"\bINV[-_]([\w\d]+)\b",
                    r"\bSCH[-_]([\w\d]+)\b",
                    r"\b(INV[\w\d]+)\b",
                    # Numeric invoice/bill number (6+ digits)
                    r"\b(\d{6,20})\b",
                ],
            )
        ],
    },
    {
        "intent_type": "get_tracking",
        "patterns": [
            r"отследить",
            r"трекинг",
            r"tracking",
            r"где\s+(посылка|заказ|груз|отправление)",
            r"статус\s+(доставки|отправления|посылки)",
            r"delivery\s+status",
        ],
        "entity_extractors": [
            (
                "carrier_external_id",
                [
                    # UUID pattern
                    r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
                    # CDEK order number
                    r"\b(CDEK[-_][\w\d]{4,})\b",
                    # Generic tracking number (8+ digits)
                    r"\b(\d{8,20})\b",
                ],
            )
        ],
    },
    {
        "intent_type": "get_waybill",
        "patterns": [
            r"накладн",
            r"waybill",
            r"стикер",
            r"этикетк",
            r"label",
            r"распечат",
        ],
        "entity_extractors": [
            (
                "carrier_external_id",
                [
                    r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
                    r"\b(CDEK[-_][\w\d]{4,})\b",
                    # Generic tracking number (8+ digits)
                    r"\b(\d{8,20})\b",
                ],
            )
        ],
    },
    {
        "intent_type": "send_invoice",
        "patterns": [
            r"выстав[ить]*\s+счёт",
            r"выставить\s+счёт",
            r"создать?\s+счёт",
            r"send\s+invoice",
            r"issue\s+invoice",
            r"новый\s+счёт",
        ],
        "entity_extractors": [
            (
                "insales_order_id",
                [
                    r"(?:РІС‹СЃС‚Р°РІ[РёС‚СЊ]*\s+СЃС‡С‘С‚|СЃРѕР·РґР°С‚СЊ?\s+СЃС‡С‘С‚|send\s+invoice|issue\s+invoice|РЅРѕРІС‹Р№\s+СЃС‡С‘С‚)\s*[#в„–: -]?\s*([A-Za-z0-9_-]*\d[A-Za-z0-9_-]*)\b",
                    r"(?:Р·Р°РєР°Р·(?:Сѓ|Р°)?|order)\s*[#в„–: -]?\s*([A-Za-z0-9_-]*\d[A-Za-z0-9_-]*)\b",
                ],
            )
        ],
    },
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _text_hash(text: str) -> str:
    """Return first 12 chars of SHA-256 hex of text (for log correlation)."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]


def _match_rule(text_lower: str, rule: Dict) -> Tuple[bool, float]:
    """
    Returns (matched, confidence).
    confidence = 1.0 for regex (deterministic).
    """
    for pattern in rule["patterns"]:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True, 1.0
    return False, 0.0


def _extract_entities(text: str, extractors: List[Tuple[str, List[str]]]) -> Dict[str, str]:
    entities: Dict[str, str] = {}
    for entity_name, patterns in extractors:
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                entities[entity_name] = m.group(1) if m.lastindex else m.group(0)
                break
    return entities


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_intent(
    sanitized_text: str,
    config: NLUConfig,
    *,
    llm_fn: Optional[Callable[[str, NLUConfig], Optional[ParsedIntent]]] = None,
) -> NLUResult:
    """
    Parse sanitized_text into a ParsedIntent.

    Execution path:
      1. If config.degradation_level >= 2 (BUTTON_ONLY) → return button_only immediately.
      2. Try regex rules.
      3. If no regex match AND llm_fn provided → call llm_fn (future wiring).
      4. If confidence < threshold → return fallback (ASSISTED mode).
      5. Otherwise return ok with ParsedIntent.

    Args:
        sanitized_text: output of sanitize_nlu_input() — already truncated + stripped.
        config: NLUConfig snapshot.
        llm_fn: optional LLM callable (not used in Phase 7).

    Returns:
        NLUResult
    """
    t0 = time.monotonic()

    def _duration() -> int:
        return max(0, int((time.monotonic() - t0) * 1000))

    if not config.nlu_enabled or config.degradation_level >= 2:
        return NLUResult(
            status="button_only",
            parsed=None,
            degradation_level=config.degradation_level,
            parse_duration_ms=_duration(),
        )

    text_lower = sanitized_text.lower()
    raw_hash = _text_hash(sanitized_text)

    # Try regex rules — first match wins
    matched_intent: Optional[str] = None
    matched_confidence: float = 0.0
    matched_entities: Dict[str, str] = {}

    for rule in _REGEX_RULES:
        matched, conf = _match_rule(text_lower, rule)
        if matched:
            matched_intent = rule["intent_type"]
            matched_confidence = conf
            matched_entities = _extract_entities(sanitized_text, rule["entity_extractors"])
            break

    # If no regex match, try LLM (injectable, not called in Phase 7)
    if matched_intent is None and llm_fn is not None:
        llm_result = llm_fn(sanitized_text, config)
        if llm_result is not None:
            return NLUResult(
                status="ok",
                parsed=llm_result,
                degradation_level=config.degradation_level,
                parse_duration_ms=_duration(),
            )

    if matched_intent is None:
        return NLUResult(
            status="fallback",
            parsed=None,
            degradation_level=config.degradation_level,
            parse_duration_ms=_duration(),
            error="no_regex_match",
        )

    parsed = ParsedIntent(
        intent_type=matched_intent,
        entities=matched_entities,
        confidence=matched_confidence,
        model_version=config.model_version,
        prompt_version=config.prompt_version,
        raw_text_hash=raw_hash,
    )

    # Low confidence → ASSISTED (offer choice buttons instead of direct confirm)
    if matched_confidence < config.confidence_threshold:
        return NLUResult(
            status="fallback",
            parsed=parsed,
            degradation_level=max(config.degradation_level, 1),
            parse_duration_ms=_duration(),
        )

    # Shadow mode: parse succeeded but do NOT offer confirmation
    if config.shadow_mode:
        return NLUResult(
            status="shadow",
            parsed=parsed,
            degradation_level=config.degradation_level,
            parse_duration_ms=_duration(),
        )

    return NLUResult(
        status="ok",
        parsed=parsed,
        degradation_level=config.degradation_level,
        parse_duration_ms=_duration(),
    )
