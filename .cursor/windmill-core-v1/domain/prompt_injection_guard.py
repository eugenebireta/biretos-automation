"""
Prompt injection guard — Phase 7.6.

sanitize_nlu_input(): truncate + strip control chars before NLU parsing.
build_nlu_prompt(): XML-delimited prompt template (future LLM use).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .nlu_models import NLUConfig, SUPPORTED_NLU_INTENTS

# ---------------------------------------------------------------------------
# SanitizedInput — output of the guard
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SanitizedInput:
    text: str            # cleaned, truncated text ready for parsing
    was_truncated: bool  # True if input exceeded max_input_bytes
    was_stripped: bool   # True if control chars or injections were removed
    original_byte_len: int


# ---------------------------------------------------------------------------
# Patterns that indicate likely injection attempts
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = [
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"<\s*/\s*system\s*>", re.IGNORECASE),
    re.compile(r"<\s*user\s*>", re.IGNORECASE),
    re.compile(r"<\s*assistant\s*>", re.IGNORECASE),
    re.compile(r"ignore\s+(previous|all|above)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(previous|all|above)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Public: sanitize_nlu_input
# ---------------------------------------------------------------------------


def sanitize_nlu_input(raw_text: str, config: NLUConfig) -> SanitizedInput:
    """
    Sanitize free-text input before NLU parsing.

    Steps:
    1. Encode to UTF-8, count bytes.
    2. Truncate to config.max_input_bytes.
    3. Remove C0/C1 control characters (except TAB, LF, CR).
    4. Normalize unicode (NFC).
    5. Detect and strip injection patterns (replace with placeholder).

    Returns SanitizedInput with cleaned text and flags.

    NOTE: This function never raises; it is intentionally defensive.
    If the input cannot be decoded it returns an empty SanitizedInput.
    """
    if not isinstance(raw_text, str):
        raw_text = str(raw_text)

    original_bytes = raw_text.encode("utf-8", errors="replace")
    original_len = len(original_bytes)

    was_truncated = original_len > config.max_input_bytes
    if was_truncated:
        # Truncate on byte boundary, then decode safely
        truncated_bytes = original_bytes[: config.max_input_bytes]
        text = truncated_bytes.decode("utf-8", errors="replace")
    else:
        text = raw_text

    # Remove control chars (keep TAB=\x09, LF=\x0a, CR=\x0d)
    cleaned = _strip_control_chars(text)
    was_stripped = cleaned != text
    text = cleaned

    # Unicode normalization
    text = unicodedata.normalize("NFC", text)

    # Detect injection patterns
    for pattern in _INJECTION_PATTERNS:
        new_text = pattern.sub("[FILTERED]", text)
        if new_text != text:
            was_stripped = True
            text = new_text

    # Collapse repeated whitespace
    text = re.sub(r"[ \t]{3,}", "  ", text).strip()

    return SanitizedInput(
        text=text,
        was_truncated=was_truncated,
        was_stripped=was_stripped,
        original_byte_len=original_len,
    )


def _strip_control_chars(text: str) -> str:
    """Remove C0/C1 control characters except TAB, LF, CR."""
    result = []
    for ch in text:
        cp = ord(ch)
        # Allow TAB (9), LF (10), CR (13)
        if cp in (9, 10, 13):
            result.append(ch)
        elif cp < 0x20 or (0x7F <= cp <= 0x9F):
            # Skip control chars
            continue
        else:
            result.append(ch)
    return "".join(result)


# ---------------------------------------------------------------------------
# Public: build_nlu_prompt (for future LLM wiring — not called in Phase 7)
# ---------------------------------------------------------------------------


def build_nlu_prompt(sanitized_text: str, config: NLUConfig) -> str:
    """
    Build an XML-delimited prompt for LLM-based intent parsing.

    Uses XML delimiters to prevent injection from leaking out of the
    <user_message> block.  Not called in Phase 7 (regex-only).

    Args:
        sanitized_text: output of sanitize_nlu_input().text
        config: NLUConfig for versioning metadata.

    Returns:
        Formatted prompt string.
    """
    intents_list = "\n".join(f"  - {it}" for it in sorted(SUPPORTED_NLU_INTENTS))
    return (
        f"<system>\n"
        f"You are an intent classifier for a logistics back-office assistant.\n"
        f"Model version: {config.model_version}\n"
        f"Prompt version: {config.prompt_version}\n"
        f"Supported intents:\n{intents_list}\n"
        f"Return JSON: {{\"intent_type\": \"<intent>\", "
        f"\"entities\": {{...}}, \"confidence\": 0.0-1.0}}\n"
        f"If no intent matches, return {{\"intent_type\": null, \"confidence\": 0.0}}\n"
        f"</system>\n"
        f"<user_message>\n"
        f"{sanitized_text}\n"
        f"</user_message>"
    )
