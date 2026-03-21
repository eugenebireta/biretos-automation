import json

from scripts.lot_scoring.run_full_ranking_v341 import (
    _build_abs_score_validation_payload,
    _compute_abs_score_100_from_row,
)


def _row(lot_id: str, *, s1: float, s2: float, s4: float, unknown_exposure: float, m_concentration: float) -> dict:
    return {
        "lot_id": lot_id,
        "S1": s1,
        "S2": s2,
        "S4": s4,
        "unknown_exposure": unknown_exposure,
        "M_concentration": m_concentration,
    }


def test_abs_score_order_invariance_for_reordered_lots():
    rows = [
        _row("10", s1=0.90, s2=0.80, s4=0.70, unknown_exposure=0.10, m_concentration=0.95),
        _row("11", s1=0.50, s2=0.60, s4=0.40, unknown_exposure=0.35, m_concentration=0.85),
        _row("12", s1=0.30, s2=1.00, s4=0.20, unknown_exposure=0.05, m_concentration=1.00),
    ]
    baseline = {row["lot_id"]: _compute_abs_score_100_from_row(row) for row in rows}
    reordered = {row["lot_id"]: _compute_abs_score_100_from_row(row) for row in reversed(rows)}
    assert baseline == reordered


def test_abs_score_single_lot_consistency_and_validation_payload():
    rows = [
        _row("10", s1=0.75, s2=0.65, s4=0.45, unknown_exposure=0.20, m_concentration=0.90),
        _row("20", s1=0.55, s2=0.35, s4=0.25, unknown_exposure=0.30, m_concentration=0.80),
    ]
    payload = _build_abs_score_validation_payload(rows)
    assert payload["checks"]["order_invariance"] is True
    assert payload["checks"]["single_lot_invariance"] is True

    single = _compute_abs_score_100_from_row(rows[0])
    with_neighbor = _compute_abs_score_100_from_row(rows[0])
    assert single == with_neighbor

    # Payload must stay JSON-serializable for audits/abs_score_validation.json.
    json.dumps(payload, ensure_ascii=False)
