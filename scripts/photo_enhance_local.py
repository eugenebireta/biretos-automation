"""Deterministic local photo enhancement for temporary placeholder images.

This runner creates derivative catalog-friendly images from local raw photos
without changing evidence truth. The raw image remains canonical; the enhanced
asset is a separate placeholder artifact with explicit lineage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
RAW_PHOTOS_DIR = DOWNLOADS / "photos"
ENHANCED_PHOTOS_DIR = DOWNLOADS / "photos_enhanced"
SCOUT_CACHE_DIR = DOWNLOADS / "scout_cache"

DEFAULT_SEED_FILE = SCOUT_CACHE_DIR / "photo_enhance_seed.jsonl"
DEFAULT_MANIFEST_FILE = SCOUT_CACHE_DIR / "photo_enhance_manifest.jsonl"
PHOTO_VERDICT_FILE = DOWNLOADS / "photo_verdict.json"

VALID_SOURCE_STATUSES = {"placeholder", "family_evidence", "exact_evidence", "rejected"}
DEFAULT_PROFILE = "catalog_placeholder_v1"
SCHEMA_VERSION = "photo_enhance_manifest_v1"
PLACEHOLDER_ENHANCEMENT_STEPS = [
    "exif_transpose",
    "flatten_transparency",
    "autocontrast",
    "mild_color_contrast_boost",
    "unsharp_mask",
    "trim_uniform_border",
    "contain_to_canvas",
    "soft_shadow",
    "gradient_background",
    "jpeg_export",
]


def safe_fn(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()) or "unnamed"


def compute_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def get_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        return img.size


def load_seed_records(seed_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not seed_path.exists():
        return records
    for raw_line in seed_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            continue
        pn = str(payload.get("part_number", "")).strip()
        source_local_path = str(payload.get("source_local_path", "")).strip()
        if not pn or not source_local_path:
            continue
        source_photo_status = str(payload.get("source_photo_status", "placeholder")).strip() or "placeholder"
        if source_photo_status not in VALID_SOURCE_STATUSES:
            continue
        records.append(
            {
                "part_number": pn,
                "brand": str(payload.get("brand", "")).strip(),
                "product_name": str(payload.get("product_name", "")).strip(),
                "source_local_path": source_local_path,
                "source_photo_status": source_photo_status,
                "source_storage_role": str(payload.get("source_storage_role", "")).strip(),
                "source_url": str(payload.get("source_url", "")).strip(),
                "source_provider": str(payload.get("source_provider", "local_raw")).strip() or "local_raw",
                "enhancement_profile": str(payload.get("enhancement_profile", DEFAULT_PROFILE)).strip() or DEFAULT_PROFILE,
                "background_hex": str(payload.get("background_hex", "#F4F1EB")).strip() or "#F4F1EB",
                "canvas_px": int(payload.get("canvas_px", 1400) or 1400),
                "content_ratio": float(payload.get("content_ratio", 0.84) or 0.84),
                "notes": str(payload.get("notes", "")).strip(),
            }
        )
    return records


def _normalize_verdict_pn(value: str) -> str:
    return safe_fn(str(value or "").strip()).upper()


def _normalize_path(value: str | Path) -> str:
    return str(Path(value).resolve()).replace("/", "\\").lower()


@lru_cache(maxsize=1)
def load_photo_verdict_index() -> dict[str, dict[str, Any]]:
    by_pn: dict[str, dict[str, Any]] = {}
    by_path: dict[str, dict[str, Any]] = {}
    if not PHOTO_VERDICT_FILE.exists():
        return {"by_pn": by_pn, "by_path": by_path}
    try:
        payload = json.loads(PHOTO_VERDICT_FILE.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"by_pn": by_pn, "by_path": by_path}
    if not isinstance(payload, dict):
        return {"by_pn": by_pn, "by_path": by_path}
    for pn_key, row in payload.items():
        if not isinstance(row, dict):
            continue
        entry = {
            "pn_key": str(pn_key),
            "verdict": str(row.get("verdict", "")).strip().upper(),
            "reason": str(row.get("reason", "")).strip(),
            "path": str(row.get("path", "")).strip(),
        }
        if entry["verdict"] not in {"KEEP", "REJECT"}:
            continue
        normalized_pn = _normalize_verdict_pn(pn_key)
        if normalized_pn:
            by_pn[normalized_pn] = entry
        if entry["path"]:
            by_path[_normalize_path(entry["path"])] = entry
    return {"by_pn": by_pn, "by_path": by_path}


def resolve_photo_verdict(part_number: str, source_path: Path) -> dict[str, str]:
    verdict_index = load_photo_verdict_index()
    by_path = verdict_index["by_path"]
    by_pn = verdict_index["by_pn"]

    path_key = _normalize_path(source_path)
    entry = by_path.get(path_key)
    if entry is not None:
        return {
            "verdict": entry["verdict"],
            "reason": entry["reason"],
            "match": "path",
            "matched_key": entry["path"],
        }

    pn_key = _normalize_verdict_pn(part_number)
    entry = by_pn.get(pn_key)
    if entry is not None:
        return {
            "verdict": entry["verdict"],
            "reason": entry["reason"],
            "match": "part_number",
            "matched_key": entry["pn_key"],
        }

    return {"verdict": "UNKNOWN", "reason": "", "match": "", "matched_key": ""}


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    normalized = str(value or "").strip().lstrip("#")
    if len(normalized) != 6:
        return (244, 241, 235)
    return tuple(int(normalized[i : i + 2], 16) for i in (0, 2, 4))


def _trim_uniform_border(image: Image.Image, background_rgb: tuple[int, int, int], tolerance: int = 10) -> Image.Image:
    base = Image.new("RGB", image.size, background_rgb)
    diff = ImageChops.difference(image.convert("RGB"), base).convert("L")
    mask = diff.point(lambda px: 255 if px > tolerance else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return image
    return image.crop(bbox)


def _make_vertical_gradient(size: tuple[int, int], top_rgb: tuple[int, int, int], bottom_rgb: tuple[int, int, int]) -> Image.Image:
    width, height = size
    gradient = Image.new("RGB", size, top_rgb)
    if height <= 1:
        return gradient
    px = gradient.load()
    for y in range(height):
        ratio = y / (height - 1)
        color = tuple(int(top_rgb[i] * (1 - ratio) + bottom_rgb[i] * ratio) for i in range(3))
        for x in range(width):
            px[x, y] = color
    return gradient


def _make_canvas(size: int, background_rgb: tuple[int, int, int]) -> Image.Image:
    lighter = tuple(min(channel + 8, 255) for channel in background_rgb)
    darker = tuple(max(channel - 6, 0) for channel in background_rgb)
    return _make_vertical_gradient((size, size), lighter, darker)


def _prepare_content(image: Image.Image) -> Image.Image:
    content = ImageOps.exif_transpose(image)
    if content.mode not in {"RGB", "RGBA"}:
        content = content.convert("RGBA")
    if content.mode == "RGBA":
        bg = Image.new("RGBA", content.size, (255, 255, 255, 255))
        content = Image.alpha_composite(bg, content).convert("RGB")
    else:
        content = content.convert("RGB")
    content = ImageOps.autocontrast(content, cutoff=1)
    content = ImageEnhance.Color(content).enhance(1.03)
    content = ImageEnhance.Contrast(content).enhance(1.04)
    content = content.filter(ImageFilter.UnsharpMask(radius=1.3, percent=130, threshold=2))
    return content


def output_path_for_record(part_number: str, profile: str, source_sha1: str) -> Path:
    filename = f"{safe_fn(part_number)}__{safe_fn(profile)}__{source_sha1[:8]}.jpg"
    return ENHANCED_PHOTOS_DIR / filename


def enhance_to_placeholder(
    source_path: Path,
    dest_path: Path,
    *,
    canvas_px: int,
    content_ratio: float,
    background_hex: str,
) -> dict[str, Any]:
    background_rgb = _hex_to_rgb(background_hex)
    with Image.open(source_path) as raw:
        content = _prepare_content(raw)
    trimmed = _trim_uniform_border(content, (255, 255, 255), tolerance=10)
    target_box = max(1, int(canvas_px * content_ratio))
    contained = ImageOps.contain(trimmed, (target_box, target_box), method=Image.Resampling.LANCZOS)

    canvas = _make_canvas(canvas_px, background_rgb)
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    content_rgba = contained.convert("RGBA")
    alpha = content_rgba.getchannel("A") if "A" in content_rgba.getbands() else Image.new("L", content_rgba.size, 255)
    shadow_mask = alpha.filter(ImageFilter.GaussianBlur(radius=14))
    x = (canvas_px - contained.width) // 2
    y = (canvas_px - contained.height) // 2
    shadow.paste((0, 0, 0, 28), (x + 10, y + 12), shadow_mask)
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow).convert("RGB")
    canvas.paste(contained, (x, y))

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest_path, format="JPEG", quality=93, optimize=True, progressive=True)

    width, height = get_size(dest_path)
    return {
        "enhancement_steps": PLACEHOLDER_ENHANCEMENT_STEPS,
        "width": width,
        "height": height,
    }


def _derive_source_storage_role(source_path: Path) -> str:
    try:
        source_path.resolve().relative_to(RAW_PHOTOS_DIR.resolve())
        return "canonical_raw_photo"
    except Exception:
        return "external_local_source"


def materialize_seed_record(record: dict[str, Any]) -> dict[str, Any]:
    source_path = Path(record["source_local_path"])
    source_exists = source_path.exists()
    source_storage_role = record.get("source_storage_role") or _derive_source_storage_role(source_path)
    source_width = source_height = source_size_kb = 0
    source_sha1 = ""
    if source_exists:
        source_width, source_height = get_size(source_path)
        source_size_kb = source_path.stat().st_size // 1024
        source_sha1 = compute_sha1(source_path)

    enhancement_profile = record.get("enhancement_profile", DEFAULT_PROFILE)
    enhanced_path = output_path_for_record(record["part_number"], enhancement_profile, source_sha1 or "missing")
    existing_derivative_found = source_exists and enhanced_path.exists()
    used_existing_derivative = False
    stale_existing_derivative_found = False
    enhancement_meta = {"enhancement_steps": PLACEHOLDER_ENHANCEMENT_STEPS, "width": 0, "height": 0}
    output_sha1 = ""
    output_size_kb = 0
    output_exists = False
    generation_reason = "generated_from_raw"
    source_verdict = resolve_photo_verdict(record["part_number"], source_path) if source_exists else {
        "verdict": "UNKNOWN",
        "reason": "",
        "match": "",
        "matched_key": "",
    }

    if source_exists and source_verdict["verdict"] != "REJECT":
        if existing_derivative_found:
            used_existing_derivative = True
            generation_reason = "existing_derivative_preserved"
        else:
            enhancement_meta = enhance_to_placeholder(
                source_path,
                enhanced_path,
                canvas_px=int(record.get("canvas_px", 1400) or 1400),
                content_ratio=float(record.get("content_ratio", 0.84) or 0.84),
                background_hex=str(record.get("background_hex", "#F4F1EB")),
            )
        output_exists = enhanced_path.exists()
        if output_exists:
            output_sha1 = compute_sha1(enhanced_path)
            output_size_kb = enhanced_path.stat().st_size // 1024
            if used_existing_derivative:
                enhancement_meta["width"], enhancement_meta["height"] = get_size(enhanced_path)
    elif source_exists and source_verdict["verdict"] == "REJECT":
        generation_reason = "blocked_by_source_photo_verdict"
        stale_existing_derivative_found = existing_derivative_found

    source_photo_status = record.get("source_photo_status", "placeholder")
    policy_reason_code = ""
    review_required = False
    output_photo_status = "placeholder"
    derivative_kind = "placeholder_enhanced"
    if source_photo_status != "placeholder":
        review_required = True
        policy_reason_code = "non_placeholder_source_requires_review"
    if not source_exists:
        review_required = True
        policy_reason_code = "source_missing"
    if source_photo_status == "rejected":
        review_required = True
        policy_reason_code = "rejected_source_not_safe_for_enhancement"
    if source_verdict["verdict"] == "REJECT":
        output_photo_status = "rejected"
        derivative_kind = "blocked_reject"
        review_required = False
        policy_reason_code = "source_photo_verdict_reject"

    return {
        "schema_version": SCHEMA_VERSION,
        "part_number": record["part_number"],
        "brand": record.get("brand", ""),
        "product_name": record.get("product_name", ""),
        "source_provider": record.get("source_provider", "local_raw"),
        "source_local_path": str(source_path),
        "source_url": record.get("source_url", ""),
        "source_exists": source_exists,
        "source_storage_role": source_storage_role,
        "source_photo_status": source_photo_status,
        "source_photo_verdict": source_verdict["verdict"],
        "source_photo_verdict_reason": source_verdict["reason"],
        "source_photo_verdict_match": source_verdict["match"],
        "source_photo_verdict_matched_key": source_verdict["matched_key"],
        "source_sha1": source_sha1,
        "source_width": source_width,
        "source_height": source_height,
        "source_size_kb": source_size_kb,
        "raw_photo_canonical_preserved": source_storage_role == "canonical_raw_photo",
        "enhancement_profile": enhancement_profile,
        "enhancement_non_generative": True,
        "sku_detail_invention_allowed": False,
        "enhancement_steps": enhancement_meta["enhancement_steps"],
        "enhanced_local_path": str(enhanced_path) if output_exists else "",
        "enhanced_exists": output_exists,
        "enhanced_width": enhancement_meta["width"],
        "enhanced_height": enhancement_meta["height"],
        "enhanced_size_kb": output_size_kb,
        "enhanced_sha1": output_sha1,
        "used_existing_derivative": used_existing_derivative,
        "stale_existing_derivative_found": stale_existing_derivative_found,
        "stale_existing_derivative_path": str(enhanced_path) if stale_existing_derivative_found else "",
        "cleanup_recommended": stale_existing_derivative_found,
        "generation_reason": generation_reason,
        "derivative_kind": derivative_kind,
        "output_photo_status": output_photo_status,
        "output_identity_proof": False,
        "replacement_required": True,
        "lineage_preserved": bool(source_sha1 and output_sha1),
        "policy_reason_code": policy_reason_code,
        "review_required": review_required,
        "notes": record.get("notes", ""),
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
    parser = argparse.ArgumentParser(description="Create derivative placeholder-friendly enhanced photos from local raw assets.")
    parser.add_argument("--seed", default=str(DEFAULT_SEED_FILE))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_FILE))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    results = run(Path(args.seed), Path(args.manifest), limit=args.limit)
    ok = sum(1 for row in results if row["enhanced_exists"])
    print(f"seed_records={len(results)} enhanced={ok} output_dir={ENHANCED_PHOTOS_DIR}")
    for row in results:
        print(
            f"{row['part_number']}: enhanced={row['enhanced_exists']} "
            f"status={row['output_photo_status']} review={row['review_required']} "
            f"path={row['enhanced_local_path'][:100]}"
        )


if __name__ == "__main__":
    main()
