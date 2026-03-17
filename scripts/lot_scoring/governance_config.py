from dataclasses import dataclass


@dataclass(frozen=True)
class GovernanceConfig:
    HVL_THRESHOLD_USD: float = 500.0
    HVL_POLICY_NOTE: str = "USD-only. Approved 2026-02-24. Not derived from RUB."
    UNIT_PRICE_FLOOR_USD: float = 0.50
    UNIT_PRICE_CEIL_USD: float = 50_000.0
    UNKNOWN_ALERT_THRESH: float = 0.40
    HHI_ALERT_THRESH: float = 0.60
    ZONE_PASS_THRESH: float = 60.0
    ZONE_REVIEW_THRESH: float = 35.0
    VALUE_OUTLIER_USD_CEIL: float = 10_000_000.0
    GOVERNANCE_VERSION: str = "v4.1.0"

    def __post_init__(self) -> None:
        if self.HVL_THRESHOLD_USD <= 0:
            raise ValueError("HVL_THRESHOLD_USD must be > 0.")
        if self.UNIT_PRICE_FLOOR_USD <= 0:
            raise ValueError("UNIT_PRICE_FLOOR_USD must be > 0.")
        if self.UNIT_PRICE_FLOOR_USD >= self.UNIT_PRICE_CEIL_USD:
            raise ValueError("UNIT_PRICE_FLOOR_USD must be < UNIT_PRICE_CEIL_USD.")
        if not (0 < self.UNKNOWN_ALERT_THRESH <= 1):
            raise ValueError("UNKNOWN_ALERT_THRESH must be in (0, 1].")
        if not (0 < self.HHI_ALERT_THRESH <= 1):
            raise ValueError("HHI_ALERT_THRESH must be in (0, 1].")
        if self.ZONE_REVIEW_THRESH <= 0:
            raise ValueError("ZONE_REVIEW_THRESH must be > 0.")
        if self.ZONE_PASS_THRESH <= self.ZONE_REVIEW_THRESH:
            raise ValueError("ZONE_PASS_THRESH must be > ZONE_REVIEW_THRESH.")
        if self.VALUE_OUTLIER_USD_CEIL <= 0:
            raise ValueError("VALUE_OUTLIER_USD_CEIL must be > 0.")
        if not self.GOVERNANCE_VERSION.strip():
            raise ValueError("GOVERNANCE_VERSION must be a non-empty string.")
