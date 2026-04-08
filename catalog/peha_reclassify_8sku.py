"""Tier-3 migration: reclassify 8 PEHA SKUs from wrong xlsx categories
to electrical_switch_covers.

The original xlsx source mislabeled PEHA switch frames/covers as
"Датчик" (sensor) or "Вентиль" (valve).  This module patches the
evidence bundles and training-data file to the correct category.

Satisfies Tier-3 module requirements:
  - trace_id from payload
  - idempotency_key per side-effect
  - no commit inside domain ops
  - structured error logging
  - deterministic, runnable in isolation
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]

TARGET_SKUS: list[str] = [
    "00020211",
    "101411",
    "104011",
    "105411",
    "106511",
    "109411",
    "125711",
    "127411",
]

OLD_CATEGORIES: frozenset[str] = frozenset({"Датчик", "Вентиль"})
NEW_CATEGORY: str = "electrical_switch_covers"

EVIDENCE_DIR: Path = REPO_ROOT / "downloads" / "evidence"
TRAINING_DATA_PATH: Path = REPO_ROOT / "training_data" / "category_classification.json"
EVIDENCE_BUNDLE_OUT: Path = (
    REPO_ROOT / "catalog" / "evidence_bundles" / "peha_sku_evidence.json"
)


@dataclass
class ReclassifyResult:
    trace_id: str
    sku: str
    idempotency_key: str
    old_category: str
    new_category: str
    file_patched: str
    status: str  # "applied" | "already_correct" | "skipped_not_found"


@dataclass
class BatchResult:
    trace_id: str
    results: list[ReclassifyResult] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


def _idempotency_key(trace_id: str, sku: str, target: str) -> str:
    return f"{trace_id}::{sku}::{target}"


def _patch_evidence_bundle(
    sku: str,
    trace_id: str,
    *,
    evidence_dir: Path = EVIDENCE_DIR,
) -> ReclassifyResult:
    idem_key = _idempotency_key(trace_id, sku, "evidence")
    path = evidence_dir / f"evidence_{sku}.json"
    if not path.exists():
        logger.warning(
            "evidence file not found",
            extra={
                "trace_id": trace_id,
                "sku": sku,
                "error_class": "PERMANENT",
                "severity": "WARNING",
                "retriable": False,
            },
        )
        return ReclassifyResult(
            trace_id=trace_id,
            sku=sku,
            idempotency_key=idem_key,
            old_category="",
            new_category=NEW_CATEGORY,
            file_patched=str(path),
            status="skipped_not_found",
        )

    data = json.loads(path.read_text(encoding="utf-8"))
    old_cat = data.get("expected_category", "")

    if old_cat == NEW_CATEGORY:
        return ReclassifyResult(
            trace_id=trace_id,
            sku=sku,
            idempotency_key=idem_key,
            old_category=old_cat,
            new_category=NEW_CATEGORY,
            file_patched=str(path),
            status="already_correct",
        )

    if old_cat not in OLD_CATEGORIES:
        logger.error(
            "unexpected current category — refusing to overwrite",
            extra={
                "trace_id": trace_id,
                "sku": sku,
                "current_category": old_cat,
                "error_class": "POLICY_VIOLATION",
                "severity": "ERROR",
                "retriable": False,
            },
        )
        return ReclassifyResult(
            trace_id=trace_id,
            sku=sku,
            idempotency_key=idem_key,
            old_category=old_cat,
            new_category=NEW_CATEGORY,
            file_patched=str(path),
            status="skipped_unexpected_category",
        )

    data["expected_category"] = NEW_CATEGORY
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    logger.info(
        "evidence bundle patched",
        extra={"trace_id": trace_id, "sku": sku, "old": old_cat, "new": NEW_CATEGORY},
    )
    return ReclassifyResult(
        trace_id=trace_id,
        sku=sku,
        idempotency_key=idem_key,
        old_category=old_cat,
        new_category=NEW_CATEGORY,
        file_patched=str(path),
        status="applied",
    )


def _patch_training_data(
    skus: list[str],
    trace_id: str,
    *,
    training_path: Path = TRAINING_DATA_PATH,
) -> list[ReclassifyResult]:
    results: list[ReclassifyResult] = []
    if not training_path.exists():
        for sku in skus:
            idem_key = _idempotency_key(trace_id, sku, "training")
            logger.warning(
                "training data file not found",
                extra={
                    "trace_id": trace_id,
                    "sku": sku,
                    "error_class": "PERMANENT",
                    "severity": "WARNING",
                    "retriable": False,
                },
            )
            results.append(
                ReclassifyResult(
                    trace_id=trace_id,
                    sku=sku,
                    idempotency_key=idem_key,
                    old_category="",
                    new_category=NEW_CATEGORY,
                    file_patched=str(training_path),
                    status="skipped_not_found",
                )
            )
        return results

    data: list[dict[str, Any]] = json.loads(
        training_path.read_text(encoding="utf-8")
    )
    sku_set = set(skus)
    patched_skus: set[str] = set()

    for entry in data:
        pn = entry.get("pn", "")
        if pn not in sku_set:
            continue
        idem_key = _idempotency_key(trace_id, pn, "training")
        old_cat = entry.get("correct_category", "")

        if old_cat == NEW_CATEGORY:
            results.append(
                ReclassifyResult(
                    trace_id=trace_id,
                    sku=pn,
                    idempotency_key=idem_key,
                    old_category=old_cat,
                    new_category=NEW_CATEGORY,
                    file_patched=str(training_path),
                    status="already_correct",
                )
            )
            patched_skus.add(pn)
            continue

        if old_cat not in OLD_CATEGORIES:
            logger.error(
                "unexpected training category — refusing to overwrite",
                extra={
                    "trace_id": trace_id,
                    "sku": pn,
                    "current_category": old_cat,
                    "error_class": "POLICY_VIOLATION",
                    "severity": "ERROR",
                    "retriable": False,
                },
            )
            results.append(
                ReclassifyResult(
                    trace_id=trace_id,
                    sku=pn,
                    idempotency_key=idem_key,
                    old_category=old_cat,
                    new_category=NEW_CATEGORY,
                    file_patched=str(training_path),
                    status="skipped_unexpected_category",
                )
            )
            patched_skus.add(pn)
            continue

        entry["correct_category"] = NEW_CATEGORY
        entry["correction"] = True
        results.append(
            ReclassifyResult(
                trace_id=trace_id,
                sku=pn,
                idempotency_key=idem_key,
                old_category=old_cat,
                new_category=NEW_CATEGORY,
                file_patched=str(training_path),
                status="applied",
            )
        )
        patched_skus.add(pn)

    # SKUs not found in training data
    for sku in skus:
        if sku not in patched_skus:
            idem_key = _idempotency_key(trace_id, sku, "training")
            results.append(
                ReclassifyResult(
                    trace_id=trace_id,
                    sku=sku,
                    idempotency_key=idem_key,
                    old_category="",
                    new_category=NEW_CATEGORY,
                    file_patched=str(training_path),
                    status="skipped_not_found",
                )
            )

    training_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return results


def _write_evidence_bundle(batch: BatchResult, *, out_path: Path = EVIDENCE_BUNDLE_OUT) -> None:
    bundle = {
        "schema_version": "1.0",
        "trace_id": batch.trace_id,
        "task_id": "RECLASSIFY-PEHA-8SKU",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": (
            "Reclassify 8 PEHA SKUs from xlsx-sourced wrong categories "
            "(Датчик/Вентиль → electrical_switch_covers)"
        ),
        "target_skus": TARGET_SKUS,
        "old_categories": sorted(OLD_CATEGORIES),
        "new_category": NEW_CATEGORY,
        "results": [
            {
                "sku": r.sku,
                "idempotency_key": r.idempotency_key,
                "old_category": r.old_category,
                "new_category": r.new_category,
                "file_patched": r.file_patched,
                "status": r.status,
            }
            for r in batch.results
        ],
        "errors": batch.errors,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def run(trace_id: str) -> BatchResult:
    """Execute the reclassification batch.

    Call this from worker boundary only — no internal commits.
    """
    batch = BatchResult(trace_id=trace_id)

    # Phase 1: patch evidence bundles
    for sku in TARGET_SKUS:
        try:
            result = _patch_evidence_bundle(sku, trace_id, evidence_dir=EVIDENCE_DIR)
            batch.results.append(result)
        except Exception as exc:
            logger.error(
                "failed to patch evidence bundle",
                extra={
                    "trace_id": trace_id,
                    "sku": sku,
                    "error_class": "TRANSIENT",
                    "severity": "ERROR",
                    "retriable": True,
                },
                exc_info=True,
            )
            batch.errors.append(
                {
                    "sku": sku,
                    "phase": "evidence_bundle",
                    "error": str(exc),
                    "error_class": "TRANSIENT",
                }
            )

    # Phase 2: patch training data
    try:
        training_results = _patch_training_data(TARGET_SKUS, trace_id, training_path=TRAINING_DATA_PATH)
        batch.results.extend(training_results)
    except Exception as exc:
        logger.error(
            "failed to patch training data",
            extra={
                "trace_id": trace_id,
                "error_class": "TRANSIENT",
                "severity": "ERROR",
                "retriable": True,
            },
            exc_info=True,
        )
        batch.errors.append(
            {
                "phase": "training_data",
                "error": str(exc),
                "error_class": "TRANSIENT",
            }
        )

    # Phase 3: write evidence bundle
    _write_evidence_bundle(batch, out_path=EVIDENCE_BUNDLE_OUT)

    applied = sum(1 for r in batch.results if r.status == "applied")
    logger.info(
        "reclassification batch complete",
        extra={
            "trace_id": trace_id,
            "total": len(batch.results),
            "applied": applied,
            "errors": len(batch.errors),
        },
    )
    return batch


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    tid = sys.argv[1] if len(sys.argv) > 1 else f"manual_{uuid.uuid4().hex[:8]}"
    result = run(tid)
    applied = sum(1 for r in result.results if r.status == "applied")
    print(f"Done: {applied} applied, {len(result.errors)} errors, trace_id={tid}")
