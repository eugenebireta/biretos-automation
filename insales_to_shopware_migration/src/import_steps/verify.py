from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from import_steps import ProductImportState, StepState

ROOT = Path(__file__).resolve().parents[2]


def run(
    client: Any,
    registry: Any,
    snapshot_product: Dict[str, Any],
    state: ProductImportState,
    context: Dict[str, Any],
) -> ProductImportState:
    dry_run: bool = context.get("dry_run", True)
    if dry_run:
        state.set_step("verify", StepState.SUCCESS, "Dry-run: РІРµСЂРёС„РёРєР°С†РёСЏ РїСЂРѕРїСѓС‰РµРЅР°")
        return state

    if not state.sku:
        state.set_step("verify", StepState.ERROR, "SKU РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚ РґР»СЏ verify_product_state")
        return state

    script_path = ROOT / "src" / "verify_product_state.py"
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), state.sku],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            state.set_step("verify", StepState.SUCCESS, "verify_product_state OK")
        else:
            message = result.stdout.strip() or result.stderr.strip() or "verify_product_state FAIL"
            state.set_step("verify", StepState.ERROR, message)
    except Exception as exc:
        state.set_step("verify", StepState.ERROR, f"РћС€РёР±РєР° Р·Р°РїСѓСЃРєР° verify_product_state: {exc}")

    return state
