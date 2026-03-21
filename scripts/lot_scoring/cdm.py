from dataclasses import dataclass, field


@dataclass
class LotRecord:
    lot_id: str
    s1: float = 0.0
    s2: float = 0.0
    s3: float = 0.0
    s4: float = 0.0
    base_score: float = 0.0
    final_score: float = 0.0
    score_10: float = 0.0
    hhi_index: float = 1.0
    tail_liability_usd: float = 0.0
    tail_distinct_sku_count: int = 0
    penny_line_ratio: float = 1.0
    core_distinct_sku_count: int = 0
    m_hustle: float = 1.0
    m_concentration: float = 1.0
    m_tail: float = 1.0
    m_liquidity_floor: float = 1.0
    m_obsolescence_floor: float = 1.0
    unknown_exposure: float = 0.0
    unknown_exposure_usd: float = 0.0
    flags: list[str] = field(default_factory=list)
    rank: int = 0


@dataclass
class ExplanationCard:
    lot_id: str
    final_score: float = 0.0
    score_10: float = 0.0
    multipliers_breakdown: dict = field(default_factory=dict)
    top_plus: list[str] = field(default_factory=list)
    top_minus: list[str] = field(default_factory=list)
