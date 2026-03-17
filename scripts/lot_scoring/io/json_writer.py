from scripts.lot_scoring.cdm import LotRecord


def lots_to_json_rows(lots: list[LotRecord]) -> list[dict]:
    rows: list[dict] = []
    for lot in lots:
        multipliers_breakdown = {
            "m_hustle": lot.m_hustle,
            "m_concentration": lot.m_concentration,
            "m_tail": lot.m_tail,
            "m_liquidity_floor": lot.m_liquidity_floor,
            "m_obsolescence_floor": lot.m_obsolescence_floor,
            "combined_multiplier": (
                lot.m_hustle
                * lot.m_concentration
                * lot.m_tail
                * lot.m_liquidity_floor
                * lot.m_obsolescence_floor
            ),
        }
        rows.append(
            {
                "lot_id": lot.lot_id,
                "rank": lot.rank,
                "score_10": lot.score_10,
                "final_score": lot.final_score,
                "base_score": lot.base_score,
                "s1": lot.s1,
                "s2": lot.s2,
                "s3": lot.s3,
                "s4": lot.s4,
                "hhi_index": lot.hhi_index,
                "tail_liability_usd": lot.tail_liability_usd,
                "penny_line_ratio": lot.penny_line_ratio,
                "core_distinct_sku_count": lot.core_distinct_sku_count,
                "tail_distinct_sku_count": lot.tail_distinct_sku_count,
                "multipliers_breakdown": multipliers_breakdown,
                "flags": list(lot.flags),
            }
        )
    return rows
