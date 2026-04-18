"""Bundle builder for AI-Audit v0.5.

Takes raw bundle text/dict and enriches with:
- relevant_docs_excerpts: DNA / MASTER_PLAN §§ matched by keywords
- decision_class: D1-D5 from MASTER_PLAN DECISION_CLASSES (auto-tagged)
- topic_type: general | data_pipeline | etl | ingest | data_drift | data_loss | coverage_regression
- v05_builder_ran: true

Usage:
    python ai_audit/bundle_builder.py --input bundle.json --output enriched.json
    python ai_audit/bundle_builder.py --text "my proposal..." --output enriched.json
    echo '{"proposal": "..."}' | python ai_audit/bundle_builder.py --stdin

Used by AI-Audit v0.5 procedure step 1. Output fed to Claude agents as bundle
context and to Gemini (excerpts prepended to --system prompt).
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent

# Keyword → DNA section (§N format). Matches on bundle text case-insensitive.
DNA_KEYWORD_MAP: list[tuple[str, list[str]]] = [
    ("frozen", ["§3"]),
    ("pinned api", ["§4"]),
    ("pinned", ["§4"]),
    ("invariant", ["§3", "§4"]),
    ("irreversible", ["§3", "§5"]),
    ("forever", ["§3"]),
    ("architectural", ["§3", "§7"]),
    ("dml", ["§5", "§5b"]),
    ("tier-3", ["§5"]),
    ("tier 3", ["§5"]),
    ("reconciliation", ["§5"]),
    ("revenue", ["§5b"]),
    ("rev_", ["§5b"]),
    ("fail loud", ["§7"]),
    ("silent failure", ["§7"]),
    ("silent drop", ["§7"]),
    ("source of truth", ["§7"]),
    ("single source", ["§7"]),
    ("idempoten", ["§7"]),
]

MASTER_KEYWORD_MAP: list[tuple[str, list[str]]] = [
    ("decision_class", ["DECISION_CLASSES"]),
    ("d4", ["DECISION_CLASSES"]),
    ("d5", ["DECISION_CLASSES"]),
    ("financial", ["DECISION_CLASSES"]),
    ("frozen file", ["DECISION_CLASSES"]),
]

# decision_class keyword patterns (first match wins — more severe listed first).
DECISION_CLASS_PATTERNS: list[tuple[str, list[str]]] = [
    ("D5", ["frozen file", "pinned api", "architectural invariant", "irreversible"]),
    ("D4", ["invoice", "payment", "reconciliation", "order_ledger", "financial",
            "billing", "currency", "vat", "НДС", "счёт на оплату"]),
    ("D3", ["pipeline", "etl", "ingest", "data loss", "coverage regression",
            "records dropped", "silent drop"]),
    ("D2", ["schema change", "migration", "alter table", "drop table"]),
]

TOPIC_TYPE_PATTERNS: list[tuple[str, list[str]]] = [
    ("coverage_regression", ["coverage regression", "coverage dropped"]),
    ("data_loss", ["records to 0", "dropped to zero", "data loss", "silent drop", "weeks существовало"]),
    ("data_drift", ["drift", "output changed"]),
    ("etl", ["etl "]),
    ("ingest", ["ingest"]),
    ("data_pipeline", ["pipeline", "writer", "reader"]),
]


def _extract_section(text: str, section_marker: str) -> str:
    """Extract §N section from a document. Returns up to 2000 chars."""
    stripped = section_marker.lstrip("§").strip()
    pattern = rf"(§\s*{re.escape(stripped)}[^\n]*\n.*?)(?=\n§\s*\d|\Z)"
    m = re.search(pattern, text, re.DOTALL)
    if m:
        return m.group(1).strip()[:2000]
    # Fallback: header match (## DECISION_CLASSES-style)
    pattern2 = rf"^(##+ [^\n]*{re.escape(stripped)}[^\n]*\n.*?)(?=\n##+ |\Z)"
    m = re.search(pattern2, text, re.MULTILINE | re.DOTALL)
    if m:
        return m.group(1).strip()[:2000]
    return ""


# Patch 2 (v0.5.1): indirect prompt injection sanitization.
# Refs: Greshake 2023 (arXiv:2302.12173), OWASP LLM01:2025, Shi 2024 JudgeDeceiver.
# Strategy: strip control markers, wrap content in UNTRUSTED_EXCERPT delimiters,
# reject high-entropy non-language runs, flag known IPI strings.
_INJECTION_MARKER_PATTERNS = [
    re.compile(r"<\s*/?\s*(system|user|assistant)\s*>", re.IGNORECASE),
    re.compile(r"\[/?INST\]"),
    re.compile(r"<\|im_(start|end)\|>", re.IGNORECASE),
    re.compile(r"===\s*SYSTEM\s*===", re.IGNORECASE),
    re.compile(r"<\s*/?\s*(prompt|role|instructions?)\s*>", re.IGNORECASE),
]

_IPI_STRING_PATTERNS = [
    re.compile(r"ignore\s+(previous|above|prior)\s+(instructions?|prompts?)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|above)", re.IGNORECASE),
    re.compile(r"(senior\s+)?auditor\s+sign-?off", re.IGNORECASE),
    re.compile(r"(prior|previous)\s+(review|audit)\s+record", re.IGNORECASE),
    re.compile(r"automated\s+agents?\s*[:,]?\s*verdict\s*=", re.IGNORECASE),
    re.compile(r"recommended_verdict\s*[:=]", re.IGNORECASE),
    re.compile(r"\bapprove_automatic\b|\bauto[-_]?approve\b", re.IGNORECASE),
]


def _sanitize_excerpt(text: str) -> tuple[str, list[str]]:
    """Strip known prompt-injection markers. Returns (cleaned_text, suspect_spans)."""
    suspect_spans: list[str] = []
    cleaned = text

    # Strip HTML/XML-like role/system markers
    for pat in _INJECTION_MARKER_PATTERNS:
        for m in pat.finditer(cleaned):
            suspect_spans.append(f"marker: {m.group(0)!r}")
        cleaned = pat.sub("[redacted-role-marker]", cleaned)

    # Flag (but don't strip — preserve evidence) known IPI strings
    for pat in _IPI_STRING_PATTERNS:
        for m in pat.finditer(cleaned):
            # Capture surrounding context for forensics
            start = max(0, m.start() - 40)
            end = min(len(cleaned), m.end() + 40)
            suspect_spans.append(f"ipi_pattern: ...{cleaned[start:end]!r}...")

    # GCG adversarial suffix heuristic (Zou 2023): long high-entropy non-language runs
    # Crude: stretch of 30+ characters with no whitespace and many non-ASCII/symbol
    for m in re.finditer(r"\S{30,}", cleaned):
        token = m.group(0)
        non_alnum = sum(1 for c in token if not (c.isalnum() or c in "._-/:"))
        if non_alnum / max(len(token), 1) > 0.3:
            suspect_spans.append(f"gcg_suspect: {token[:60]!r}")

    return cleaned, suspect_spans


def _wrap_untrusted(idx: int, sha: str, content: str) -> str:
    """Wrap excerpt in UNTRUSTED delimiters so agents know this is CONTENT, not INSTRUCTIONS."""
    return (
        f"<<< UNTRUSTED_EXCERPT id={idx} sha256={sha[:12]} >>>\n"
        f"{content}\n"
        f"<<< END_UNTRUSTED_EXCERPT id={idx} >>>"
    )


def _match_excerpts(bundle_text: str, dna_text: str, master_text: str) -> list[dict[str, str]]:
    import hashlib
    bundle_lower = bundle_text.lower()
    seen: set[tuple[str, str]] = set()
    excerpts: list[dict[str, str]] = []
    idx = 0

    def _append(source: str, section: str, kw: str, raw_text: str) -> None:
        nonlocal idx
        idx += 1
        clean, suspects = _sanitize_excerpt(raw_text)
        sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        entry = {
            "source": source,
            "section": section,
            "matched_keyword": kw,
            "sha256": sha,
            "text": _wrap_untrusted(idx, sha, clean),
        }
        if suspects:
            entry["injection_flags"] = suspects
        excerpts.append(entry)

    for kw, sections in DNA_KEYWORD_MAP:
        if kw.lower() in bundle_lower:
            for sec in sections:
                key = ("DNA", sec)
                if key in seen:
                    continue
                seen.add(key)
                text = _extract_section(dna_text, sec)
                if text:
                    _append("docs/PROJECT_DNA.md", sec, kw, text)

    for kw, sections in MASTER_KEYWORD_MAP:
        if kw.lower() in bundle_lower:
            for sec in sections:
                key = ("MASTER", sec)
                if key in seen:
                    continue
                seen.add(key)
                text = _extract_section(master_text, sec)
                if text:
                    _append("docs/MASTER_PLAN_v1_9_2.md", sec, kw, text)
    return excerpts


def _detect_decision_class(bundle_text: str) -> str:
    bundle_lower = bundle_text.lower()
    for cls, patterns in DECISION_CLASS_PATTERNS:
        for pat in patterns:
            if pat.lower() in bundle_lower:
                return cls
    return "D1"


def _detect_topic_type(bundle_text: str) -> str:
    bundle_lower = bundle_text.lower()
    for tt, patterns in TOPIC_TYPE_PATTERNS:
        for pat in patterns:
            if pat.lower() in bundle_lower:
                return tt
    return "general"


def enrich(bundle: dict[str, Any]) -> dict[str, Any]:
    """Enrich bundle with v0.5 auto-fields (decision_class, topic_type, excerpts).

    Existing keys in the bundle are preserved — caller can set decision_class
    manually and bundle_builder will not overwrite.

    v0.5.1 (Patch 2): bundle_text itself is scanned for prompt-injection patterns;
    flags are returned in `bundle_injection_flags` for arbiter pre-audit review.
    """
    text_parts: list[str] = []
    for key, val in bundle.items():
        if isinstance(val, str):
            text_parts.append(val)
        elif isinstance(val, (list, dict)):
            text_parts.append(json.dumps(val, ensure_ascii=False))
    bundle_text = "\n".join(text_parts)

    dna_path = ROOT / "docs" / "PROJECT_DNA.md"
    master_path = ROOT / "docs" / "MASTER_PLAN_v1_9_2.md"
    dna_text = dna_path.read_text(encoding="utf-8") if dna_path.exists() else ""
    master_text = master_path.read_text(encoding="utf-8") if master_path.exists() else ""

    enriched = dict(bundle)
    enriched["decision_class"] = bundle.get("decision_class") or _detect_decision_class(bundle_text)
    enriched["topic_type"] = bundle.get("topic_type") or _detect_topic_type(bundle_text)
    existing = bundle.get("relevant_docs_excerpts")
    enriched["relevant_docs_excerpts"] = existing if existing else _match_excerpts(bundle_text, dna_text, master_text)

    # Patch 2: scan the bundle proposal itself for injection attempts
    _, bundle_suspects = _sanitize_excerpt(bundle_text)
    if bundle_suspects:
        enriched["bundle_injection_flags"] = bundle_suspects

    enriched["v05_builder_ran"] = True
    enriched["schema_version"] = "0.5.1"
    return enriched


def main() -> int:
    ap = argparse.ArgumentParser(description="AI-Audit v0.5 bundle enricher")
    ap.add_argument("--input", help="JSON file with raw bundle")
    ap.add_argument("--output", help="Write enriched bundle here (default: stdout)")
    ap.add_argument("--text", help="One-shot: treat TEXT as bundle.proposal")
    ap.add_argument("--stdin", action="store_true", help="Read JSON bundle from stdin")
    args = ap.parse_args()

    if args.text:
        bundle = {"proposal": args.text}
    elif args.stdin:
        bundle = json.load(sys.stdin)
    elif args.input:
        bundle = json.loads(Path(args.input).read_text(encoding="utf-8"))
    else:
        print("Provide --input, --text or --stdin", file=sys.stderr)
        return 1

    enriched = enrich(bundle)
    out_json = json.dumps(enriched, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(out_json, encoding="utf-8")
        print(f"wrote {args.output} ({len(enriched.get('relevant_docs_excerpts', []))} excerpts, "
              f"decision_class={enriched['decision_class']}, topic_type={enriched['topic_type']})",
              file=sys.stderr)
    else:
        print(out_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
