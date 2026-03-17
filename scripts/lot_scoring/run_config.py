from dataclasses import dataclass


@dataclass(frozen=True)
class RunConfig:
    SCORE_GAMMA: float = 0.85
    SCORE_PRECISION: int = 6
    DEAL_FLOOR: float = 100.0
    DEAL_CEIL: float = 5000.0
    VD_FLOOR: float = 50.0
    VD_CEIL: float = 5000.0
    PENNY_THRESH: float = 50.0
    FRAG_LOW: int = 10
    FRAG_HIGH: int = 50
    HUSTLE_W_PENNY: float = 0.60
    HUSTLE_W_FRAG: float = 0.30
    HUSTLE_FLOOR: float = 0.10
    HHI_SAFE: float = 0.25
    CONC_K: float = 1.50
    CONC_FLOOR: float = 0.50
    BASE_HANDLING_PER_SKU: float = 3.00
    TAIL_FLOOR: float = 0.70
    TAIL_UNKNOWN_DEFAULT_USD: float = 10.0
    LIQUIDITY_KILL_THRESH: float = 0.10
    LIQUIDITY_KILL_MULT: float = 0.20
    OBSOLESCENCE_KILL_THRESH: float = 0.10
    OBSOLESCENCE_KILL_MULT: float = 0.30
    TAIL_HANDLING_COST_FILE: str = "data/tail_handling_cost.json"

    def __post_init__(self) -> None:
        if not (0 < self.SCORE_GAMMA <= 1.0):
            raise ValueError("SCORE_GAMMA must be in (0, 1].")
        if self.SCORE_PRECISION < 0:
            raise ValueError("SCORE_PRECISION must be >= 0.")
        if not (0 < self.DEAL_FLOOR < self.DEAL_CEIL):
            raise ValueError("DEAL_FLOOR/DEAL_CEIL must satisfy 0 < DEAL_FLOOR < DEAL_CEIL.")
        if not (0 < self.VD_FLOOR < self.VD_CEIL):
            raise ValueError("VD_FLOOR/VD_CEIL must satisfy 0 < VD_FLOOR < VD_CEIL.")
        if self.PENNY_THRESH < 0:
            raise ValueError("PENNY_THRESH must be >= 0.")
        if not (0 <= self.FRAG_LOW < self.FRAG_HIGH):
            raise ValueError("FRAG_LOW/FRAG_HIGH must satisfy 0 <= FRAG_LOW < FRAG_HIGH.")
        if not (0 <= self.HUSTLE_W_PENNY <= 1):
            raise ValueError("HUSTLE_W_PENNY must be in [0, 1].")
        if not (0 <= self.HUSTLE_W_FRAG <= 1):
            raise ValueError("HUSTLE_W_FRAG must be in [0, 1].")
        if not (0 <= self.HUSTLE_FLOOR <= 1):
            raise ValueError("HUSTLE_FLOOR must be in [0, 1].")
        if not (0 <= self.HHI_SAFE <= 1):
            raise ValueError("HHI_SAFE must be in [0, 1].")
        if self.CONC_K < 0:
            raise ValueError("CONC_K must be >= 0.")
        if not (0 <= self.CONC_FLOOR <= 1):
            raise ValueError("CONC_FLOOR must be in [0, 1].")
        if self.BASE_HANDLING_PER_SKU < 0:
            raise ValueError("BASE_HANDLING_PER_SKU must be >= 0.")
        if not (0 <= self.TAIL_FLOOR <= 1):
            raise ValueError("TAIL_FLOOR must be in [0, 1].")
        if self.TAIL_UNKNOWN_DEFAULT_USD < 0:
            raise ValueError("TAIL_UNKNOWN_DEFAULT_USD must be >= 0.")
        if not (0 <= self.LIQUIDITY_KILL_THRESH <= 1):
            raise ValueError("LIQUIDITY_KILL_THRESH must be in [0, 1].")
        if not (0 <= self.LIQUIDITY_KILL_MULT <= 1):
            raise ValueError("LIQUIDITY_KILL_MULT must be in [0, 1].")
        if not (0 <= self.OBSOLESCENCE_KILL_THRESH <= 1):
            raise ValueError("OBSOLESCENCE_KILL_THRESH must be in [0, 1].")
        if not (0 <= self.OBSOLESCENCE_KILL_MULT <= 1):
            raise ValueError("OBSOLESCENCE_KILL_MULT must be in [0, 1].")
        if not self.TAIL_HANDLING_COST_FILE.strip():
            raise ValueError("TAIL_HANDLING_COST_FILE must be a non-empty path.")
