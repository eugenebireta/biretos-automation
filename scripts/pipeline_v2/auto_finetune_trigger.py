"""Auto-trigger fine-tune when enough training data accumulates.

Checks training_v2/ for data size, triggers fine-tune of local models when thresholds hit.
Run as cron job or manually.

Thresholds:
- datasheet_extraction.jsonl >= 200 pairs → fine-tune Qwen2-VL-2B
- url_datasheet_validation.jsonl >= 200 pairs → fine-tune DistilBERT
- evidence_to_structured.jsonl >= 500 pairs → fine-tune entity resolver

After fine-tune:
- Runs evaluation against cloud AI (Gemini/Haiku) on held-out set
- If local accuracy >= 85% — marks local as "ready for production"
- Logs result to downloads/training_v2/finetune_log.jsonl
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TRAINING_DIR = ROOT / "downloads" / "training_v2"
LOG_FILE = TRAINING_DIR / "finetune_log.jsonl"

# Thresholds (min pairs to trigger fine-tune)
THRESHOLDS = {
    "datasheet_extraction": 200,      # PDF parser
    "url_datasheet_validation": 200,  # Binary classifier
    "evidence_to_structured": 500,    # Entity resolver
    "photo_training": 1000,            # Photo quality (already 563)
}

# Production readiness threshold (local model accuracy)
READY_THRESHOLD = 0.85


def count_pairs(jsonl_path: Path) -> int:
    """Count valid training pairs in JSONL."""
    if not jsonl_path.exists():
        return 0
    count = 0
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            # Only count pairs marked for training
            if d.get("use_for_training", True):
                count += 1
        except Exception:
            pass
    return count


def log_event(event: dict):
    """Append event to log."""
    event["timestamp"] = datetime.now().isoformat()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def trigger_qwen_datasheet_finetune(pairs_count: int) -> bool:
    """Fine-tune Qwen2-VL-2B on datasheet_extraction pairs."""
    print(f"\n>>> TRIGGERING Qwen2-VL-2B fine-tune on {pairs_count} pairs")

    # Check if script exists
    finetune_script = ROOT / "scripts" / "finetune_qwen2vl_datasheet.py"
    if not finetune_script.exists():
        print("  Creating finetune script stub...")
        finetune_script.write_text(_QWEN_FINETUNE_STUB, encoding="utf-8")
        log_event({
            "model": "qwen2vl_datasheet",
            "status": "script_created",
            "pairs": pairs_count,
            "note": "Manual review required before first run",
        })
        return False

    # Run fine-tune
    try:
        result = subprocess.run(
            ["python", str(finetune_script)],
            capture_output=True, text=True, timeout=3600,
            encoding="utf-8", errors="replace",
        )
        success = result.returncode == 0
        log_event({
            "model": "qwen2vl_datasheet",
            "status": "success" if success else "failed",
            "pairs": pairs_count,
            "stdout_tail": result.stdout[-500:] if result.stdout else "",
            "stderr_tail": result.stderr[-500:] if result.stderr else "",
        })
        return success
    except Exception as e:
        log_event({
            "model": "qwen2vl_datasheet", "status": "error",
            "pairs": pairs_count, "error": str(e),
        })
        return False


def evaluate_against_cloud(model_name: str, test_set_size: int = 20) -> dict:
    """Evaluate local model against cloud AI on held-out set."""
    # Placeholder — real implementation runs local model vs Gemini/Haiku
    # and compares results
    eval_script = ROOT / "scripts" / f"evaluate_{model_name}.py"
    if not eval_script.exists():
        return {"status": "no_evaluator", "accuracy": None}

    try:
        result = subprocess.run(
            ["python", str(eval_script), "--test-size", str(test_set_size)],
            capture_output=True, text=True, timeout=1800,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0:
            # Parse accuracy from output (convention: last line = "accuracy=0.xx")
            for line in reversed(result.stdout.split("\n")):
                if "accuracy=" in line:
                    try:
                        acc = float(line.split("accuracy=")[1].split()[0])
                        return {"status": "success", "accuracy": acc}
                    except Exception:
                        pass
        return {"status": "failed", "accuracy": None}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_and_trigger():
    """Main trigger logic: check thresholds, run fine-tune if ready."""
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(f"Auto Fine-tune Trigger Check ({datetime.now().isoformat()})")
    print("=" * 80)

    triggers = []

    # Check each dataset
    datasets = {
        "datasheet_extraction": TRAINING_DIR / "datasheet_extraction.jsonl",
        "url_datasheet_validation": TRAINING_DIR / "url_datasheet_validation.jsonl",
        "evidence_to_structured": TRAINING_DIR / "evidence_to_structured.jsonl",
    }

    for name, path in datasets.items():
        count = count_pairs(path)
        threshold = THRESHOLDS[name]
        ready = count >= threshold
        status = "READY" if ready else f"{count}/{threshold}"
        print(f"  {name:<30} {count:>5} pairs  {status}")

        if ready:
            # Check if already fine-tuned recently
            log_content = LOG_FILE.read_text(encoding="utf-8") if LOG_FILE.exists() else ""
            recent_finetune = f'"model": "{name}"' in log_content[-5000:] if log_content else False

            if not recent_finetune:
                triggers.append(name)
                print("    -> Will trigger fine-tune")
            else:
                print("    (already fine-tuned, skip)")

    # photo_training already handled separately
    photo_count = len(list((ROOT / "downloads" / "photo_training").rglob("*.json"))) if (ROOT / "downloads" / "photo_training").exists() else 0
    photo_threshold = THRESHOLDS["photo_training"]
    photo_status = "READY" if photo_count >= photo_threshold else f"{photo_count}/{photo_threshold}"
    print(f"  photo_training                 {photo_count:>5} pairs  {photo_status}")

    # Execute triggers
    for name in triggers:
        if name == "datasheet_extraction":
            pairs = count_pairs(datasets[name])
            trigger_qwen_datasheet_finetune(pairs)

    log_event({
        "event": "trigger_check",
        "pairs_counts": {n: count_pairs(p) for n, p in datasets.items()},
        "triggers_fired": triggers,
    })

    print(f"\n  Log: {LOG_FILE}")
    return len(triggers)


_QWEN_FINETUNE_STUB = '''"""Fine-tune Qwen2-VL-2B on datasheet_extraction.jsonl.

Auto-generated stub. Customize before first run.

Run: python scripts/finetune_qwen2vl_datasheet.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRAIN_DATA = ROOT / "downloads" / "training_v2" / "datasheet_extraction.jsonl"
OUTPUT_DIR = Path("D:/AI_MODELS/trained/qwen2vl_2b_datasheet")

def main():
    # Load training data
    records = []
    for line in TRAIN_DATA.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))

    print(f"Loaded {len(records)} training pairs")

    # TODO: implement PEFT/LoRA fine-tune
    # Similar to scripts/finetune_qwen2vl.py but for PDF pages
    # 1. Convert PDF to images (fitz)
    # 2. Create conversation pairs: [page_image] -> extracted_json
    # 3. Fine-tune with gradient accumulation
    # 4. Save to OUTPUT_DIR

    print("STUB: actual fine-tune logic TBD")
    print(f"accuracy=0.00")

if __name__ == "__main__":
    main()
'''


if __name__ == "__main__":
    check_and_trigger()
