from __future__ import annotations

from dataclasses import dataclass

from scripts.lot_scoring.pipeline.helpers import clamp, normalize_category_key, to_float


@dataclass(frozen=True)
class CapitalMapResult:
    analyzed_value_usd: float
    analyzed_share_of_core: float
    distribution: dict[str, float]
    top_categories: list[tuple[str, float]]
    flags: list[str]


def compute_capital_map(
    analyzed_skus: list[dict],
    total_core_value_usd: float,
    top_k: int = 5,
) -> CapitalMapResult:
    value_by_category: dict[str, float] = {}
    for sku in analyzed_skus:
        line_value = to_float(sku.get("effective_line_usd"), 0.0)
        if line_value <= 0.0:
            continue
        cat = normalize_category_key(sku.get("category"))
        value_by_category[cat] = value_by_category.get(cat, 0.0) + line_value

    analyzed_value_usd = sum(value_by_category.values())

    if analyzed_value_usd <= 0.0 or total_core_value_usd <= 0.0:
        return CapitalMapResult(
            analyzed_value_usd=0.0,
            analyzed_share_of_core=0.0,
            distribution={"unknown": 1.0},
            top_categories=[("unknown", 1.0)],
            flags=["CAPITAL_MAP:ZERO_VALUE"],
        )

    analyzed_share_of_core = clamp(analyzed_value_usd / total_core_value_usd, 0.0, 1.0)
    distribution = {cat: val / analyzed_value_usd for cat, val in value_by_category.items()}

    sorted_cats = sorted(
        distribution.items(),
        key=lambda pair: (-pair[1], pair[0]),
    )

    top_categories: list[tuple[str, float]] = []
    if len(sorted_cats) <= top_k:
        top_categories = list(sorted_cats)
    else:
        top_categories = list(sorted_cats[:top_k])
        other_share = sum(share for _, share in sorted_cats[top_k:])
        top_categories.append(("OTHER", other_share))

    flags: list[str] = []
    if len(sorted_cats) >= 1 and sorted_cats[0][1] >= 0.90:
        flags.append("CAPITAL_MAP:SINGLE_CATEGORY")

    return CapitalMapResult(
        analyzed_value_usd=analyzed_value_usd,
        analyzed_share_of_core=analyzed_share_of_core,
        distribution=distribution,
        top_categories=top_categories,
        flags=flags,
    )
