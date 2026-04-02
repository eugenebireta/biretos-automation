"""Manual photo/scene scout for Codex-seeded trusted product pages.

This runner lets Codex or an operator supply exact page URLs discovered manually
and then reuses the deterministic page parser/downloader from photo_pipeline
without requiring SerpAPI search.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from photo_pipeline import (
    absolutize_url,
    compute_sha1,
    download_image,
    get_size,
    parse_product_page,
    safe_fn,
)
from source_trust import get_source_role, is_denied
from trust import get_source_trust


ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
SCOUT_CACHE_DIR = DOWNLOADS / "scout_cache"
DEFAULT_SEED_FILE = SCOUT_CACHE_DIR / "photo_scene_manual_seed.jsonl"
PRODUCT_PHOTOS_DIR = DOWNLOADS / "photos"
SCOUT_ASSET_DIR = DOWNLOADS / "scout_assets"
DEFAULT_MANIFEST_FILE = SCOUT_CACHE_DIR / "photo_scene_manual_manifest.jsonl"

VALID_ASSET_KINDS = {"product_photo", "scene_placeholder"}


def load_seed_records(seed_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not seed_path.exists():
        return records
    for raw_line in seed_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            continue
        part_number = str(payload.get("part_number", "")).strip()
        page_url = str(payload.get("page_url", "")).strip()
        asset_url = str(payload.get("asset_url", "")).strip()
        asset_kind = str(payload.get("asset_kind", "product_photo")).strip()
        if not part_number or asset_kind not in VALID_ASSET_KINDS:
            continue
        if not page_url and not asset_url:
            continue
        records.append(
            {
                "part_number": part_number,
                "brand": str(payload.get("brand", "")).strip(),
                "product_name": str(payload.get("product_name", "")).strip(),
                "asset_kind": asset_kind,
                "page_url": page_url,
                "asset_url": asset_url,
                "source_provider": str(payload.get("source_provider", "codex_manual")).strip() or "codex_manual",
                "notes": str(payload.get("notes", "")).strip(),
            }
        )
    return records


def _output_name(part_number: str, asset_kind: str) -> str:
    if asset_kind == "scene_placeholder":
        return f"{safe_fn(part_number)}__scene.jpg"
    return f"{safe_fn(part_number)}.jpg"


def output_path_for_record(part_number: str, asset_kind: str) -> Path:
    if asset_kind == "scene_placeholder":
        return SCOUT_ASSET_DIR / _output_name(part_number, asset_kind)
    return PRODUCT_PHOTOS_DIR / _output_name(part_number, asset_kind)


def _default_photo_status(asset_kind: str) -> str:
    return "placeholder" if asset_kind == "scene_placeholder" else "exact_evidence"


def materialize_seed_record(record: dict[str, Any]) -> dict[str, Any]:
    part_number = record["part_number"]
    page_url = record.get("page_url", "")
    page_parse: dict[str, Any] = {}
    if page_url:
        page_parse = parse_product_page(page_url, pn=part_number)

    resolved_asset_url = record.get("asset_url", "") or page_parse.get("image_url", "")
    if resolved_asset_url and page_url:
        resolved_asset_url = absolutize_url(resolved_asset_url, page_url)

    source_url = page_url or resolved_asset_url
    trust = get_source_trust(source_url) if source_url else {"tier": "unknown", "weight": 0.40, "domain": ""}
    source_role = get_source_role(source_url) if source_url else "organic_discovery"
    if source_role == "organic_discovery" and trust.get("domain"):
        source_role = get_source_role(str(trust["domain"]))
    denied = bool(source_url and is_denied(source_url))

    local_path = output_path_for_record(part_number, record["asset_kind"])
    local_path.parent.mkdir(parents=True, exist_ok=True)

    download_ok = False
    width = height = size_kb = 0
    sha1 = ""
    used_existing_canonical = record["asset_kind"] == "product_photo" and local_path.exists()
    selection_reason = "downloaded_from_seed"

    if used_existing_canonical:
        download_ok = True
        width, height = get_size(local_path)
        size_kb = local_path.stat().st_size // 1024
        sha1 = compute_sha1(local_path)
        selection_reason = "existing_canonical_preserved"
    elif resolved_asset_url and not denied:
        download_ok = download_image(resolved_asset_url, local_path)
        if download_ok:
            width, height = get_size(local_path)
            size_kb = local_path.stat().st_size // 1024
            sha1 = compute_sha1(local_path)

    return {
        "part_number": part_number,
        "brand": record.get("brand", ""),
        "product_name": record.get("product_name", ""),
        "asset_kind": record["asset_kind"],
        "source_provider": record.get("source_provider", "codex_manual"),
        "page_url": page_url,
        "resolved_asset_url": resolved_asset_url,
        "source_domain": (urlparse(source_url).netloc or "").lower().removeprefix("www.") if source_url else "",
        "source_role": source_role,
        "source_tier": trust.get("tier", "unknown"),
        "source_weight": trust.get("weight", 0.40),
        "source_denylisted": denied,
        "storage_role": "canonical_raw_photo" if record["asset_kind"] == "product_photo" else "scratch_placeholder",
        "photo_status_target": _default_photo_status(record["asset_kind"]),
        "exact_structured_pn_match": bool(page_parse.get("exact_structured_pn_match")),
        "structured_pn_match_location": page_parse.get("structured_pn_match_location", ""),
        "mpn_confirmed_via_jsonld": bool(page_parse.get("mpn_confirmed")),
        "download_ok": download_ok,
        "local_path": str(local_path) if download_ok else "",
        "used_existing_canonical": used_existing_canonical,
        "selection_reason": selection_reason,
        "width": width,
        "height": height,
        "size_kb": size_kb,
        "sha1": sha1,
        "notes": record.get("notes", ""),
        "review_required": denied or not download_ok or source_role == "organic_discovery",
    }


def run(seed_path: Path, manifest_path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    records = load_seed_records(seed_path)
    if limit is not None:
        records = records[:limit]
    results = [materialize_seed_record(record) for record in records]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        for row in results:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize Codex-seeded photo/scene assets.")
    parser.add_argument("--seed", default=str(DEFAULT_SEED_FILE))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_FILE))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    results = run(Path(args.seed), Path(args.manifest), limit=args.limit)
    ok = sum(1 for row in results if row["download_ok"])
    print(
        f"seed_records={len(results)} download_ok={ok} "
        f"product_dir={PRODUCT_PHOTOS_DIR} scratch_dir={SCOUT_ASSET_DIR}"
    )
    for row in results:
        print(
            f"{row['part_number']}: ok={row['download_ok']} role={row['source_role']} "
            f"tier={row['source_tier']} status={row['photo_status_target']} "
            f"url={row['resolved_asset_url'][:100]}"
        )


if __name__ == "__main__":
    main()
