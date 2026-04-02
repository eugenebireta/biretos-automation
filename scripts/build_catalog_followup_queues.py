"""Build operational follow-up queues from refreshed local evidence bundles."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
DEFAULT_EVIDENCE_DIR = DOWNLOADS / "evidence"
DEFAULT_OUTPUT_DIR = DOWNLOADS / "scout_cache"


def _load_bundle(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def iter_bundles(evidence_dir: Path) -> list[dict[str, Any]]:
    bundles: list[dict[str, Any]] = []
    for path in sorted(evidence_dir.glob("evidence_*.json")):
        payload = _load_bundle(path)
        if isinstance(payload, dict) and payload.get("pn"):
            bundles.append(payload)
    return bundles


def build_photo_recovery_row(bundle: dict[str, Any]) -> dict[str, Any]:
    content = bundle.get("content", {})
    price = bundle.get("price", {})
    return {
        "part_number": bundle.get("pn", ""),
        "product_name": bundle.get("name", ""),
        "brand": bundle.get("brand", ""),
        "card_status": bundle.get("card_status", ""),
        "photo_verdict": bundle.get("photo", {}).get("verdict", ""),
        "photo_verdict_reason": bundle.get("photo", {}).get("verdict_reason", ""),
        "current_image_status": bundle.get("merchandising", {}).get("image_status", "") or bundle.get("photo", {}).get("photo_status", ""),
        "current_image_local_path": bundle.get("merchandising", {}).get("image_local_path", ""),
        "site_placement": content.get("site_placement", ""),
        "product_type": content.get("product_type", ""),
        "description_source": content.get("description_source", ""),
        "price_status": price.get("price_status", ""),
        "price_source_url": price.get("source_url", ""),
        "suggested_action": "find_replacement_photo_from_trusted_source",
    }


def build_price_followup_row(bundle: dict[str, Any]) -> dict[str, Any]:
    content = bundle.get("content", {})
    price = bundle.get("price", {})
    return {
        "part_number": bundle.get("pn", ""),
        "product_name": bundle.get("name", ""),
        "brand": bundle.get("brand", ""),
        "card_status": bundle.get("card_status", ""),
        "price_status": price.get("price_status", ""),
        "price_source_url": price.get("source_url", ""),
        "currency": price.get("currency", ""),
        "rub_price": price.get("rub_price"),
        "stock_status": price.get("stock_status", ""),
        "category_mismatch": bool(price.get("category_mismatch")),
        "site_placement": content.get("site_placement", ""),
        "product_type": content.get("product_type", ""),
        "suggested_action": "find_admissible_price_source_or_confirm_no_price",
    }


def run(
    *,
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    prefix: str = "",
) -> dict[str, Any]:
    bundles = iter_bundles(evidence_dir)
    photo_queue = [
        build_photo_recovery_row(bundle)
        for bundle in bundles
        if str(bundle.get("photo", {}).get("verdict", "") or "").strip().upper() == "REJECT"
    ]
    price_queue = [
        build_price_followup_row(bundle)
        for bundle in bundles
        if str(bundle.get("price", {}).get("price_status", "") or "").strip() in {
            "no_price_found",
            "ambiguous_offer",
            "category_mismatch_only",
        }
    ]

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix_part = f"{prefix}_" if prefix else ""
    photo_path = output_dir / f"{prefix_part}photo_recovery_queue_{ts}.jsonl"
    price_path = output_dir / f"{prefix_part}price_followup_queue_{ts}.jsonl"
    summary_path = output_dir / f"{prefix_part}followup_summary_{ts}.json"

    _write_jsonl(photo_path, photo_queue)
    _write_jsonl(price_path, price_queue)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_evidence_dir": str(evidence_dir),
        "photo_recovery_queue": str(photo_path),
        "price_followup_queue": str(price_path),
        "photo_recovery_count": len(photo_queue),
        "price_followup_count": len(price_queue),
        "source_bundle_count": len(bundles),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build photo/price follow-up queues from refreshed evidence bundles.")
    parser.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--prefix", default="")
    args = parser.parse_args()

    summary = run(
        evidence_dir=Path(args.evidence_dir),
        output_dir=Path(args.output_dir),
        prefix=args.prefix,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
