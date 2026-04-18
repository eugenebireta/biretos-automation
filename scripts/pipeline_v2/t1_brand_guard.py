"""T1 Sync Guard — Step 1 hotfix for brand correction incident (2026-04-16).

Root cause: auto-fix LLM proposed wrong brands for SKUs whose evidence
already contained authoritative T1 data (structured_identity.confirmed_manufacturer).

Empirical: 55/55 incident SKUs had T1 populated; T1 alone resolves 41/55 (75%)
correctly. Remaining 14 are parent/sub-brand ambiguities requiring URL Oracle
(deferred to v1.1).

This module provides two deterministic functions:
- should_skip_brand_autofix(evidence): block LLM brand proposal if T1 is trusted
- sync_brand_to_t1(evidence): deterministically align top-level brand to T1

No LLM calls. No external dependencies. ~100 lines.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

# Tier 1 trust markers: require at least one strong positive signal
# (confirmed_manufacturer + exact_title_pn_match is the strongest combination
# seen in the 41/55 resolvable cases).
TRUST_SIGNALS = [
    "exact_title_pn_match",
    "exact_h1_pn_match",
    "exact_structured_pn_match",
]


def get_t1_brand(evidence: dict) -> Optional[str]:
    """Return T1 confirmed_manufacturer if populated, else None."""
    si = evidence.get("structured_identity") or {}
    mfr = (si.get("confirmed_manufacturer") or "").strip()
    return mfr if mfr else None


def get_t1_trust(evidence: dict) -> str:
    """Return T1 trust classification.

    - 'strong': confirmed_manufacturer + at least one exact_*_match
    - 'weak':   confirmed_manufacturer only, no title/h1/structured match
    - 'none':   no confirmed_manufacturer
    """
    si = evidence.get("structured_identity") or {}
    if not si.get("confirmed_manufacturer"):
        return "none"
    if any(si.get(k) for k in TRUST_SIGNALS):
        return "strong"
    return "weak"


def should_skip_brand_autofix(evidence: dict) -> tuple[bool, str]:
    """Guard: if T1 (confirmed_manufacturer) is populated, auto-fix must NOT
    propose a new brand for this SKU. Period.

    Rationale: all 19 incident SKUs where auto-fix wrote wrong brand had T1
    populated. Empirically, LLM proposals did not improve over T1 — they only
    regressed. If T1 itself is wrong (rare), correction needs URL Oracle or
    human review, not another LLM pass.

    Returns (skip: bool, reason: str).
    """
    t1_brand = get_t1_brand(evidence)
    if t1_brand:
        trust = get_t1_trust(evidence)
        return True, f"T1 populated (confirmed_manufacturer={t1_brand!r}, trust={trust})"
    return False, "T1 empty — autofix allowed"


def needs_sync(evidence: dict) -> Optional[tuple[str, str]]:
    """Check if top-level brand diverges from T1 confirmed_manufacturer.

    Returns (current_brand, t1_brand) tuple if divergent and T1 trust is strong.
    Returns None if no sync needed.

    Ambiguity handling: parent/sub-brand pairs are considered 'compatible' and
    NOT synced here (e.g. brand='Honeywell', T1='Esser' — both are acceptable
    because Esser is a Honeywell sub-brand). Sync only when brands are clearly
    different manufacturers (e.g. brand='Honeywell', T1='Dell').
    """
    if get_t1_trust(evidence) != "strong":
        return None

    current = (evidence.get("brand") or "").strip()
    t1 = get_t1_brand(evidence)
    if not t1:
        return None

    current_norm = current.lower().split("/")[0].split("(")[0].strip()
    t1_norm = t1.lower().split("/")[0].split("(")[0].strip()

    if not current_norm:
        return (current, t1)

    # Tokens overlap → compatible (e.g., 'Honeywell' vs 'Honeywell/ESSER')
    current_tokens = set(current_norm.replace("-", " ").split())
    t1_tokens = set(t1_norm.replace("-", " ").split())
    if current_tokens & t1_tokens:
        return None

    # Known parent/sub-brand pairs — compatible, do not force sync
    compat_pairs = [
        ({"honeywell"}, {"esser"}),
        ({"honeywell"}, {"sperian"}),
        ({"honeywell"}, {"notifier"}),
        ({"honeywell"}, {"peha"}),
        ({"honeywell"}, {"saia", "saia-burgess"}),
        ({"honeywell"}, {"howard", "leight"}),
        ({"honeywell"}, {"distech"}),
    ]
    for a, b in compat_pairs:
        if (current_tokens & a and t1_tokens & b) or (current_tokens & b and t1_tokens & a):
            return None

    return (current, t1)


def sync_brand_to_t1(evidence: dict, reason: str = "t1_sync_guard") -> bool:
    """Apply T1 → brand sync if needed. Returns True if evidence was mutated."""
    div = needs_sync(evidence)
    if not div:
        return False
    current, t1 = div
    evidence["brand"] = t1
    # Track original value for audit
    evidence.setdefault("_corrections", {})
    evidence["_corrections"]["t1_sync"] = {
        "before": current,
        "after": t1,
        "reason": reason,
    }
    return True


# ---------------------------------------------------------------------------
# Batch CLI
# ---------------------------------------------------------------------------

def main():
    """Scan all evidence files; report sync candidates; apply with --apply."""
    import sys
    import io
    import argparse

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply syncs (default: dry-run)")
    parser.add_argument("--ev-dir", default="downloads/evidence")
    args = parser.parse_args()

    ev_dir = Path(args.ev_dir)
    files = sorted(ev_dir.glob("evidence_*.json"))

    skip_count = 0
    sync_candidates = []
    applied = 0

    for f in files:
        try:
            ev = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue

        skip, _ = should_skip_brand_autofix(ev)
        if skip:
            skip_count += 1

        div = needs_sync(ev)
        if div:
            sync_candidates.append((f.stem.replace("evidence_", ""), div[0], div[1]))
            if args.apply:
                sync_brand_to_t1(ev)
                f.write_text(json.dumps(ev, indent=2, ensure_ascii=False), encoding="utf-8")
                applied += 1

    print(f"Scanned: {len(files)}")
    print(f"Guard would skip autofix: {skip_count}")
    print(f"Sync candidates (brand != T1, incompatible): {len(sync_candidates)}")
    for pn, cur, t1 in sync_candidates[:30]:
        print(f"  {pn}: {cur!r} -> {t1!r}")
    if len(sync_candidates) > 30:
        print(f"  ... and {len(sync_candidates) - 30} more")
    if args.apply:
        print(f"\nApplied: {applied} syncs")
    else:
        print("\nDry run — use --apply to mutate evidence")


if __name__ == "__main__":
    main()
