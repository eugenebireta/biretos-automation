from __future__ import annotations

from scripts.lot_scoring.pipeline.helpers import normalize_category_key, to_float, to_str


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = to_str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "t"}:
        return True
    if text in {"0", "false", "no", "n", "f", ""}:
        return False
    return bool(value)


def classify_skus(raw_skus: list[dict]) -> list[dict]:
    prepared: list[dict] = []
    for idx, original in enumerate(raw_skus, start=1):
        sku = dict(original)
        sku.setdefault("row_index", idx)

        is_fake = _to_bool(sku.get("is_fake"))
        sku["is_fake"] = is_fake

        raw_qty = max(0.0, to_float(sku.get("raw_qty"), 0.0))
        sku["raw_qty"] = raw_qty
        sku["qty"] = raw_qty
        sku["q_has_qty"] = raw_qty > 0.0

        category = normalize_category_key(sku.get("category"))
        sku["category"] = category if category else "unknown"
        sku["brand"] = to_str(sku.get("brand"), "unknown").lower() or "unknown"

        if is_fake:
            sku["category"] = "toxic_fake"
            sku["effective_line_usd"] = 0.0
            sku["qty"] = 0.0
            sku["q_has_qty"] = False
            sku["is_in_core_slice"] = False

        prepared.append(sku)
    return prepared

