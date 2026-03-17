import json
import time
from pathlib import Path

from scripts.lot_scoring.cdm import LotRecord


def _debug_log(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    # region agent log
    payload = {
        "sessionId": "2eec37",
        "runId": "pre-fix",
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    log_path = Path(__file__).resolve().parents[3] / "debug-2eec37.log"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    # endregion


def render_console_table(lots: list[LotRecord]) -> str:
    lines: list[str] = []
    lines.append("Rank | Lot | Score10 | Final(0-1) | Base | M_hust | M_conc | M_tail | Flags")
    _debug_log(
        "H1",
        "io/console_writer.py:render_console_table",
        "Console header generated",
        {"header": lines[0], "column_count": len([segment.strip() for segment in lines[0].split(\"|\")])},
    )
    for lot in lots:
        flags = ",".join(lot.flags)
        lines.append(
            f"{lot.rank} | {lot.lot_id} | {lot.score_10:.2f} | {lot.final_score:.6f} | "
            f"{lot.base_score:.6f} | {lot.m_hustle:.4f} | {lot.m_concentration:.4f} | {lot.m_tail:.4f} | {flags}"
        )
    return "\n".join(lines)
