"""research_queue.py — Research queue export for unresolved SKU enrichment.

Reads evidence bundles and emits structured research packets for SKUs that
are DRAFT_ONLY or REVIEW_REQUIRED. Packets are used by research_runner.py
to drive Claude API deep-research calls.

Deterministic — no API calls. Runnable in isolation.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Allow running directly from scripts/ dir or from repo root
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

# ── Paths (resolved relative to repo root regardless of cwd) ─────────────────
_repo_root = Path(_scripts_dir).parent
EVIDENCE_DIR    = _repo_root / "downloads" / "evidence"
QUEUE_DIR       = _repo_root / "research_queue"
PACKETS_DIR     = QUEUE_DIR / "packets"
QUEUE_JSONL     = QUEUE_DIR / "research_queue.jsonl"

PACKET_VERSION  = "v1"

# ── Research-triggering card statuses ─────────────────────────────────────────
_RESEARCH_STATUSES = frozenset({"DRAFT_ONLY", "REVIEW_REQUIRED"})

# ── Priority classification ───────────────────────────────────────────────────
# high: has price lineage + only missing identity/photo → close to resolved
# medium: has some evidence but incomplete
# low: very little evidence
_HIGH_REASONS    = frozenset({"category_mismatch", "no_price_lineage"})
_REVIEW_REASONS  = frozenset({"IDENTITY_WEAK", "NO_IMAGE_EVIDENCE", "NO_PDF_EVIDENCE"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def determine_research_reason(bundle: dict) -> str:
    """Classify the primary reason this SKU needs research.

    Returns one of:
      admissibility_review | category_mismatch | specs_gap |
      photo_mismatch | identity_weak | no_price_lineage
    """
    price_block = bundle.get("price", {})
    review_reasons = bundle.get("review_reasons", [])
    price_status = price_block.get("price_status", "no_price_found")
    category_mismatch = price_block.get("category_mismatch", False)
    photo_verdict = bundle.get("photo", {}).get("verdict", "REJECT")
    identity_level = bundle.get("policy_decision_v2", {}).get("identity_level", "")
    price_lineage = price_block.get("price_source_exact_product_lineage_confirmed", False)

    if price_status in ("rejected_sanity_check", "category_mismatch_only") or category_mismatch:
        return "category_mismatch"
    if price_status in ("no_price_found", "hidden_price", "rfq_only") and not price_lineage:
        return "no_price_lineage"
    if identity_level == "weak" or "IDENTITY_WEAK" in review_reasons:
        return "identity_weak"
    if photo_verdict == "REJECT" or "NO_IMAGE_EVIDENCE" in review_reasons:
        return "photo_mismatch"
    if price_status == "review_required":
        return "admissibility_review"
    # Default: specs / general enrichment gap
    return "specs_gap"


def classify_priority(bundle: dict, reason: str) -> str:
    """Classify research priority: high | medium | low."""
    price_block = bundle.get("price", {})
    has_price = bool(price_block.get("price_source_exact_product_lineage_confirmed"))
    has_photo = bundle.get("photo", {}).get("verdict") == "KEEP"
    identity_level = bundle.get("policy_decision_v2", {}).get("identity_level", "")

    if reason == "category_mismatch" and has_price:
        return "high"
    if reason == "no_price_lineage" and has_photo:
        return "high"
    if reason in ("identity_weak",) and not has_price and not has_photo:
        return "low"
    if identity_level == "strong":
        return "high"
    if identity_level == "moderate":
        return "medium"
    return "low"


def generate_questions(pn: str, bundle: dict, reason: str) -> list[str]:
    """Generate targeted research questions based on the reason."""
    brand = bundle.get("brand", "Honeywell")
    name = bundle.get("name", "")
    questions: list[str] = []

    if reason == "identity_weak":
        questions.extend([
            f"Confirm the exact product identity for {brand} PN={pn}",
            f"What is the full product name and product family for {brand} {pn}?",
            f"Is {pn} a current, discontinued, or superseded part number?",
        ])
    elif reason == "category_mismatch":
        expected = bundle.get("expected_category", "")
        questions.extend([
            f"What is the correct product category for {brand} {pn} ({name})?",
            f"Is the expected category '{expected}' correct for this product?",
            "What similar part numbers exist in the same product family?",
        ])
    elif reason == "no_price_lineage":
        questions.extend([
            f"Find a public market price for {brand} {pn} from a verifiable distributor",
            f"Is {pn} RFQ-only or available with published pricing?",
            "Which authorized distributors carry this part number?",
        ])
    elif reason == "photo_mismatch":
        questions.extend([
            f"Find the official product image for {brand} {pn}",
            "Is there a manufacturer page with product images?",
            f"What does {brand} {pn} physically look like?",
        ])
    elif reason == "admissibility_review":
        questions.extend([
            f"Verify the price admissibility for {brand} {pn}",
            "Is the found price a unit price or bulk/case price?",
            "Are there multiple distributors with consistent pricing?",
        ])
    else:  # specs_gap
        questions.extend([
            f"Find technical specifications for {brand} {pn}",
            "What are the key technical parameters and operating conditions?",
            f"Is there a product datasheet for {brand} {pn}?",
        ])

    questions.append(f"Provide any relevant Russian-language product description for {brand} {pn}")
    return questions


def extract_current_state(bundle: dict) -> dict:
    """Extract a concise current-state summary for the research packet."""
    price_block = bundle.get("price", {})
    photo_block = bundle.get("photo", {})
    confidence = bundle.get("confidence", {})
    return {
        "card_status": bundle.get("card_status"),
        "identity_level": bundle.get("policy_decision_v2", {}).get("identity_level", "unknown"),
        "photo_verdict": photo_block.get("verdict"),
        "price_status": price_block.get("price_status"),
        "price_source_url": price_block.get("source_url"),
        "category_mismatch": price_block.get("category_mismatch"),
        "overall_confidence": confidence.get("overall_label"),
        "review_reasons": bundle.get("review_reasons", []),
    }


def extract_known_facts(bundle: dict) -> dict:
    """Extract known-good facts from the bundle for the research prompt."""
    price_block = bundle.get("price", {})
    content = bundle.get("content", {})
    return {
        "brand": bundle.get("brand"),
        "name": bundle.get("name"),
        "assembled_title": bundle.get("assembled_title"),
        "expected_category": bundle.get("expected_category"),
        "our_price_raw": bundle.get("our_price_raw"),
        "has_content_seed": bool(content.get("description")),
        "price_currency": price_block.get("currency"),
        "price_native_value": price_block.get("price_per_unit"),
        "price_rub": price_block.get("rub_price"),
        "existing_source_url": price_block.get("source_url"),
        "pn_variants": bundle.get("pn_variants", []),
    }


def write_research_brief_md(pn: str, packet: dict, md_path: Path) -> None:
    """Write human-readable Markdown brief for a research packet."""
    reason = packet["research_reason"]
    questions = packet["questions_to_resolve"]
    facts = packet.get("known_facts", {})

    lines = [
        f"# Research Brief — {packet['entity_id']}",
        "",
        f"**Priority:** {packet['priority']} | **Reason:** {reason}",
        f"**Goal:** {packet['goal']}",
        "",
        "## Known Facts",
        f"- Brand: {facts.get('brand', '?')}",
        f"- Name: {facts.get('name', '?')}",
        f"- Expected Category: {facts.get('expected_category', '?')}",
        f"- Our Price (xlsx): {facts.get('our_price_raw', '?')}",
        "",
        "## Questions to Resolve",
    ]
    for q in questions:
        lines.append(f"- {q}")

    lines.extend([
        "",
        "## Current State",
        f"```json",
        json.dumps(packet.get("current_state", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Constraints",
    ])
    for c in packet.get("constraints", []):
        lines.append(f"- {c}")

    md_path.write_text("\n".join(lines), encoding="utf-8")


def _append_jsonl(path: Path, entry: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def emit_research_packet(pn: str, bundle: dict) -> dict:
    """Generate JSON + MD research packet for a DRAFT/REVIEW_REQUIRED SKU.

    Returns the packet dict. Writes to research_queue/packets/ and
    appends an entry to research_queue/research_queue.jsonl.
    """
    PACKETS_DIR.mkdir(parents=True, exist_ok=True)

    reason   = determine_research_reason(bundle)
    priority = classify_priority(bundle, reason)
    questions = generate_questions(pn, bundle, reason)
    brand = bundle.get("brand", "Honeywell")

    pn_safe = re.sub(r'[\\/:*?"<>|]', "_", pn)

    packet = {
        "packet_version": PACKET_VERSION,
        "task_id": f"enrichment_research_{pn}",
        "domain": "enrichment",
        "entity_type": "pn",
        "entity_id": pn,
        "brand_hint": brand,
        "goal": f"Close unresolved enrichment gaps for PN {pn} ({brand})",
        "research_reason": reason,
        "priority": priority,
        "questions_to_resolve": questions,
        "current_state": extract_current_state(bundle),
        "known_facts": extract_known_facts(bundle),
        "existing_evidence_refs": [f"downloads/evidence/evidence_{pn_safe}.json"],
        "constraints": [
            "Use public web evidence only",
            "Do not use xlsx price as market price",
            "Do not invent specs if not found",
            "If uncertain, return ambiguity explicitly",
            "Prefer exact PN evidence over family-level evidence",
            "Cite specific URLs for any claim",
        ],
        "required_output": {
            "identity": True,
            "title_ru": True,
            "description_ru": True,
            "category": True,
            "price_assessment": True,
            "photo_assessment": True,
            "specs_assessment": True,
            "citations_required": True,
            "ambiguities_required": True,
        },
        "generated_at": _now_iso(),
    }

    # Write JSON packet
    packet_path = PACKETS_DIR / f"research_packet_{pn_safe}.json"
    packet_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")

    # Write MD brief
    md_path = PACKETS_DIR / f"research_packet_{pn_safe}.md"
    write_research_brief_md(pn, packet, md_path)

    # Append to queue
    queue_entry = {
        "pn": pn,
        "reason": reason,
        "priority": priority,
        "packet_path": str(packet_path),
        "generated_at": _now_iso(),
    }
    _append_jsonl(QUEUE_JSONL, queue_entry)

    return packet


def build_queue_from_evidence(
    evidence_dir: Path = EVIDENCE_DIR,
    force: bool = False,
) -> dict:
    """Scan all evidence bundles and emit packets for DRAFT/REVIEW_REQUIRED SKUs.

    Args:
        evidence_dir: Directory containing evidence_*.json files.
        force: If True, re-emit even if packet already exists.

    Returns:
        Statistics dict.
    """
    # Start fresh queue file
    if QUEUE_JSONL.exists() and not force:
        # Append mode — read existing entries to avoid duplicates
        existing_pns: set[str] = set()
        with open(QUEUE_JSONL, encoding="utf-8") as f:
            for line in f:
                try:
                    existing_pns.add(json.loads(line.strip())["pn"])
                except Exception:
                    pass
    else:
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        QUEUE_JSONL.write_text("", encoding="utf-8")  # clear
        existing_pns = set()

    stats: dict[str, int] = {
        "total_bundles": 0,
        "research_needed": 0,
        "skipped_resolved": 0,
        "already_queued": 0,
        "emitted": 0,
    }
    priority_counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    reason_counts: dict[str, int] = {}

    for ev_path in sorted(evidence_dir.glob("evidence_*.json")):
        stats["total_bundles"] += 1
        try:
            bundle = json.loads(ev_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        pn = bundle.get("pn") or ev_path.stem.replace("evidence_", "")
        card_status = bundle.get("card_status", "")

        if card_status not in _RESEARCH_STATUSES:
            stats["skipped_resolved"] += 1
            continue

        stats["research_needed"] += 1

        if pn in existing_pns:
            stats["already_queued"] += 1
            continue

        packet = emit_research_packet(pn, bundle)
        reason = packet["research_reason"]
        priority = packet["priority"]
        stats["emitted"] += 1
        priority_counts[priority] = priority_counts.get(priority, 0) + 1
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    stats["priority_breakdown"] = priority_counts
    stats["reason_breakdown"] = reason_counts
    return stats


def print_queue_stats(stats: dict) -> None:
    print("\n=== RESEARCH QUEUE STATS ===")
    print(f"  Total bundles scanned:   {stats['total_bundles']}")
    print(f"  Research needed:         {stats['research_needed']}")
    print(f"  Skipped (resolved):      {stats['skipped_resolved']}")
    print(f"  Already in queue:        {stats['already_queued']}")
    print(f"  Newly emitted:           {stats['emitted']}")
    print(f"\nBy priority:")
    for p, n in stats.get("priority_breakdown", {}).items():
        print(f"  {p:8s}: {n}")
    print(f"\nBy reason:")
    for r, n in sorted(stats.get("reason_breakdown", {}).items(), key=lambda x: -x[1]):
        print(f"  {r:30s}: {n}")
    print(f"\nQueue file: {QUEUE_JSONL}")
    print(f"Packets:    {PACKETS_DIR}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build research queue from evidence bundles")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Clear existing queue and re-emit all packets",
    )
    parser.add_argument(
        "--evidence-dir",
        default=str(EVIDENCE_DIR),
        help="Evidence directory (default: downloads/evidence)",
    )
    args = parser.parse_args()
    stats = build_queue_from_evidence(
        evidence_dir=Path(args.evidence_dir),
        force=args.force,
    )
    print_queue_stats(stats)
