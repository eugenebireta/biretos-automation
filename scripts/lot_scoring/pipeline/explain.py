from scripts.lot_scoring.cdm import ExplanationCard, LotRecord


def build_explanation_card(lot: LotRecord) -> ExplanationCard:
    combined = (
        lot.m_hustle
        * lot.m_concentration
        * lot.m_tail
        * lot.m_liquidity_floor
        * lot.m_obsolescence_floor
    )
    card = ExplanationCard(
        lot_id=lot.lot_id,
        final_score=lot.final_score,
        score_10=lot.score_10,
        multipliers_breakdown={
            "m_hustle": lot.m_hustle,
            "m_concentration": lot.m_concentration,
            "m_tail": lot.m_tail,
            "m_liquidity_floor": lot.m_liquidity_floor,
            "m_obsolescence_floor": lot.m_obsolescence_floor,
            "combined_multiplier": combined,
        },
    )
    if lot.m_hustle < 1.0:
        card.top_minus.append(f"hustle_penalty:{lot.m_hustle:.3f}")
    if lot.m_concentration < 1.0:
        card.top_minus.append(f"concentration_penalty:{lot.m_concentration:.3f}")
    if lot.m_tail < 1.0:
        card.top_minus.append(f"tail_penalty:{lot.m_tail:.3f}")
    if lot.m_liquidity_floor < 1.0:
        card.top_minus.append(f"liquidity_kill:{lot.m_liquidity_floor:.3f}")
    if lot.m_obsolescence_floor < 1.0:
        card.top_minus.append(f"obsolescence_kill:{lot.m_obsolescence_floor:.3f}")
    return card
