import json
import os
import sys
from pathlib import Path


_scripts = Path(__file__).resolve().parents[2] / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from supervisor.main import run_supervisor_cycle
from supervisor.reader import compute_active_evidence_fingerprint


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_snapshot(root: Path, *, ts: str, photo_rows: list[dict], price_rows: list[dict]) -> None:
    photo_path = root / f"refreshed_catalog_photo_recovery_queue_{ts}.jsonl"
    price_path = root / f"refreshed_catalog_price_followup_queue_{ts}.jsonl"
    summary_path = root / f"refreshed_catalog_followup_summary_{ts}.json"
    _write_jsonl(photo_path, photo_rows)
    _write_jsonl(price_path, price_rows)
    summary_path.write_text(
        json.dumps(
            {
                "snapshot_generated_at": "2026-04-06T20:00:00Z",
                "snapshot_id": f"snap_{ts}",
                "queue_schema_version": "followup_queue_v2",
                "source_evidence_fingerprint": "sha256:evidence",
                "photo_recovery_queue_path": str(photo_path),
                "price_followup_queue_path": str(price_path),
                "photo_recovery_count": len(photo_rows),
                "price_followup_count": len(price_rows),
                "source_bundle_count": 2,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_evidence_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "evidence_A.json").write_text(json.dumps({"pn": "A"}), encoding="utf-8")
    (path / "evidence_B.json").write_text(json.dumps({"pn": "B"}), encoding="utf-8")


def test_run_supervisor_cycle_dry_run_writes_manifest_and_journal(tmp_path):
    state_root = tmp_path / "supervisor"
    scout_cache = tmp_path / "scout_cache"
    evidence_dir = tmp_path / "evidence"
    scout_cache.mkdir()
    _write_evidence_dir(evidence_dir)
    _write_snapshot(
        scout_cache,
        ts="20260406T160000Z",
        photo_rows=[{"pn": "A", "action_code": "photo_recovery"}],
        price_rows=[{"pn": "B", "action_code": "scout_price"}],
    )

    result = run_supervisor_cycle(
        state_root=state_root,
        scout_cache_dir=scout_cache,
        evidence_dir=evidence_dir,
        dry_run=True,
    )

    manifest = json.loads((state_root / "manifest.json").read_text(encoding="utf-8"))
    runs = (state_root / "runs.jsonl").read_text(encoding="utf-8").splitlines()

    assert result["last_action"] == "photo_pipeline"
    assert manifest["status"] == "completed"
    assert manifest["write_phase"] == "terminal"
    assert manifest["dispatch_id"].startswith("dispatch_")
    assert len(runs) == 1


def test_run_supervisor_cycle_uses_configured_batch_limit(tmp_path, monkeypatch):
    state_root = tmp_path / "supervisor"
    scout_cache = tmp_path / "scout_cache"
    evidence_dir = tmp_path / "evidence"
    scout_cache.mkdir()
    _write_evidence_dir(evidence_dir)
    _write_snapshot(
        scout_cache,
        ts="20260406T160500Z",
        photo_rows=[{"pn": "A", "action_code": "photo_recovery"}],
        price_rows=[],
    )

    monkeypatch.setattr(
        "supervisor.main.load_supervisor_config",
        lambda: {
            "batch_limits": {"photo": 1, "price": 2},
            "telegram": {
                "enabled": True,
                "api_base": "https://api.telegram.org",
                "bot_token_key": "SUPERVISOR_TELEGRAM_BOT_TOKEN",
                "chat_id_key": "SUPERVISOR_TELEGRAM_CHAT_ID",
                "poll_limit": 20,
                "send_timeout_seconds": 15,
                "poll_timeout_seconds": 15,
                "delivery_retry_backoff_seconds": [60, 300, 1800],
                "decision_timeout_hours": 24,
            },
        },
    )

    result = run_supervisor_cycle(
        state_root=state_root,
        scout_cache_dir=scout_cache,
        evidence_dir=evidence_dir,
        dry_run=True,
    )

    assert result["params"]["limit"] == 1


def test_run_supervisor_cycle_child_failure_creates_incident_packet(tmp_path, monkeypatch):
    state_root = tmp_path / "supervisor"
    scout_cache = tmp_path / "scout_cache"
    evidence_dir = tmp_path / "evidence"
    scout_cache.mkdir()
    _write_evidence_dir(evidence_dir)
    _write_snapshot(
        scout_cache,
        ts="20260406T170000Z",
        photo_rows=[{"pn": "A", "action_code": "photo_recovery"}],
        price_rows=[],
    )

    def fake_run_command(command, *, trace_id, logs_dir):
        return {
            "exit_code": 1,
            "stdout_path": str(logs_dir / f"{trace_id}.stdout.log"),
            "stderr_path": str(logs_dir / f"{trace_id}.stderr.log"),
            "result_summary": None,
        }

    monkeypatch.setattr("supervisor.main.run_command", fake_run_command)

    result = run_supervisor_cycle(
        state_root=state_root,
        scout_cache_dir=scout_cache,
        evidence_dir=evidence_dir,
        dry_run=False,
    )

    packets = (state_root / "packets.jsonl").read_text(encoding="utf-8").splitlines()
    assert result["status"] == "awaiting_packet_delivery"
    assert result["pending_packet_type"] == "incident"
    assert len(packets) == 1


def test_run_supervisor_cycle_lock_busy_is_fail_fast(tmp_path):
    state_root = tmp_path / "supervisor"
    scout_cache = tmp_path / "scout_cache"
    evidence_dir = tmp_path / "evidence"
    scout_cache.mkdir()
    _write_evidence_dir(evidence_dir)
    _write_snapshot(
        scout_cache,
        ts="20260406T180000Z",
        photo_rows=[{"pn": "A", "action_code": "photo_recovery"}],
        price_rows=[],
    )

    lock_path = state_root / "supervisor.lock"
    state_root.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({"pid": os.getpid(), "acquired_at": "2026-04-06T18:00:00Z"}), encoding="utf-8")

    result = run_supervisor_cycle(
        state_root=state_root,
        scout_cache_dir=scout_cache,
        evidence_dir=evidence_dir,
        dry_run=True,
    )

    assert result["rule"] == "RULE 0"
    assert result["result_kind"] == "lock_busy"


def test_run_supervisor_cycle_packet_creation_blocks_new_work(tmp_path):
    state_root = tmp_path / "supervisor"
    scout_cache = tmp_path / "scout_cache"
    evidence_dir = tmp_path / "evidence"
    scout_cache.mkdir()
    _write_evidence_dir(evidence_dir)
    _write_snapshot(
        scout_cache,
        ts="20260406T190000Z",
        photo_rows=[],
        price_rows=[{"pn": "B", "action_code": "blocked_owner_review"}],
    )
    current_fingerprint = compute_active_evidence_fingerprint(evidence_dir)
    (state_root / "manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (state_root / "manifest.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "last_evidence_fingerprint": current_fingerprint,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    first = run_supervisor_cycle(
        state_root=state_root,
        scout_cache_dir=scout_cache,
        evidence_dir=evidence_dir,
        dry_run=True,
    )
    second = run_supervisor_cycle(
        state_root=state_root,
        scout_cache_dir=scout_cache,
        evidence_dir=evidence_dir,
        dry_run=True,
    )

    assert first["status"] == "awaiting_packet_delivery"
    assert second["status"] == "awaiting_packet_delivery"
    assert second["result_kind"] == "delivery_pending"
