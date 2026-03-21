"""
NLU domain models — Phase 7.

ParsedIntent, NLUResult, NLUConfig.
These are pure data containers with no side-effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Literal, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_NLU_INTENTS: FrozenSet[str] = frozenset(
    {
        "check_payment",
        "get_tracking",
        "get_waybill",
        "send_invoice",
    }
)

CONFIDENCE_HIGH: float = 0.80


# ---------------------------------------------------------------------------
# ParsedIntent — output of the NLU layer (draft-only, never executes)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedIntent:
    """
    Result of parsing one free-text message.

    raw_text is NEVER stored here — only a 12-char SHA-256 hex prefix
    of the sanitized input, for log correlation without data leakage.
    """

    intent_type: str                     # one of SUPPORTED_NLU_INTENTS
    entities: Dict[str, str]             # e.g. {"invoice_id": "INV-123"}
    confidence: float                    # 0.0 – 1.0
    model_version: str                   # e.g. "regex-v1"
    prompt_version: str                  # e.g. "v1.0"
    raw_text_hash: str                   # SHA-256[:12] of sanitized input


# ---------------------------------------------------------------------------
# NLUResult — full outcome including timing and degradation context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NLUResult:
    status: Literal["ok", "fallback", "failed", "shadow", "button_only", "injection_rejected"]
    parsed: Optional[ParsedIntent]
    degradation_level: int               # 0=FULL_NLU, 1=ASSISTED, 2=BUTTON_ONLY
    parse_duration_ms: int
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# NLUConfig — runtime configuration snapshot (read from Config at startup)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NLUConfig:
    nlu_enabled: bool = False
    degradation_level: int = 2           # default: BUTTON_ONLY (safe)
    confidence_threshold: float = 0.80
    shadow_mode: bool = True
    model_version: str = "regex-v1"
    prompt_version: str = "v1.0"
    max_input_bytes: int = 1024
