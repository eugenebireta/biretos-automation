"""evidence_normalize.py — Normalization layer: unify 3-pipeline evidence data.

Writes a `normalized` top-level dict to each evidence file with canonical
best_price / best_description / best_photo_url, selected from whichever
pipeline has the richest data.

Pipeline sources:
  Pipeline 1 (Phase A / SerpAPI): price.price_per_unit, price.currency,
                                   photo.verdict, photo.source
  Pipeline 2 (DR):                 price_contract.dr_value, price_contract.dr_currency,
                                   dr_image_url, deep_research.description_ru
  Pipeline 3 (Excel import):       content.description, our_price_raw

SAFE RULES:
  - Never deletes or overwrites dr_price, price, price_contract, content, photo,
    deep_research, or any existing field
  - normalized{} is always fully replaced (idempotent — never merges stale values)
  - Atomic write per file (write to .tmp then os.replace)
  - Structured error logging on every failure

Usage:
    python scripts/evidence_normalize.py --dry-run
    python scripts/evidence_normalize.py
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

log = logging.getLogger(__name__)

EVIDENCE_DIR = Path("downloads/evidence")

_MIN_DESC_LEN = 50


# ---------------------------------------------------------------------------
# Price selection
# ---------------------------------------------------------------------------

def _pick_price(evidence: dict) -> tuple[float | None, str | None, str | None]:
    """Return (value, currency, source) for the best available price.

    Priority:
      1. price_contract.dr_value (DR pipeline, has unit_basis judgment attached)
      2. price.price_per_unit (Phase A SerpAPI pipeline)
      3. price_contract.our_price_parsed (RUB estimate from internal Excel, ~2022 rate)
    """
    pc = evidence.get("price_contract") or {}
    dr_val = pc.get("dr_value")
    dr_cur = pc.get("dr_currency")

    if dr_val is not None:
        try:
            return float(dr_val), dr_cur or None, "price_contract"
        except (TypeError, ValueError):
            log.warning(
                "normalize: price_contract.dr_value not numeric pn=%s val=%r",
                evidence.get("pn"), dr_val,
                extra={"error_class": "PERMANENT", "severity": "WARNING", "retriable": False},
            )

    price_obj = evidence.get("price") or {}
    p1_val = price_obj.get("price_per_unit")
    p1_cur = price_obj.get("currency")

    if p1_val is not None:
        try:
            return float(p1_val), p1_cur or None, "pipeline1"
        except (TypeError, ValueError):
            log.warning(
                "normalize: price.price_per_unit not numeric pn=%s val=%r",
                evidence.get("pn"), p1_val,
                extra={"error_class": "PERMANENT", "severity": "WARNING", "retriable": False},
            )

    # Fallback: internal RUB market estimate from Excel (currency inferred as RUB)
    our_val = pc.get("our_price_parsed")
    if our_val is not None:
        try:
            return float(our_val), "RUB", "our_estimate"
        except (TypeError, ValueError):
            log.warning(
                "normalize: price_contract.our_price_parsed not numeric pn=%s val=%r",
                evidence.get("pn"), our_val,
                extra={"error_class": "PERMANENT", "severity": "WARNING", "retriable": False},
            )

    return None, None, None


# ---------------------------------------------------------------------------
# Description selection
# ---------------------------------------------------------------------------

def _pick_description(evidence: dict) -> tuple[str | None, str | None]:
    """Return (text, source) for the best available description.

    Picks whichever of DR and content is longer (both >= MIN_LEN are
    evaluated; if only one qualifies, use that one; if neither, use
    the longer of the two regardless of length).
    """
    dr = evidence.get("deep_research") or {}
    dr_desc = (dr.get("description_ru") or "").strip()

    content = evidence.get("content") or {}
    ct_desc = (content.get("description") or "").strip()

    dr_len = len(dr_desc)
    ct_len = len(ct_desc)

    dr_ok = dr_len >= _MIN_DESC_LEN
    ct_ok = ct_len >= _MIN_DESC_LEN

    if dr_ok and ct_ok:
        # Both qualify — pick the longer (more complete)
        return (dr_desc, "dr") if dr_len >= ct_len else (ct_desc, "content")
    if dr_ok:
        return dr_desc, "dr"
    if ct_ok:
        return ct_desc, "content"
    # Neither qualifies — still pick best available (non-empty preferred)
    if dr_desc and ct_desc:
        return (dr_desc, "dr") if dr_len >= ct_len else (ct_desc, "content")
    if dr_desc:
        return dr_desc, "dr"
    if ct_desc:
        return ct_desc, "content"
    return None, None


# ---------------------------------------------------------------------------
# Photo selection
# ---------------------------------------------------------------------------

def _parse_photo_source_url(source: str, dr_image_url: str | None) -> str | None:
    """Extract photo URL from photo.source string.

    photo.source format:
      - "cached"                    → the cached image lives at dr_image_url
      - "<engine>:<url>"            → e.g. "google:https://...", "jsonld:https://..."
      - "img:<url>"                 → e.g. "img:https://..."
      - bare "https://..."          → edge case: use as-is
    """
    if source == "cached":
        return dr_image_url or None
    # Bare HTTP URL (no engine prefix)
    if source.startswith("http"):
        return source
    if ":" in source:
        # Split on first colon only: "google:https://..." → ["google", "https://..."]
        _, url = source.split(":", 1)
        url = url.strip()
        return url if url.startswith("http") else None
    return None


def _pick_photo(evidence: dict) -> tuple[str | None, str | None]:
    """Return (url, source) for the best available photo.

    Priority:
      1. photo.verdict in (KEEP, ACCEPT) → use photo.source (or dr_image_url if cached)
      2. dr_image_url (fallback, unreviewed)
    """
    photo_obj = evidence.get("photo") or {}
    verdict = photo_obj.get("verdict")
    source_raw = photo_obj.get("source") or ""
    dr_image_url = evidence.get("dr_image_url")

    if verdict in ("KEEP", "ACCEPT") and source_raw:
        url = _parse_photo_source_url(source_raw, dr_image_url)
        if url:
            return url, "photo_verdict"

    if dr_image_url:
        return dr_image_url, "dr_image"

    return None, None


# ---------------------------------------------------------------------------
# Build normalized block
# ---------------------------------------------------------------------------

def build_normalized(evidence: dict) -> dict:
    """Build the normalized dict for a single evidence record."""
    price_val, price_cur, price_src = _pick_price(evidence)
    desc_val, desc_src = _pick_description(evidence)
    photo_url, photo_src = _pick_photo(evidence)

    return {
        "schema_version": "normalized_v1",
        "best_price": price_val,
        "best_price_currency": price_cur,
        "best_price_source": price_src,
        "best_description": desc_val,
        "best_description_source": desc_src,
        "best_photo_url": photo_url,
        "best_photo_source": photo_src,
    }


# ---------------------------------------------------------------------------
# Atomic write helper
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically via a temp file + os.replace."""
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, prefix=path.name + ".tmp_", suffix=".json"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            # fdopen takes ownership — fd is closed when f is closed
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        # fdopen may not have taken ownership if it raised (e.g. bad fd)
        # Attempt fd close first, then unlink
        try:
            os.close(tmp_fd)
        except OSError:
            pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run(dry_run: bool = False) -> None:
    trace_id = str(uuid.uuid4())
    run_id = f"normalize_{int(time.time())}"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    sys.stdout.reconfigure(encoding="utf-8")

    log.info("normalize: START run_id=%s trace_id=%s dry_run=%s", run_id, trace_id, dry_run)

    evidence_files = sorted(EVIDENCE_DIR.glob("evidence_*.json"))
    print(f"{'[DRY RUN] ' if dry_run else ''}Normalizing {len(evidence_files)} evidence files...")
    print()

    stats = {
        "processed": 0,
        "skipped_no_file": 0,
        "errors": 0,
        "price_price_contract": 0,
        "price_pipeline1": 0,
        "price_our_estimate": 0,
        "price_none": 0,
        "desc_dr": 0,
        "desc_content": 0,
        "desc_none": 0,
        "photo_verdict": 0,
        "photo_dr_image": 0,
        "photo_none": 0,
    }

    for fpath in evidence_files:
        try:
            evidence = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.error(
                "normalize: cannot read file trace_id=%s path=%s error=%s",
                trace_id, fpath, exc,
                extra={"error_class": "PERMANENT", "severity": "ERROR", "retriable": False},
            )
            stats["errors"] += 1
            continue

        try:
            normalized = build_normalized(evidence)
        except Exception as exc:
            pn = evidence.get("pn", fpath.stem)
            log.error(
                "normalize: build_normalized failed trace_id=%s pn=%s error=%s",
                trace_id, pn, exc,
                extra={"error_class": "PERMANENT", "severity": "ERROR", "retriable": False},
            )
            stats["errors"] += 1
            continue

        # Always replace normalized block (idempotent — never merge stale values)
        evidence["normalized"] = normalized

        # Stats
        stats["processed"] += 1
        src = normalized["best_price_source"]
        if src == "price_contract":
            stats["price_price_contract"] += 1
        elif src == "pipeline1":
            stats["price_pipeline1"] += 1
        elif src == "our_estimate":
            stats["price_our_estimate"] += 1
        else:
            stats["price_none"] += 1

        ds = normalized["best_description_source"]
        if ds == "dr":
            stats["desc_dr"] += 1
        elif ds == "content":
            stats["desc_content"] += 1
        else:
            stats["desc_none"] += 1

        ps = normalized["best_photo_source"]
        if ps == "photo_verdict":
            stats["photo_verdict"] += 1
        elif ps == "dr_image":
            stats["photo_dr_image"] += 1
        else:
            stats["photo_none"] += 1

        if not dry_run:
            try:
                _atomic_write(
                    fpath,
                    json.dumps(evidence, ensure_ascii=False, indent=2),
                )
            except Exception as exc:
                pn = evidence.get("pn", fpath.stem)
                log.error(
                    "normalize: write failed trace_id=%s pn=%s path=%s error=%s",
                    trace_id, pn, fpath, exc,
                    extra={"error_class": "TRANSIENT", "severity": "ERROR", "retriable": True},
                )
                stats["errors"] += 1

    # ── Report ──────────────────────────────────────────────────────────────
    print("=" * 60)
    print("EVIDENCE NORMALIZE — RESULTS")
    print("=" * 60)
    print()
    total = stats["processed"]
    print(f"  Processed:       {total} / {len(evidence_files)}")
    print(f"  Errors:          {stats['errors']}")
    print()
    print("PRICE (best_price_source):")
    print(f"  price_contract:  {stats['price_price_contract']}")
    print(f"  pipeline1:       {stats['price_pipeline1']}")
    print(f"  our_estimate:    {stats['price_our_estimate']}  (RUB, ~2022 rate)")
    print(f"  none:            {stats['price_none']}")
    if total:
        print(f"  coverage:        {(total - stats['price_none']) / total * 100:.1f}%")
    print()
    print("DESCRIPTION (best_description_source):")
    print(f"  dr:              {stats['desc_dr']}")
    print(f"  content:         {stats['desc_content']}")
    print(f"  none:            {stats['desc_none']}")
    if total:
        print(f"  coverage:        {(total - stats['desc_none']) / total * 100:.1f}%")
    print()
    print("PHOTO (best_photo_source):")
    print(f"  photo_verdict:   {stats['photo_verdict']}")
    print(f"  dr_image:        {stats['photo_dr_image']}")
    print(f"  none:            {stats['photo_none']}")
    if total:
        print(f"  coverage:        {(total - stats['photo_none']) / total * 100:.1f}%")
    print()

    if dry_run:
        print("[DRY RUN] No files were written.")
    else:
        log.info(
            "normalize: DONE run_id=%s trace_id=%s processed=%d errors=%d",
            run_id, trace_id, stats["processed"], stats["errors"],
        )


# ---------------------------------------------------------------------------
# Self-contained deterministic tests (no live API, no unmocked time)
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """Deterministic unit tests — no live I/O, no randomness."""
    failures = 0

    def check(label: str, got, want) -> None:
        nonlocal failures
        if got != want:
            print(f"  FAIL [{label}]: got {got!r}, want {want!r}")
            failures += 1
        else:
            print(f"  PASS [{label}]")

    # ── Price tests ──────────────────────────────────────────────────────────
    e_pc = {"price_contract": {"dr_value": 99.0, "dr_currency": "EUR"}}
    v, c, s = _pick_price(e_pc)
    check("price/price_contract", (v, c, s), (99.0, "EUR", "price_contract"))

    e_p1 = {"price": {"price_per_unit": 42.5, "currency": "USD"}}
    v, c, s = _pick_price(e_p1)
    check("price/pipeline1", (v, c, s), (42.5, "USD", "pipeline1"))

    e_both = {
        "price_contract": {"dr_value": 10.0, "dr_currency": "EUR"},
        "price": {"price_per_unit": 8.0, "currency": "USD"},
    }
    v, c, s = _pick_price(e_both)
    check("price/priority_pc_over_p1", (v, c, s), (10.0, "EUR", "price_contract"))

    e_our = {"price_contract": {"our_price_parsed": 714.1}}
    v, c, s = _pick_price(e_our)
    check("price/our_estimate", (v, c, s), (714.1, "RUB", "our_estimate"))

    e_our_skip = {
        "price_contract": {"dr_value": 50.0, "dr_currency": "EUR", "our_price_parsed": 714.1}
    }
    v, c, s = _pick_price(e_our_skip)
    check("price/dr_beats_our_estimate", (v, c, s), (50.0, "EUR", "price_contract"))

    e_none = {}
    v, c, s = _pick_price(e_none)
    check("price/none", (v, c, s), (None, None, None))

    # ── Description tests ────────────────────────────────────────────────────
    short = "Hi"
    long_dr = "A" * 60
    long_ct = "B" * 80  # longer

    e_dr_only = {"deep_research": {"description_ru": long_dr}}
    d, ds = _pick_description(e_dr_only)
    check("desc/dr_only", (d, ds), (long_dr, "dr"))

    e_ct_only = {"content": {"description": long_ct}}
    d, ds = _pick_description(e_ct_only)
    check("desc/content_only", (d, ds), (long_ct, "content"))

    e_both_long = {
        "deep_research": {"description_ru": long_dr},
        "content": {"description": long_ct},
    }
    d, ds = _pick_description(e_both_long)
    check("desc/both_pick_longer", (d, ds), (long_ct, "content"))

    e_dr_short = {
        "deep_research": {"description_ru": short},
        "content": {"description": long_ct},
    }
    d, ds = _pick_description(e_dr_short)
    check("desc/dr_short_use_content", (d, ds), (long_ct, "content"))

    e_neither = {}
    d, ds = _pick_description(e_neither)
    check("desc/none", (d, ds), (None, None))

    # ── Photo tests ──────────────────────────────────────────────────────────
    dr_url = "https://example.com/img.jpg"

    e_keep_cached = {
        "photo": {"verdict": "KEEP", "source": "cached"},
        "dr_image_url": dr_url,
    }
    u, ps = _pick_photo(e_keep_cached)
    check("photo/keep_cached", (u, ps), (dr_url, "photo_verdict"))

    e_keep_google = {
        "photo": {"verdict": "KEEP", "source": "google:https://shop.com/img.jpg"},
        "dr_image_url": dr_url,
    }
    u, ps = _pick_photo(e_keep_google)
    check("photo/keep_google", (u, ps), ("https://shop.com/img.jpg", "photo_verdict"))

    e_reject = {
        "photo": {"verdict": "REJECT", "source": "google:https://shop.com/img.jpg"},
        "dr_image_url": dr_url,
    }
    u, ps = _pick_photo(e_reject)
    check("photo/reject_fallback_dr", (u, ps), (dr_url, "dr_image"))

    e_no_photo = {"dr_image_url": dr_url}
    u, ps = _pick_photo(e_no_photo)
    check("photo/no_photo_obj_fallback_dr", (u, ps), (dr_url, "dr_image"))

    e_empty = {}
    u, ps = _pick_photo(e_empty)
    check("photo/none", (u, ps), (None, None))

    # bare URL in photo.source (edge case)
    bare_url = "https://bare-url.com/img.jpg"
    check("photo/bare_url", _parse_photo_source_url(bare_url, None), bare_url)

    # ── Build normalized integration test ────────────────────────────────────
    e_full = {
        "pn": "TEST-001",
        "price_contract": {"dr_value": 100.0, "dr_currency": "EUR"},
        "deep_research": {"description_ru": "A" * 100},
        "content": {"description": "B" * 60},
        "photo": {"verdict": "KEEP", "source": "cached"},
        "dr_image_url": "https://img.example.com/p.jpg",
    }
    n = build_normalized(e_full)
    check("integration/price", n["best_price"], 100.0)
    check("integration/price_source", n["best_price_source"], "price_contract")
    check("integration/desc_source", n["best_description_source"], "dr")  # dr is longer
    check("integration/photo_source", n["best_photo_source"], "photo_verdict")
    check("integration/schema", n["schema_version"], "normalized_v1")

    print()
    if failures:
        print(f"FAILED: {failures} test(s)")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evidence Normalization Layer")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--test", action="store_true", help="Run deterministic self-tests")
    args = parser.parse_args()

    if args.test:
        _run_tests()
    else:
        run(dry_run=args.dry_run)
