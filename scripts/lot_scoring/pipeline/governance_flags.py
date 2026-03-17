from __future__ import annotations

from typing import Any

from scripts.lot_scoring.governance_config import GovernanceConfig
from scripts.lot_scoring.pipeline.helpers import to_float


def is_hvl(total_effective_usd: float, gov_config: GovernanceConfig) -> bool:
    return to_float(total_effective_usd, 0.0) >= gov_config.HVL_THRESHOLD_USD


def compute_governance_flags(
    *,
    lot: Any,
    metadata: dict[str, float | int],
    v4_scalars: dict[str, Any],
    gov_config: GovernanceConfig,
) -> list[str]:
    flags: list[str] = []

    total_effective_usd = to_float(metadata.get("total_effective_usd"), 0.0)
    core_count = max(0, int(metadata.get("core_count", 0)))
    tail_count = max(0, int(metadata.get("tail_count", 0)))
    total_lines = max(1, core_count + tail_count)
    avg_unit_price_usd = total_effective_usd / total_lines

    unknown_exposure = to_float(v4_scalars.get("unknown_exposure"), to_float(getattr(lot, "unknown_exposure", 0.0), 0.0))
    hhi_index = to_float(v4_scalars.get("hhi_index"), to_float(getattr(lot, "hhi_index", 1.0), 1.0))

    if is_hvl(total_effective_usd, gov_config):
        flags.append("HVL")
    if avg_unit_price_usd < gov_config.UNIT_PRICE_FLOOR_USD:
        flags.append("UNIT_PRICE_LOW")
    if avg_unit_price_usd > gov_config.UNIT_PRICE_CEIL_USD:
        flags.append("UNIT_PRICE_HIGH")
    if unknown_exposure >= gov_config.UNKNOWN_ALERT_THRESH:
        flags.append("UNKNOWN_HIGH")
    if hhi_index >= gov_config.HHI_ALERT_THRESH:
        flags.append("HHI_HIGH")
    if total_effective_usd >= gov_config.VALUE_OUTLIER_USD_CEIL:
        flags.append("VALUE_OUTLIER")

    return flags
