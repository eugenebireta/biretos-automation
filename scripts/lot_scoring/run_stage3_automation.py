from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from scripts.lot_scoring.category_engine import VALID_CATEGORIES, reload_taxonomy
from scripts.lot_scoring.pipeline.helpers import normalize_category_key, to_float, to_str
from scripts.lot_scoring.run_full_ranking_v341 import run_full_ranking


_DATA_DIR = Path(__file__).resolve().parent / "data"
_DEFAULT_SKU_LOOKUP_PATH = _DATA_DIR / "sku_lookup.json"
_DEFAULT_PN_PATTERNS_PATH = _DATA_DIR / "pn_patterns.json"
_DEFAULT_TAXONOMY_VERSION_PATH = _DATA_DIR / "taxonomy_version.json"
_DEFAULT_TAXONOMY_LOCK_PATH = _DATA_DIR / "taxonomy_lock.json"

_LOOKUP_ALLOWED_CATEGORIES: frozenset[str] = frozenset(VALID_CATEGORIES - {"toxic_fake", "unknown"})
_DEFAULT_AUTHOR = "stage3_automation"


def _normalize_sku_key(value: object) -> str:
    text = to_str(value).upper().replace(" ", "")
    return re.sub(r"[^A-Z0-9]", "", text)


def _fixed_prefix_length(pattern: str) -> int:
    stripped = pattern[1:] if pattern.startswith("^") else pattern
    length = 0
    for ch in stripped:
        if ch in {".", "[", "]", "(", ")", "+", "*", "?", "{", "\\", "|", "^", "$"}:
            break
        length += 1
    return length


def _fixed_prefix_text(pattern: str) -> str:
    stripped = pattern[1:] if pattern.startswith("^") else pattern
    chars: list[str] = []
    escaped = False
    for ch in stripped:
        if escaped:
            chars.append(ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch in {".", "[", "]", "(", ")", "+", "*", "?", "{", "|", "^", "$"}:
            break
        chars.append(ch)
    return "".join(chars)


def _load_json_object(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _load_json_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON array in {path}")
    result: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            result.append(dict(item))
    return result


def _dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=False)


def _compute_sources_signature(unknown_intelligence_path: Path, llm_results_path: Path) -> str:
    digest = hashlib.sha256()
    for path in (unknown_intelligence_path, llm_results_path):
        digest.update(path.name.encode("utf-8"))
        if path.exists():
            digest.update(path.read_bytes())
        else:
            digest.update(b"__MISSING__")
    return digest.hexdigest()


def _read_unknown_intelligence(path: Path) -> set[str]:
    if not path.exists():
        return set()
    selected: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            ranking = to_str(row.get("ranking"))
            if ranking not in {"top_usd", "top_freq"}:
                continue
            pn = _normalize_sku_key(row.get("pn"))
            if pn:
                selected.add(pn)
    return selected


def _read_llm_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = _load_json_object(path, default={})
    raw_rows = payload.get("results", [])
    if not isinstance(raw_rows, list):
        return []
    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "lot_id": to_str(row.get("lot_id")),
                "slice_rank": int(to_float(row.get("slice_rank"), 0.0)),
                "sku_code": _normalize_sku_key(row.get("sku_code")),
                "category_engine": normalize_category_key(row.get("category_engine")),
                "llm_category": normalize_category_key(row.get("llm_category")),
                "confidence": to_float(row.get("confidence"), 0.0),
                "effective_usd": max(0.0, to_float(row.get("effective_usd"), 0.0)),
            }
        )
    return rows


def _collect_sku_candidates(
    llm_rows: list[dict[str, Any]],
    *,
    target_unknown_pn: set[str],
    min_confidence: float,
    min_votes: int,
) -> list[dict[str, Any]]:
    votes: dict[tuple[str, str], dict[str, Any]] = {}
    for row in llm_rows:
        sku = to_str(row.get("sku_code"))
        if not sku:
            continue
        if target_unknown_pn and sku not in target_unknown_pn:
            continue
        if to_str(row.get("category_engine"), "unknown") != "unknown":
            continue
        category = to_str(row.get("llm_category"), "unknown")
        if category not in _LOOKUP_ALLOWED_CATEGORIES:
            continue
        confidence = to_float(row.get("confidence"), 0.0)
        if confidence < min_confidence:
            continue
        key = (sku, category)
        entry = votes.setdefault(key, {"usd": 0.0, "votes": 0, "lot_ids": set()})
        entry["usd"] = to_float(entry.get("usd"), 0.0) + max(0.0, to_float(row.get("effective_usd"), 0.0))
        entry["votes"] = int(entry.get("votes", 0)) + 1
        lot_ids = entry.get("lot_ids")
        if isinstance(lot_ids, set):
            lot_ids.add(to_str(row.get("lot_id")))

    by_sku: dict[str, list[dict[str, Any]]] = {}
    for (sku, category), stat in votes.items():
        by_sku.setdefault(sku, []).append(
            {
                "sku": sku,
                "category": category,
                "usd": to_float(stat.get("usd"), 0.0),
                "votes": int(stat.get("votes", 0)),
                "lot_count": len(stat.get("lot_ids", set())),
            }
        )

    selected: list[dict[str, Any]] = []
    for sku in sorted(by_sku.keys()):
        ranked = sorted(
            by_sku[sku],
            key=lambda item: (-to_float(item.get("usd"), 0.0), -int(item.get("votes", 0)), to_str(item.get("category"))),
        )
        best = ranked[0]
        if int(best.get("votes", 0)) < int(min_votes):
            continue
        selected.append(best)

    selected.sort(key=lambda item: (-to_float(item.get("usd"), 0.0), to_str(item.get("sku"))))
    return selected


def _pattern_safety_audit(patterns: list[dict[str, Any]]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(patterns):
        pattern = to_str(item.get("pattern"))
        category = normalize_category_key(item.get("category"))
        if not pattern or category not in _LOOKUP_ALLOWED_CATEGORIES:
            continue
        normalized.append(
            {
                "index": index,
                "pattern": pattern,
                "category": category,
                "prefix": _fixed_prefix_text(pattern),
                "prefix_len": _fixed_prefix_length(pattern),
            }
        )

    overlaps: set[tuple[str, str, str, str]] = set()
    redundant_prefixes: set[tuple[str, str, str]] = set()
    shadowing: set[tuple[str, str, str, str]] = set()
    for i in range(len(normalized)):
        left = normalized[i]
        for j in range(i + 1, len(normalized)):
            right = normalized[j]
            left_prefix = to_str(left.get("prefix"))
            right_prefix = to_str(right.get("prefix"))
            if not left_prefix or not right_prefix:
                continue
            related = (
                left_prefix == right_prefix
                or left_prefix.startswith(right_prefix)
                or right_prefix.startswith(left_prefix)
            )
            if not related:
                continue

            left_pattern = to_str(left.get("pattern"))
            right_pattern = to_str(right.get("pattern"))
            left_category = to_str(left.get("category"))
            right_category = to_str(right.get("category"))
            if left_category != right_category:
                overlaps.add((left_pattern, left_category, right_pattern, right_category))

            if left_category == right_category and left_prefix != right_prefix:
                shorter = left if len(left_prefix) < len(right_prefix) else right
                longer = right if shorter is left else left
                redundant_prefixes.add(
                    (
                        to_str(shorter.get("pattern")),
                        to_str(longer.get("pattern")),
                        to_str(shorter.get("category")),
                    )
                )

            if left_category != right_category and left_prefix != right_prefix:
                general = left if len(left_prefix) < len(right_prefix) else right
                specific = right if general is left else left
                if int(general.get("index", 0)) < int(specific.get("index", 0)):
                    shadowing.add(
                        (
                            to_str(general.get("pattern")),
                            to_str(general.get("category")),
                            to_str(specific.get("pattern")),
                            to_str(specific.get("category")),
                        )
                    )

    return {
        "overlaps_count": len(overlaps),
        "overlaps": [
            {"left_pattern": left_p, "left_category": left_c, "right_pattern": right_p, "right_category": right_c}
            for left_p, left_c, right_p, right_c in sorted(overlaps)
        ],
        "redundant_prefixes_count": len(redundant_prefixes),
        "redundant_prefixes": [
            {"shorter_pattern": shorter, "longer_pattern": longer, "category": category}
            for shorter, longer, category in sorted(redundant_prefixes)
        ],
        "shadowing_count": len(shadowing),
        "shadowing": [
            {
                "general_pattern": general,
                "general_category": general_category,
                "specific_pattern": specific,
                "specific_category": specific_category,
            }
            for general, general_category, specific, specific_category in sorted(shadowing)
        ],
    }


def _build_drift_report(
    *,
    audits_dir: Path,
    llm_rows: list[dict[str, Any]],
    sku_lookup: dict[str, str],
    pn_patterns: list[dict[str, Any]],
    source_signature: str,
) -> tuple[Path, dict[str, Any]]:
    compiled_patterns: list[tuple[re.Pattern[str], str]] = []
    for item in pn_patterns:
        pattern = to_str(item.get("pattern"))
        category = normalize_category_key(item.get("category"))
        if not pattern or category not in _LOOKUP_ALLOWED_CATEGORIES:
            continue
        try:
            compiled_patterns.append((re.compile(pattern, re.IGNORECASE), category))
        except re.error:
            continue

    total_rows = 0
    changed_rows = 0
    for row in sorted(llm_rows, key=lambda item: (to_str(item.get("lot_id")), int(item.get("slice_rank", 0)), to_str(item.get("sku_code")))):
        old_category = normalize_category_key(row.get("category_engine"))
        sku = _normalize_sku_key(row.get("sku_code"))
        new_category = old_category
        if sku:
            mapped = sku_lookup.get(sku)
            if mapped in _LOOKUP_ALLOWED_CATEGORIES:
                new_category = mapped
            else:
                for regex, category in compiled_patterns:
                    if regex.search(sku):
                        new_category = category
                        break
        total_rows += 1
        if new_category != old_category:
            changed_rows += 1

    category_change_pct = round((100.0 * changed_rows / total_rows), 6) if total_rows > 0 else 0.0

    delta_path = audits_dir / "delta_from_baseline.csv"
    delta_rows: list[dict[str, Any]] = []
    if delta_path.exists():
        with delta_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                lot_id = to_str(row.get("lot_id"))
                baseline_rank = int(to_float(row.get("baseline_rank"), 0.0))
                current_rank = int(to_float(row.get("current_rank"), 0.0))
                delta_rank = int(to_float(row.get("delta_rank"), 0.0))
                delta_unknown_exposure = to_float(row.get("delta_unknown_exposure"), 0.0)
                delta_rows.append(
                    {
                        "lot_id": lot_id,
                        "baseline_rank": baseline_rank,
                        "current_rank": current_rank,
                        "delta_rank": delta_rank,
                        "delta_unknown_exposure": delta_unknown_exposure,
                    }
                )
    delta_rows.sort(key=lambda item: to_str(item.get("lot_id")))

    lots_total = len(delta_rows)
    lots_changed_unknown = sum(1 for row in delta_rows if abs(to_float(row.get("delta_unknown_exposure"), 0.0)) > 0.0)
    unknown_exposure_change_pct = round((100.0 * lots_changed_unknown / lots_total), 6) if lots_total > 0 else 0.0

    top_rank_changes = sorted(
        delta_rows,
        key=lambda row: (
            -abs(int(to_float(row.get("delta_rank"), 0.0))),
            to_str(row.get("lot_id")),
        ),
    )[:10]

    report = {
        "source_signature": source_signature,
        "category_change_pct": category_change_pct,
        "category_change_counts": {"changed": changed_rows, "total": total_rows},
        "unknown_exposure_change_pct": unknown_exposure_change_pct,
        "unknown_exposure_change_counts": {"changed": lots_changed_unknown, "total": lots_total},
        "top_rank_changes": top_rank_changes,
        "delta_source_found": delta_path.exists(),
    }
    report_path = audits_dir / "drift_report.json"
    _dump_json(report_path, report)
    return report_path, report


def _merge_sku_lookup(
    existing: dict[str, str],
    candidates: list[dict[str, Any]],
    *,
    overwrite_existing: bool,
) -> tuple[dict[str, str], dict[str, int]]:
    merged = dict(existing)
    added = 0
    updated = 0
    conflicts = 0
    skipped = 0
    for item in candidates:
        sku = _normalize_sku_key(item.get("sku"))
        category = normalize_category_key(item.get("category"))
        if not sku or category not in _LOOKUP_ALLOWED_CATEGORIES:
            skipped += 1
            continue
        current = merged.get(sku)
        if current is None:
            merged[sku] = category
            added += 1
            continue
        if current == category:
            skipped += 1
            continue
        if overwrite_existing:
            merged[sku] = category
            updated += 1
        else:
            conflicts += 1
    return merged, {"added": added, "updated": updated, "conflicts": conflicts, "skipped": skipped}


def _derive_pn_patterns(
    sku_lookup: dict[str, str],
    *,
    min_prefix_len: int,
    max_prefix_len: int,
    min_support: int,
    author: str,
    max_new_patterns: int,
) -> list[dict[str, Any]]:
    min_prefix_len = max(2, int(min_prefix_len))
    max_prefix_len = max(min_prefix_len, int(max_prefix_len))
    min_support = max(2, int(min_support))

    category_by_sku = {sku: category for sku, category in sku_lookup.items() if category in _LOOKUP_ALLOWED_CATEGORIES}
    if not category_by_sku:
        return []

    prefix_to_categories: dict[str, set[str]] = {}
    for sku, category in sorted(category_by_sku.items()):
        for length in range(min_prefix_len, min(max_prefix_len, len(sku)) + 1):
            prefix = sku[:length]
            prefix_to_categories.setdefault(prefix, set()).add(category)

    candidates: list[dict[str, Any]] = []
    for prefix in sorted(prefix_to_categories.keys()):
        cats = prefix_to_categories[prefix]
        if len(cats) != 1:
            continue
        category = next(iter(cats))
        support = sum(1 for sku, cat in category_by_sku.items() if cat == category and sku.startswith(prefix))
        if support < min_support:
            continue
        candidates.append(
            {
                "prefix": prefix,
                "category": category,
                "support": support,
                "pattern": f"^{prefix}[A-Z0-9]*$",
                "comment": f"auto-derived from sku_lookup; support={support}; prefix_len={len(prefix)}",
                "author": author,
            }
        )

    candidates.sort(key=lambda item: (-len(to_str(item.get("prefix"))), to_str(item.get("prefix")), to_str(item.get("category"))))

    # Keep only most specific non-redundant prefixes to avoid pattern explosion.
    selected: list[dict[str, Any]] = []
    for item in candidates:
        prefix = to_str(item.get("prefix"))
        category = to_str(item.get("category"))
        redundant = False
        for chosen in selected:
            chosen_prefix = to_str(chosen.get("prefix"))
            chosen_category = to_str(chosen.get("category"))
            if chosen_category == category and chosen_prefix.startswith(prefix):
                redundant = True
                break
        if not redundant:
            selected.append(item)

    if max_new_patterns > 0:
        selected = selected[: max(0, int(max_new_patterns))]
    return selected


def _merge_pn_patterns(
    existing_patterns: list[dict[str, Any]],
    derived_patterns: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    existing_by_pattern: dict[str, dict[str, Any]] = {}
    for item in existing_patterns:
        pattern = to_str(item.get("pattern"))
        if not pattern:
            continue
        existing_by_pattern[pattern] = dict(item)

    added = 0
    conflicts = 0
    for item in derived_patterns:
        pattern = to_str(item.get("pattern"))
        category = normalize_category_key(item.get("category"))
        if not pattern or category not in _LOOKUP_ALLOWED_CATEGORIES:
            continue
        current = existing_by_pattern.get(pattern)
        if current is None:
            existing_by_pattern[pattern] = {
                "pattern": pattern,
                "category": category,
                "comment": to_str(item.get("comment")),
                "author": to_str(item.get("author"), _DEFAULT_AUTHOR),
            }
            added += 1
            continue
        if normalize_category_key(current.get("category")) != category:
            conflicts += 1

    merged = sorted(
        existing_by_pattern.values(),
        key=lambda item: (-_fixed_prefix_length(to_str(item.get("pattern"))), to_str(item.get("pattern"))),
    )
    return merged, {"added": added, "conflicts": conflicts}


def _next_taxonomy_version(current: str, *, changed: bool) -> str:
    version = to_str(current, "v4.0-s1.0")
    if not changed:
        return version
    stage3_match = re.fullmatch(r"(.*-s3\.)(\d+)", version)
    if stage3_match:
        prefix, number = stage3_match.groups()
        return f"{prefix}{int(number) + 1}"
    base_match = re.fullmatch(r"(v\d+\.\d+).*", version)
    if base_match:
        return f"{base_match.group(1)}-s3.1"
    return f"{version}-s3.1"


def run_stage3_automation(
    *,
    input_path: Path | None,
    output_dir: Path,
    audits_dir: Path,
    save_baseline: bool,
    run_pipeline: bool,
    recompute_after_update: bool,
    overwrite_existing: bool,
    min_confidence: float,
    min_votes: int,
    min_prefix_len: int,
    max_prefix_len: int,
    min_prefix_support: int,
    max_new_patterns: int,
    max_new_sku_per_run: int,
    max_new_patterns_per_run: int,
    force_update: bool,
    author: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    audits_dir.mkdir(parents=True, exist_ok=True)

    if run_pipeline:
        if input_path is None or not input_path.exists():
            raise FileNotFoundError("input_path must exist when run_pipeline=True")
        run_full_ranking(input_path, output_dir, save_baseline=save_baseline)

    unknown_intelligence_path = audits_dir / "unknown_intelligence.csv"
    llm_results_path = audits_dir / "llm_audit_results.json"
    state_path = audits_dir / "stage3_state.json"
    summary_path = audits_dir / "stage3_automation_summary.json"

    source_signature = _compute_sources_signature(unknown_intelligence_path, llm_results_path)
    previous_state = _load_json_object(state_path, default={})
    previous_signature = to_str(previous_state.get("source_signature"))

    skip_reason = ""
    if not force_update and previous_signature and previous_signature == source_signature:
        skip_reason = "No new source data detected (source signature unchanged)."
    lock_active = _DEFAULT_TAXONOMY_LOCK_PATH.exists()
    if lock_active:
        skip_reason = "taxonomy_lock.json detected; dictionary updates are locked."

    sku_lookup = _load_json_object(_DEFAULT_SKU_LOOKUP_PATH, default={})
    normalized_lookup: dict[str, str] = {}
    for key, value in sku_lookup.items():
        sku = _normalize_sku_key(key)
        category = normalize_category_key(value)
        if sku and category in _LOOKUP_ALLOWED_CATEGORIES:
            normalized_lookup[sku] = category

    existing_patterns = _load_json_array(_DEFAULT_PN_PATTERNS_PATH)
    taxonomy = _load_json_object(_DEFAULT_TAXONOMY_VERSION_PATH, default={"version": "v4.0-s1.0"})

    target_unknown_pn = _read_unknown_intelligence(unknown_intelligence_path)
    llm_rows = _read_llm_rows(llm_results_path)

    candidates: list[dict[str, Any]] = []
    merged_lookup = dict(normalized_lookup)
    sku_stats = {"added": 0, "updated": 0, "conflicts": 0, "skipped": 0}
    merged_patterns = list(existing_patterns)
    pattern_stats = {"added": 0, "conflicts": 0}

    if not skip_reason:
        candidates = _collect_sku_candidates(
            llm_rows,
            target_unknown_pn=target_unknown_pn,
            min_confidence=min_confidence,
            min_votes=min_votes,
        )
        merged_lookup, sku_stats = _merge_sku_lookup(
            normalized_lookup,
            candidates,
            overwrite_existing=overwrite_existing,
        )
        derived_patterns = _derive_pn_patterns(
            merged_lookup,
            min_prefix_len=min_prefix_len,
            max_prefix_len=max_prefix_len,
            min_support=min_prefix_support,
            author=to_str(author, _DEFAULT_AUTHOR) or _DEFAULT_AUTHOR,
            max_new_patterns=max_new_patterns,
        )
        merged_patterns, pattern_stats = _merge_pn_patterns(existing_patterns, derived_patterns)

    guard_thresholds = {
        "max_new_sku_per_run": max(0, int(max_new_sku_per_run)),
        "max_new_patterns_per_run": max(0, int(max_new_patterns_per_run)),
    }
    guard_triggered = (
        int(sku_stats.get("added", 0)) > guard_thresholds["max_new_sku_per_run"]
        or int(pattern_stats.get("added", 0)) > guard_thresholds["max_new_patterns_per_run"]
    )

    lookup_changed = merged_lookup != normalized_lookup
    patterns_changed = merged_patterns != existing_patterns
    changed = lookup_changed or patterns_changed
    apply_updates = bool(changed and not skip_reason and not guard_triggered)

    if apply_updates:
        ordered_lookup = {key: merged_lookup[key] for key in sorted(merged_lookup.keys())}
        _dump_json(_DEFAULT_SKU_LOOKUP_PATH, ordered_lookup)
        _dump_json(_DEFAULT_PN_PATTERNS_PATH, merged_patterns)

    current_version = to_str(taxonomy.get("version"), "v4.0-s1.0")
    new_version = current_version
    if apply_updates:
        new_version = _next_taxonomy_version(current_version, changed=True)
        taxonomy_payload = {
            "version": new_version,
            "created_at": to_str(taxonomy.get("created_at"), "2026-02-24"),
            "sku_lookup_count": len(merged_lookup),
            "pn_patterns_count": len(merged_patterns),
            "stage3_source_signature": source_signature,
        }
        _dump_json(_DEFAULT_TAXONOMY_VERSION_PATH, taxonomy_payload)
        reload_taxonomy()

    recompute_ran = False
    if apply_updates and recompute_after_update:
        if input_path is None or not input_path.exists():
            raise FileNotFoundError("input_path must exist when recompute_after_update=True and dictionaries changed")
        run_full_ranking(input_path, output_dir, save_baseline=False)
        recompute_ran = True

    effective_lookup = merged_lookup if apply_updates else normalized_lookup
    effective_patterns = merged_patterns if apply_updates else existing_patterns
    pattern_safety = _pattern_safety_audit(effective_patterns)
    drift_report_path, drift_report = _build_drift_report(
        audits_dir=audits_dir,
        llm_rows=llm_rows,
        sku_lookup=effective_lookup,
        pn_patterns=effective_patterns,
        source_signature=source_signature,
    )

    if not lock_active and not guard_triggered:
        state_payload = {
            "source_signature": source_signature,
            "taxonomy_version": new_version,
            "lookup_count": len(effective_lookup),
            "patterns_count": len(effective_patterns),
        }
        _dump_json(state_path, state_payload)

    status = "completed"
    if lock_active:
        status = "locked"
    elif guard_triggered:
        status = "guard_triggered"
    elif skip_reason:
        status = "skipped"

    summary = {
        "status": status,
        "skip_reason": skip_reason,
        "input_path": str(input_path) if input_path is not None else "",
        "output_dir": str(output_dir),
        "audits_dir": str(audits_dir),
        "sources": {
            "unknown_intelligence_csv": str(unknown_intelligence_path),
            "llm_audit_results_json": str(llm_results_path),
            "source_signature": source_signature,
            "target_unknown_pn_count": len(target_unknown_pn),
            "llm_rows_count": len(llm_rows),
        },
        "updates": {
            "candidates_count": len(candidates),
            "sku_lookup": sku_stats,
            "pn_patterns": pattern_stats,
            "lookup_changed": lookup_changed,
            "patterns_changed": patterns_changed,
            "applied": apply_updates,
            "recompute_ran": recompute_ran,
        },
        "guardrails": {
            "taxonomy_lock_active": lock_active,
            "taxonomy_lock_path": str(_DEFAULT_TAXONOMY_LOCK_PATH),
            "dictionary_growth_guard_triggered": guard_triggered,
            "dictionary_growth_limits": guard_thresholds,
            "dictionary_growth_actual": {
                "new_sku": int(sku_stats.get("added", 0)),
                "new_patterns": int(pattern_stats.get("added", 0)),
            },
            "pattern_safety_audit": pattern_safety,
            "drift_report": drift_report,
        },
        "artifacts": {
            "sku_lookup_json": str(_DEFAULT_SKU_LOOKUP_PATH),
            "pn_patterns_json": str(_DEFAULT_PN_PATTERNS_PATH),
            "taxonomy_version_json": str(_DEFAULT_TAXONOMY_VERSION_PATH),
            "taxonomy_lock_json": str(_DEFAULT_TAXONOMY_LOCK_PATH),
            "drift_report_json": str(drift_report_path),
            "state_json": str(state_path),
            "summary_json": str(summary_path),
        },
    }
    _dump_json(summary_path, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 3 automation: deterministic DI dictionary updates.")
    parser.add_argument("--input", default="honeywell.xlsx", help="Path to source xlsx file.")
    parser.add_argument(
        "--output-dir",
        default="downloads",
        help="Directory where run_full_ranking outputs are generated.",
    )
    parser.add_argument(
        "--audits-dir",
        default="downloads/audits",
        help="Directory with unknown_intelligence.csv and llm_audit_results.json.",
    )
    parser.add_argument("--save-baseline", action="store_true", help="Pass --save-baseline to run_full_ranking pre-step.")
    parser.add_argument(
        "--run-pipeline",
        action="store_true",
        help="Run run_full_ranking before training/update step.",
    )
    parser.add_argument(
        "--recompute-after-update",
        action="store_true",
        help="Re-run run_full_ranking after dictionary updates are applied.",
    )
    parser.add_argument("--overwrite-existing", action="store_true", help="Allow replacing existing sku_lookup mappings.")
    parser.add_argument("--force-update", action="store_true", help="Update dictionaries even if source signature unchanged.")
    parser.add_argument("--min-confidence", type=float, default=0.85, help="Minimum LLM confidence for candidate selection.")
    parser.add_argument("--min-votes", type=int, default=2, help="Minimum supporting rows per sku candidate.")
    parser.add_argument("--min-prefix-len", type=int, default=5, help="Minimum prefix length for auto pn patterns.")
    parser.add_argument("--max-prefix-len", type=int, default=8, help="Maximum prefix length for auto pn patterns.")
    parser.add_argument("--min-prefix-support", type=int, default=3, help="Minimum sku support per derived prefix.")
    parser.add_argument("--max-new-patterns", type=int, default=25, help="Maximum number of derived pn patterns per run.")
    parser.add_argument("--max-new-sku-per-run", type=int, default=100, help="Guardrail limit for new sku_lookup rows per run.")
    parser.add_argument(
        "--max-new-patterns-per-run",
        type=int,
        default=50,
        help="Guardrail limit for newly added pn_patterns per run.",
    )
    parser.add_argument("--author", default=_DEFAULT_AUTHOR, help="Author tag written into derived pn patterns.")
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else None
    output_dir = Path(args.output_dir)
    audits_dir = Path(args.audits_dir)

    summary = run_stage3_automation(
        input_path=input_path,
        output_dir=output_dir,
        audits_dir=audits_dir,
        save_baseline=bool(args.save_baseline),
        run_pipeline=bool(args.run_pipeline),
        recompute_after_update=bool(args.recompute_after_update),
        overwrite_existing=bool(args.overwrite_existing),
        min_confidence=to_float(args.min_confidence, 0.85),
        min_votes=max(1, int(args.min_votes)),
        min_prefix_len=max(2, int(args.min_prefix_len)),
        max_prefix_len=max(2, int(args.max_prefix_len)),
        min_prefix_support=max(2, int(args.min_prefix_support)),
        max_new_patterns=max(0, int(args.max_new_patterns)),
        max_new_sku_per_run=max(0, int(args.max_new_sku_per_run)),
        max_new_patterns_per_run=max(0, int(args.max_new_patterns_per_run)),
        force_update=bool(args.force_update),
        author=to_str(args.author, _DEFAULT_AUTHOR) or _DEFAULT_AUTHOR,
    )
    print("===STAGE3_AUTOMATION_SUMMARY_START===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("===STAGE3_AUTOMATION_SUMMARY_END===")


if __name__ == "__main__":
    main()
