from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EtlConfig:
    CONDITION_FLOOR: float = 0.30
    QTY_CAP_PERCENTILE: float = 95.0
    QTY_CAP_MULTIPLIER: float = 3.0
    QTY_CAP_FLOOR: float = 100.0
    CORE_MIN_VALUE_RATIO: float = 0.70
    CORE_MAX_VALUE_RATIO: float = 0.85
    CORE_BUFFER_ITEMS: int = 3
    GAP_MULTIPLIER: float = 2.0
    GAP_MIN_ITEMS: int = 10

    def __post_init__(self) -> None:
        if not (0.0 < self.CONDITION_FLOOR <= 1.0):
            raise ValueError("CONDITION_FLOOR must be in (0, 1].")
        if not (0.0 < self.QTY_CAP_PERCENTILE <= 100.0):
            raise ValueError("QTY_CAP_PERCENTILE must be in (0, 100].")
        if self.QTY_CAP_MULTIPLIER <= 0.0:
            raise ValueError("QTY_CAP_MULTIPLIER must be > 0.")
        if self.QTY_CAP_FLOOR < 0.0:
            raise ValueError("QTY_CAP_FLOOR must be >= 0.")
        if not (0.0 < self.CORE_MIN_VALUE_RATIO <= 1.0):
            raise ValueError("CORE_MIN_VALUE_RATIO must be in (0, 1].")
        if not (0.0 < self.CORE_MAX_VALUE_RATIO <= 1.0):
            raise ValueError("CORE_MAX_VALUE_RATIO must be in (0, 1].")
        if self.CORE_MAX_VALUE_RATIO < self.CORE_MIN_VALUE_RATIO:
            raise ValueError("CORE_MAX_VALUE_RATIO must be >= CORE_MIN_VALUE_RATIO.")
        if self.CORE_BUFFER_ITEMS < 0:
            raise ValueError("CORE_BUFFER_ITEMS must be >= 0.")
        if self.GAP_MULTIPLIER <= 0.0:
            raise ValueError("GAP_MULTIPLIER must be > 0.")
        if self.GAP_MIN_ITEMS < 2:
            raise ValueError("GAP_MIN_ITEMS must be >= 2.")

