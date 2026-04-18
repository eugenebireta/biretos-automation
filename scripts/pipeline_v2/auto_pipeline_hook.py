"""Pipeline hook: auto-check fine-tune trigger after every enrichment run.

Add this call at the end of any enrichment script:
    from scripts.pipeline_v2.auto_pipeline_hook import post_run_hook
    post_run_hook()

It will:
1. Rebuild training data from latest evidence
2. Check if any thresholds hit
3. Auto-trigger fine-tune if ready
4. Send Telegram notification to owner
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def post_run_hook(silent: bool = False):
    """Run after enrichment pipeline. Returns dict with status."""
    from scripts.pipeline_v2._build_training_data import build_datasheet_training, build_url_validation_training, build_evidence_training
    from scripts.pipeline_v2.auto_finetune_trigger import check_and_trigger
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent.parent
    ROOT / "downloads" / "training_v2"

    # Rebuild training data
    try:
        c1 = build_datasheet_training()
        c2 = build_url_validation_training()
        c3 = build_evidence_training()
    except Exception as e:
        if not silent:
            print(f"Training data build failed: {e}")
        return {"status": "build_failed", "error": str(e)}

    if not silent:
        print(f"Training data updated: datasheet={c1}, url_val={c2}, evidence={c3}")

    # Check triggers
    try:
        triggers_fired = check_and_trigger()
    except Exception as e:
        if not silent:
            print(f"Trigger check failed: {e}")
        return {"status": "trigger_failed", "error": str(e)}

    result = {
        "status": "ok",
        "training_pairs": {
            "datasheet_extraction": c1,
            "url_datasheet_validation": c2,
            "evidence_to_structured": c3,
        },
        "triggers_fired": triggers_fired,
    }

    # Notify owner if fine-tune started
    if triggers_fired > 0:
        try:
            _notify_owner(f"Auto fine-tune triggered: {triggers_fired} models")
        except Exception:
            pass

    return result


def _notify_owner(message: str):
    """Send Telegram notification."""
    try:
        import requests
        from scripts.app_secrets import get_secret
        token = get_secret("TELEGRAM_BOT_TOKEN")
        chat_id = get_secret("TELEGRAM_OWNER_CHAT_ID")
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": f"[Pipeline v2] {message}"},
            timeout=5,
        )
    except Exception:
        pass


if __name__ == "__main__":
    result = post_run_hook()
    print(f"\nResult: {result}")
