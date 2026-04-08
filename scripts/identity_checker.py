"""identity_checker.py — Identity verification and retrospective boost for enrichment pipeline.

Root cause (from investigation 2026-04-08):
  _infer_identity_level() reads photo_result["pn_match_location"] which is always "".
  The actual structured match is stored in photo_result["structured_pn_match_location"]
  and bundle["structured_identity"]["structured_pn_match_location"].
  These two keys diverged — the data is there, just not consumed by the identity check.

Approach:
  1. retrospective_identity_boost() — reads existing checkpoint data, upgrades identity_level
     in-place. Free, no API. Fixes 204 SKUs that already have structured PN match.
  2. select_identity_sprint_cohort() — stratified sample of remaining weak SKUs for Gemini check.
  3. check_identity_via_gemini() — Gemini grounding for SKUs without structured match.
  4. run_identity_sprint() — bounded pilot runner (50 SKU, ~$0.15).
  5. evaluate_acceptance() — strict acceptance rules for Gemini results.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

_ROOT = Path(_scripts_dir).parent
EVIDENCE_DIR = _ROOT / "downloads" / "evidence"
CHECKPOINT_PATH = _ROOT / "downloads" / "checkpoint.json"
TRAINING_DIR = _ROOT / "training_data"
SPRINT_DIR = _ROOT / "research_results" / "identity_sprint"
COHORT_PATH = _ROOT / "research_queue" / "identity_sprint_cohort.json"

# Identity levels (ordered weakest → strongest)
_IDENTITY_LEVELS = ("weak", "medium", "strong", "confirmed")

# Structured contexts that _infer_identity_level considers "strong"
_STRUCTURED_CONTEXTS = {"jsonld", "title", "h1", "product_context"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ══════════════════════════════════════════════════════════════════════════════
# Retrospective identity boost (free — uses existing checkpoint data)
# ══════════════════════════════════════════════════════════════════════════════

def retrospective_identity_boost(
    checkpoint_path: str | Path = CHECKPOINT_PATH,
    training: bool = True,
) -> dict:
    """Upgrade identity_level for SKUs whose structured match was already found.

    Root cause fix: pipeline stores PN match in 'structured_pn_match_location'
    but _infer_identity_level() reads 'pn_match_location' (always empty).
    The data is there — we just read it from 'structured_identity' and
    upgrade the bundle's policy_decision_v2.identity_level accordingly.

    Does NOT touch card_status — that requires pipeline re-run.
    Does NOT auto-accept — only upgrades identity_level for human review.

    Returns: stats dict
    """
    cp_path = Path(checkpoint_path)
    if not cp_path.exists():
        return {"error": f"checkpoint not found: {cp_path}"}

    cp = json.loads(cp_path.read_text(encoding="utf-8"))

    stats = {
        "total_checked": 0,
        "already_strong": 0,
        "boosted_to_strong": 0,    # structured match in title/h1/jsonld/product_context
        "boosted_to_medium": 0,    # body match only
        "remained_weak": 0,
        "errors": 0,
    }

    for pn, bundle in cp.items():
        if not isinstance(bundle, dict):
            continue
        stats["total_checked"] += 1

        pd = bundle.get("policy_decision_v2", {})
        current_identity = pd.get("identity_level", "weak")

        if current_identity in ("strong", "confirmed"):
            stats["already_strong"] += 1
            continue

        # Read structured match from two possible locations
        si = bundle.get("structured_identity", {})
        trace = bundle.get("trace", {})

        # Primary: structured_identity block (set by extract_structured_pn_flags)
        si_loc = si.get("structured_pn_match_location", "")
        si_exact = si.get("exact_structured_pn_match", False)

        # Fallback: trace.structured_pn_match_location
        if not si_loc:
            si_loc = trace.get("structured_pn_match_location", "")
            si_exact = bool(si_loc)

        # Determine new identity level
        new_level = None
        signals = []

        if si_exact and si_loc in _STRUCTURED_CONTEXTS:
            new_level = "strong"
            signals.append(f"structured_pn_match:{si_loc}")
        elif si_loc == "body" or trace.get("pn_match_location") == "body":
            new_level = "medium"
            signals.append("body_pn_match")

        if new_level is None:
            stats["remained_weak"] += 1
            continue

        # Apply upgrade
        try:
            if "policy_decision_v2" not in bundle:
                bundle["policy_decision_v2"] = {}
            bundle["policy_decision_v2"]["identity_level"] = new_level
            bundle["policy_decision_v2"]["identity_boost_signals"] = signals
            bundle["policy_decision_v2"]["identity_boost_source"] = "retrospective_structured_match"
            bundle["policy_decision_v2"]["identity_boost_ts"] = _now_iso()

            cp[pn] = bundle

            if new_level == "strong":
                stats["boosted_to_strong"] += 1
            else:
                stats["boosted_to_medium"] += 1

            if training:
                _append_jsonl(
                    TRAINING_DIR / "identity_boost_examples.jsonl",
                    {
                        "input": {"pn": pn, "structured_identity": si, "signals": signals},
                        "output": {"old_level": current_identity, "new_level": new_level},
                        "timestamp": _now_iso(),
                    },
                )
        except Exception as e:
            log.warning(f"Boost failed for {pn}: {e}")
            stats["errors"] += 1

    # Persist updated checkpoint
    cp_path.write_text(json.dumps(cp, indent=2, ensure_ascii=False), encoding="utf-8")

    total_boosted = stats["boosted_to_strong"] + stats["boosted_to_medium"]
    print(
        f"Retrospective boost: {stats['boosted_to_strong']} to strong, "
        f"{stats['boosted_to_medium']} to medium, "
        f"{stats['remained_weak']} remained weak "
        f"(of {stats['total_checked']} checked)"
    )
    return stats


# ══════════════════════════════════════════════════════════════════════════════
# Identity Artifact (structured result from Gemini grounding)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class IdentityArtifact:
    pn: str
    brand: str

    # Core result
    identity_status: str = "not_found"   # "confirmed" | "probable" | "conflict" | "not_found"

    # Evidence
    source_url: Optional[str] = None
    source_type: Optional[str] = None      # "manufacturer" | "distributor" | "datasheet" | "other"
    source_domain: Optional[str] = None
    source_strength: Optional[str] = None  # "tier1" | "tier2" | "weak"
    pn_match_type: Optional[str] = None    # "exact" | "family" | "inferred" | "not_found"

    # Extracted data
    product_name: Optional[str] = None
    product_type: Optional[str] = None
    datasheet_url: Optional[str] = None

    # Quality
    confidence: str = "low"               # "high" | "medium" | "low"
    raw_response: Optional[str] = None

    # Decision
    accept_for_pipeline: bool = False
    reject_reason: Optional[str] = None


def evaluate_acceptance(
    artifact: IdentityArtifact,
    trusted_domains: Optional[list[str]] = None,
) -> IdentityArtifact:
    """Apply strict acceptance rules to a Gemini identity result.

    AUTO ACCEPT only if:
      - exact PN match
      - trusted domain (tier1/tier2) OR high confidence
      - source type is manufacturer/distributor/datasheet

    probable → review queue, NOT auto-accept
    family/inferred → NOT confirmation of identity
    """
    # Determine source strength from trusted_domains list
    if artifact.source_domain and trusted_domains:
        tier1 = trusted_domains[:3]
        tier2 = trusted_domains[3:]
        if artifact.source_domain in tier1:
            artifact.source_strength = "tier1"
        elif artifact.source_domain in tier2:
            artifact.source_strength = "tier2"
        else:
            artifact.source_strength = "weak"

    if artifact.pn_match_type == "exact":
        trusted = artifact.source_strength in ("tier1", "tier2")
        strong_source = artifact.source_type in ("manufacturer", "distributor", "datasheet")
        high_conf = artifact.confidence == "high"

        if (trusted and strong_source and artifact.confidence in ("high", "medium")) or \
           (high_conf and strong_source):
            artifact.accept_for_pipeline = True
            artifact.identity_status = "confirmed"
        else:
            artifact.identity_status = "probable"
            artifact.reject_reason = "exact match but weak source or low confidence"

    elif artifact.pn_match_type == "family":
        artifact.identity_status = "probable"
        artifact.reject_reason = "family match only, not exact PN"

    else:
        artifact.identity_status = "not_found"
        artifact.reject_reason = "no match or inferred only"

    return artifact


# ══════════════════════════════════════════════════════════════════════════════
# Gemini identity checker
# ══════════════════════════════════════════════════════════════════════════════

def _build_identity_prompt(pn: str, brand: str) -> str:
    return f"""Verify this industrial product exists and find its official page.

Brand: {brand}
Part Number: {pn}

Search manufacturer website and authorized distributors.

Answer these questions:
1. Does this EXACT part number exist as a real product? (not a family, not similar)
2. What is the full official product name?
3. What type of product is it?
4. URL of the page where you found this exact PN
5. Is there a datasheet PDF available? If yes, URL.
6. What domain is the source from?

CRITICAL: I need EXACT part number match, not family or similar products.
If you find "{pn}" mentioned as part of a product family but not as exact standalone PN,
report that as "family" match, not "exact".

Return JSON only (no markdown):
{{"pn_found": true or false,
  "match_type": "exact or family or inferred or not_found",
  "product_name": "...",
  "product_type": "...",
  "source_url": "...",
  "source_domain": "...",
  "source_type": "manufacturer or distributor or datasheet or other",
  "datasheet_url": null,
  "confidence": "high or medium or low",
  "notes": "..."}}"""


def check_identity_via_gemini(
    pn: str,
    brand: str,
    trusted_domains: Optional[list[str]] = None,
) -> IdentityArtifact:
    """One Gemini grounding call for identity verification. ~$0.003/SKU."""
    from research_providers import GeminiResearchProvider, _parse_json_from_text

    provider = GeminiResearchProvider()
    prompt = _build_identity_prompt(pn, brand)

    try:
        response_text, model, cost = provider.call(prompt)
        parsed = _parse_json_from_text(response_text) or {}
    except Exception as e:
        return IdentityArtifact(
            pn=pn, brand=brand,
            identity_status="error",
            reject_reason=str(e),
        )

    artifact = IdentityArtifact(
        pn=pn,
        brand=brand,
        source_url=parsed.get("source_url"),
        source_type=parsed.get("source_type"),
        source_domain=parsed.get("source_domain"),
        pn_match_type=parsed.get("match_type", "not_found"),
        product_name=parsed.get("product_name"),
        product_type=parsed.get("product_type"),
        datasheet_url=parsed.get("datasheet_url"),
        confidence=parsed.get("confidence", "low"),
        raw_response=response_text[:2000] if response_text else None,
    )

    return evaluate_acceptance(artifact, trusted_domains)


# ══════════════════════════════════════════════════════════════════════════════
# Sprint cohort selection
# ══════════════════════════════════════════════════════════════════════════════

def select_identity_sprint_cohort(
    checkpoint_path: str | Path = CHECKPOINT_PATH,
    cohort_size: int = 50,
    output_path: str | Path = COHORT_PATH,
) -> list[str]:
    """Select stratified cohort of identity_weak SKUs for Gemini sprint.

    Stratification groups (higher value groups sampled first):
      has_photo_and_price  — photo KEEP + public_price (highest Gemini chance)
      has_photo_no_price   — photo KEEP but no price
      has_price_no_photo   — price found, photo rejected
      alphanumeric_pn      — non-numeric PN (more findable online)
      numeric_pn           — PEHA-style numeric PN
      nothing              — no photo, no price

    Only includes SKUs that are STILL weak after retrospective boost.
    """
    cp = json.loads(Path(checkpoint_path).read_text(encoding="utf-8"))

    groups: dict[str, list[str]] = {
        "has_photo_and_price": [],
        "has_photo_no_price": [],
        "has_price_no_photo": [],
        "alphanumeric_pn": [],
        "numeric_pn": [],
        "nothing": [],
    }

    total_weak = 0
    for pn, bundle in cp.items():
        if not isinstance(bundle, dict):
            continue
        pd = bundle.get("policy_decision_v2", {})
        if pd.get("identity_level") not in ("weak", None, ""):
            continue  # already boosted or confirmed

        total_weak += 1
        photo = bundle.get("photo", {})
        price = bundle.get("price", {})
        has_photo = photo.get("verdict") == "KEEP"
        has_price = price.get("price_status") == "public_price"
        is_numeric = pn.replace(".", "").replace("-", "").isdigit()

        if has_photo and has_price:
            groups["has_photo_and_price"].append(pn)
        elif has_photo:
            groups["has_photo_no_price"].append(pn)
        elif has_price:
            groups["has_price_no_photo"].append(pn)
        elif not is_numeric:
            groups["alphanumeric_pn"].append(pn)
        elif is_numeric:
            groups["numeric_pn"].append(pn)
        else:
            groups["nothing"].append(pn)

    # Proportional selection: min 3 from each non-empty group
    per_group = max(3, cohort_size // max(len(groups), 1))
    cohort: list[str] = []
    selected_set: set[str] = set()

    for group_name, pns in groups.items():
        take = min(len(pns), per_group)
        for pn in pns[:take]:
            if pn not in selected_set:
                cohort.append(pn)
                selected_set.add(pn)

    # Fill remainder
    for group_name, pns in groups.items():
        for pn in pns:
            if len(cohort) >= cohort_size:
                break
            if pn not in selected_set:
                cohort.append(pn)
                selected_set.add(pn)

    cohort = cohort[:cohort_size]

    # Save cohort manifest
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({
            "cohort_size": len(cohort),
            "total_weak_after_boost": total_weak,
            "groups": {k: len(v) for k, v in groups.items()},
            "selected_pns": cohort,
            "generated_at": _now_iso(),
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Identity sprint cohort: {len(cohort)}/{total_weak} remaining-weak SKU")
    for g, pns in groups.items():
        in_cohort = sum(1 for p in pns if p in selected_set)
        print(f"  {g}: {in_cohort}/{len(pns)}")

    return cohort


# ══════════════════════════════════════════════════════════════════════════════
# Sprint runner
# ══════════════════════════════════════════════════════════════════════════════

def run_identity_sprint(
    cohort_path: str | Path = COHORT_PATH,
    checkpoint_path: str | Path = CHECKPOINT_PATH,
    max_budget_usd: float = 0.50,
    training: bool = True,
) -> dict:
    """Run Gemini identity check for sprint cohort. ~$0.003/SKU × 50 = $0.15."""
    cohort_data = json.loads(Path(cohort_path).read_text(encoding="utf-8"))
    pns = cohort_data["selected_pns"]
    cp = json.loads(Path(checkpoint_path).read_text(encoding="utf-8"))

    SPRINT_DIR.mkdir(parents=True, exist_ok=True)
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)

    stats: dict = {
        "total": len(pns),
        "confirmed": 0,
        "probable": 0,
        "not_found": 0,
        "errors": 0,
        "budget_spent_usd": 0.0,
        "acceptance_rate": 0.0,
        "probable_rate": 0.0,
        "artifacts": [],
    }

    try:
        from brand_knowledge import get_trusted_domains
    except ImportError:
        def get_trusted_domains(brand, pn=None):
            return []

    _GEMINI_COST = 0.003

    for pn in pns:
        if stats["budget_spent_usd"] + _GEMINI_COST > max_budget_usd:
            stats["budget_stop"] = True
            break

        bundle = cp.get(pn, {})
        brand = bundle.get("brand", "Honeywell") if isinstance(bundle, dict) else "Honeywell"

        try:
            trusted = get_trusted_domains(brand, pn)
            artifact = check_identity_via_gemini(pn, brand, trusted)
            stats["budget_spent_usd"] += _GEMINI_COST

            # Count outcome
            status = artifact.identity_status
            if status == "confirmed":
                stats["confirmed"] += 1
            elif status == "probable":
                stats["probable"] += 1
            else:
                stats["not_found"] += 1

            stats["artifacts"].append({
                "pn": pn,
                "status": status,
                "accept": artifact.accept_for_pipeline,
                "match_type": artifact.pn_match_type,
                "source_strength": artifact.source_strength,
                "confidence": artifact.confidence,
                "source_url": artifact.source_url,
                "reject_reason": artifact.reject_reason,
            })

            # Save per-SKU artifact
            safe_pn = pn.replace("/", "_").replace("\\", "_")
            artifact_path = SPRINT_DIR / f"{safe_pn}_identity.json"
            artifact_path.write_text(
                json.dumps(asdict(artifact), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            # Update checkpoint if confirmed
            if artifact.accept_for_pipeline and isinstance(bundle, dict):
                if "policy_decision_v2" not in bundle:
                    bundle["policy_decision_v2"] = {}
                bundle["policy_decision_v2"]["identity_level"] = "confirmed"
                bundle["policy_decision_v2"]["identity_gemini_source"] = artifact.source_url
                bundle["policy_decision_v2"]["identity_gemini_product_name"] = artifact.product_name
                bundle["policy_decision_v2"]["identity_gemini_ts"] = _now_iso()
                cp[pn] = bundle

            # Training data
            if training:
                _append_jsonl(
                    TRAINING_DIR / "identity_check_examples.jsonl",
                    {
                        "input": {"pn": pn, "brand": brand},
                        "output": {
                            "identity_status": status,
                            "pn_match_type": artifact.pn_match_type,
                            "source_strength": artifact.source_strength,
                            "accept": artifact.accept_for_pipeline,
                        },
                        "raw_response": artifact.raw_response,
                        "timestamp": _now_iso(),
                    },
                )

        except Exception as e:
            stats["errors"] += 1
            log.warning(f"Identity check failed for {pn}: {e}")

    # Save updated checkpoint
    Path(checkpoint_path).write_text(
        json.dumps(cp, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Compute rates
    checked = stats["confirmed"] + stats["probable"] + stats["not_found"]
    if checked > 0:
        stats["acceptance_rate"] = round(stats["confirmed"] / checked, 3)
        stats["probable_rate"] = round(stats["probable"] / checked, 3)

    # Save report
    report_path = _ROOT / "research_results" / "identity_sprint_report.json"
    report = {k: v for k, v in stats.items() if k != "artifacts"}
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Print summary
    print("=" * 60)
    print("IDENTITY SPRINT REPORT")
    print("=" * 60)
    print(f"Total checked: {checked}/{len(pns)}")
    print(f"Confirmed (auto-accept): {stats['confirmed']} ({stats['acceptance_rate']:.0%})")
    print(f"Probable (review queue): {stats['probable']} ({stats['probable_rate']:.0%})")
    print(f"Not found: {stats['not_found']}")
    print(f"Errors: {stats['errors']}")
    print(f"Budget: ${stats['budget_spent_usd']:.3f}")
    print("=" * 60)

    rate = stats["acceptance_rate"]
    if rate >= 0.5:
        print("RECOMMENDATION: High acceptance. Scale to all remaining weak SKU.")
    elif rate >= 0.3:
        print("RECOMMENDATION: Moderate acceptance. Scale cautiously, review probable.")
    else:
        print("RECOMMENDATION: Low acceptance. Investigate identity criteria before scaling.")

    return stats


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Identity checker for enrichment pipeline")
    sub = parser.add_subparsers(dest="cmd")

    boost_p = sub.add_parser("boost", help="Retrospective boost using existing structured_identity data")
    boost_p.add_argument("--checkpoint", default=str(CHECKPOINT_PATH))
    boost_p.add_argument("--no-training", action="store_true")

    cohort_p = sub.add_parser("cohort", help="Select sprint cohort")
    cohort_p.add_argument("--size", type=int, default=50)

    sprint_p = sub.add_parser("sprint", help="Run Gemini identity sprint")
    sprint_p.add_argument("--budget", type=float, default=0.50)
    sprint_p.add_argument("--no-training", action="store_true")

    args = parser.parse_args()

    if args.cmd == "boost":
        retrospective_identity_boost(
            checkpoint_path=args.checkpoint,
            training=not args.no_training,
        )
    elif args.cmd == "cohort":
        select_identity_sprint_cohort(cohort_size=args.size)
    elif args.cmd == "sprint":
        select_identity_sprint_cohort()
        run_identity_sprint(max_budget_usd=args.budget, training=not args.no_training)
    else:
        parser.print_help()
