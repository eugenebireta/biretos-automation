"""ETL package for lot scoring v3.4.1."""

from scripts.lot_scoring.etl.assemble import AssembledLot, ETLInvariantError, assemble_for_scoring
from scripts.lot_scoring.etl.classify import classify_skus
from scripts.lot_scoring.etl.condition import apply_condition_floor
from scripts.lot_scoring.etl.core_slicer import apply_adaptive_core_slice
from scripts.lot_scoring.etl.etl_config import EtlConfig
from scripts.lot_scoring.etl.volume_sanitize import apply_qty_cap


def run_etl_pipeline(raw_skus: list[dict], config: EtlConfig | None = None) -> AssembledLot:
    cfg = config or EtlConfig()
    skus = classify_skus(raw_skus)
    skus = apply_condition_floor(skus, cfg)
    skus, qty_cap = apply_qty_cap(skus, cfg)
    skus = apply_adaptive_core_slice(skus, cfg)
    return assemble_for_scoring(skus, qty_cap=qty_cap, config=cfg)


