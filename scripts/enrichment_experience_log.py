"""
enrichment_experience_log.py — append-only structured log for enrichment decisions.

Purpose: compact, normalised record of significant per-SKU decisions.
Intended for RAG / local model training (NOT full prompt/response pairs).

Schema version: experience_log_v1
File:           shadow_log/experience_YYYY-MM.jsonl
"""
from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA_VERSION = "experience_log_v1"
_ANOMALY_WARNING_THRESHOLD = 5  # warn if >N DRAFT_ONLY in a single batch


def _experience_log_path(shadow_log_dir: Path) -> Path:
    month = datetime.datetime.utcnow().strftime("%Y-%m")
    return shadow_log_dir / f"experience_{month}.jsonl"


def append_experience_record(
    *,
    shadow_log_dir: Path,
    pn: str,
    task_type: str,
    decision: str,
    reason_code: str | list[str],
    evidence_refs: list[str] | None = None,
    outcome: str,
    correction_if_any: str | None = None,
    batch_id: str | None = None,
    trace_id: str | None = None,
) -> None:
    """Append one normalised experience record.

    Does NOT log:
    - raw prompts or responses
    - sensitive payload
    - full evidence bundle content

    Args:
        pn:              Part number.
        task_type:       e.g. "card_finalization", "photo_verdict", "price_extraction"
        decision:        Final decision string: card_status, verdict, price_status, etc.
        reason_code:     review_reasons list or single code string.
        evidence_refs:   Short refs to evidence used (URL domains, source types). No raw URLs.
        outcome:         Qualitative outcome: "publishable", "review_required", "no_evidence", etc.
        correction_if_any: Human correction if known, else None.
        batch_id:        run_ts or batch identifier.
        trace_id:        Trace ID if available.
    """
    if isinstance(reason_code, list):
        reason_code = "|".join(reason_code) if reason_code else "none"

    refs = evidence_refs or []
    # Normalise to domain-only to avoid leaking full URLs
    normalised_refs = []
    for ref in refs:
        if ref.startswith("http"):
            try:
                from urllib.parse import urlparse
                normalised_refs.append(urlparse(ref).netloc or ref)
            except Exception:
                normalised_refs.append(ref[:60])
        else:
            normalised_refs.append(ref[:60])

    record = {
        "schema_version": SCHEMA_VERSION,
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "pn": pn,
        "task_type": task_type,
        "decision": decision,
        "reason_code": reason_code,
        "evidence_refs": normalised_refs,
        "outcome": outcome,
        "correction_if_any": correction_if_any,
        "batch_id": batch_id,
        "trace_id": trace_id,
    }

    try:
        path = _experience_log_path(shadow_log_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.warning(f"experience_log write failed for {pn}: {exc}")


def append_batch_experience(
    *,
    shadow_log_dir: Path,
    bundles: list[dict],
    batch_id: str,
) -> None:
    """Log one experience record per newly-processed evidence bundle.

    Skips bundles with no card_status (incomplete).
    """
    for bundle in bundles:
        pn = bundle.get("pn", "?")
        card_status = bundle.get("card_status", "")
        if not card_status:
            continue

        photo_verdict = bundle.get("photo", {}).get("verdict", "")
        price_status = bundle.get("price", {}).get("price_status", "")
        review_reasons: list[str] = bundle.get("review_reasons_v2") or bundle.get("review_reasons") or []

        # Collect short evidence refs (domain only)
        refs: list[str] = []
        photo_src = bundle.get("photo", {}).get("source", "")
        if photo_src:
            refs.append(photo_src[:60])
        price_url = bundle.get("price", {}).get("source_url", "")
        if price_url:
            refs.append(price_url)

        outcome = _classify_outcome(card_status, photo_verdict, price_status)

        append_experience_record(
            shadow_log_dir=shadow_log_dir,
            pn=pn,
            task_type="card_finalization",
            decision=card_status,
            reason_code=review_reasons,
            evidence_refs=refs,
            outcome=outcome,
            batch_id=batch_id,
        )


def _classify_outcome(card_status: str, photo_verdict: str, price_status: str) -> str:
    if card_status == "AUTO_PUBLISH":
        return "publishable"
    if card_status == "REVIEW_REQUIRED":
        if photo_verdict == "KEEP" and price_status == "public_price":
            return "review_required_strong"
        return "review_required_weak"
    # DRAFT_ONLY
    if photo_verdict == "REJECT" and "no_price" in price_status:
        return "no_evidence"
    if "mismatch" in price_status:
        return "identity_mismatch"
    return "draft_incomplete"
