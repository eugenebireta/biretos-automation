import json
import sys
from pathlib import Path


_scripts = Path(__file__).resolve().parents[2] / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from supervisor.main import run_supervisor_cycle
from supervisor.reader import compute_active_evidence_fingerprint
from supervisor.telegram import build_reply_markup, format_packet_text, send_packet
from supervisor.telegram_reader import apply_callback_updates


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


def _runtime() -> dict:
    return {
        "api_base": "https://api.telegram.org",
        "bot_token": "token",
        "chat_id": "123",
        "poll_limit": 20,
        "send_timeout_seconds": 15,
        "poll_timeout_seconds": 15,
        "delivery_retry_backoff_seconds": [60, 300, 1800],
        "decision_timeout_hours": 24,
    }


def test_send_packet_success_and_keyboard():
    packet = {
        "type": "owner_decision",
        "packet_id": "pkt_1",
        "trace_id": "trace_1",
        "what_blocked": "blocked",
        "business_question": "what now?",
        "affected_sku_count": 2,
        "recommended_option": "defer",
        "decision_status": "pending",
        "applied_option_id": None,
        "options": [
            {"id": "defer", "label": "Отложить", "next_action": "set_idle"},
            {"id": "review", "label": "Review", "next_action": "set_idle"},
        ],
    }

    calls = []

    def fake_post(url, payload, timeout):
        calls.append((url, payload, timeout))
        return {"ok": True, "result": {"message_id": 77}}

    result = send_packet(packet, _runtime(), post_json=fake_post)

    assert "owner_decision" in format_packet_text(packet)
    assert build_reply_markup(packet)["inline_keyboard"][0][0]["callback_data"] == "sup|pkt_1|defer"
    assert result["delivery_status"] == "sent"
    assert result["telegram_message_id"] == 77
    assert calls[0][1]["chat_id"] == "123"


def test_apply_callback_updates_applies_once_and_ignores_duplicate():
    packet_states = {
        "pkt_1": {
            "packet_id": "pkt_1",
            "decision_status": "pending",
            "applied_option_id": None,
            "options": [{"id": "defer"}, {"id": "review"}],
        }
    }
    updates = [{"update_id": 10, "callback_query": {"data": "sup|pkt_1|review"}}]
    first = apply_callback_updates(updates, packet_states)
    second = apply_callback_updates(updates, packet_states)

    assert first[0]["decision_status"] == "applied"
    assert first[0]["applied_option_id"] == "review"
    assert second[0]["ignored_reason"] == "already_processed"


def test_run_supervisor_cycle_sends_owner_packet_and_waits_for_reply(tmp_path, monkeypatch):
    state_root = tmp_path / "supervisor"
    scout_cache = tmp_path / "scout_cache"
    evidence_dir = tmp_path / "evidence"
    scout_cache.mkdir()
    _write_evidence_dir(evidence_dir)
    _write_snapshot(
        scout_cache,
        ts="20260406T200000Z",
        photo_rows=[],
        price_rows=[{"pn": "B", "action_code": "blocked_owner_review"}],
    )
    current_fingerprint = compute_active_evidence_fingerprint(evidence_dir)
    (state_root / "manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (state_root / "manifest.json").write_text(
        json.dumps({"status": "ready", "last_evidence_fingerprint": current_fingerprint}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    monkeypatch.setattr("supervisor.main.load_telegram_runtime", lambda **kwargs: _runtime())
    monkeypatch.setattr(
        "supervisor.main.poll_updates",
        lambda runtime, telegram_state: ([], {"last_update_id": 0, "last_poll_ts": "2026-04-06T20:00:00Z"}),
    )
    monkeypatch.setattr(
        "supervisor.main.send_packet",
        lambda packet, runtime: {
            "event_type": "delivery_update",
            "packet_id": packet["packet_id"],
            "delivery_status": "sent",
            "delivery_attempts": 1,
            "next_retry_at": None,
            "last_send_error": None,
            "telegram_message_id": 99,
            "sent_at": "2026-04-06T20:00:00Z",
            "decision_status": packet["decision_status"],
            "applied_option_id": packet["applied_option_id"],
        },
    )

    result = run_supervisor_cycle(
        state_root=state_root,
        scout_cache_dir=scout_cache,
        evidence_dir=evidence_dir,
        dry_run=False,
    )

    assert result["status"] == "awaiting_owner_reply"
    assert result["pending_packet_type"] == "owner_decision"
    assert result["default_option_id"] == "defer"


def test_run_supervisor_cycle_retry_send_failed_then_sent(tmp_path, monkeypatch):
    state_root = tmp_path / "supervisor"
    scout_cache = tmp_path / "scout_cache"
    evidence_dir = tmp_path / "evidence"
    scout_cache.mkdir()
    _write_evidence_dir(evidence_dir)
    _write_snapshot(scout_cache, ts="20260406T210000Z", photo_rows=[], price_rows=[])
    (state_root / "manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (state_root / "manifest.json").write_text(
        json.dumps(
            {
                "status": "awaiting_packet_delivery",
                "pending_packet_id": "pkt_owner",
                "pending_packet_type": "owner_decision",
                "last_evidence_fingerprint": compute_active_evidence_fingerprint(evidence_dir),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_jsonl(
        state_root / "packets.jsonl",
        [
            {
                "event_type": "created",
                "type": "owner_decision",
                "packet_id": "pkt_owner",
                "delivery_status": "send_failed",
                "delivery_attempts": 1,
                "next_retry_at": "2026-04-06T00:00:00Z",
                "decision_status": "pending",
                "applied_option_id": None,
                "default_if_no_reply": "defer",
                "decision_deadline_at": "2026-04-07T00:00:00Z",
                "options": [{"id": "defer", "label": "Отложить", "next_action": "set_idle"}],
            }
        ],
    )

    monkeypatch.setattr("supervisor.main.load_telegram_runtime", lambda **kwargs: _runtime())
    monkeypatch.setattr(
        "supervisor.main.poll_updates",
        lambda runtime, telegram_state: ([], {"last_update_id": 0, "last_poll_ts": "2026-04-06T21:00:00Z"}),
    )
    monkeypatch.setattr(
        "supervisor.main.send_packet",
        lambda packet, runtime: {
            "event_type": "delivery_update",
            "packet_id": packet["packet_id"],
            "delivery_status": "sent",
            "delivery_attempts": 2,
            "next_retry_at": None,
            "last_send_error": None,
            "telegram_message_id": 100,
            "sent_at": "2026-04-06T21:00:00Z",
            "decision_status": packet["decision_status"],
            "applied_option_id": packet["applied_option_id"],
        },
    )

    result = run_supervisor_cycle(
        state_root=state_root,
        scout_cache_dir=scout_cache,
        evidence_dir=evidence_dir,
        dry_run=False,
    )

    assert result["status"] == "awaiting_owner_reply"
    assert result["pending_packet_id"] == "pkt_owner"


def test_run_supervisor_cycle_applies_callback_and_updates_offset(tmp_path, monkeypatch):
    state_root = tmp_path / "supervisor"
    scout_cache = tmp_path / "scout_cache"
    evidence_dir = tmp_path / "evidence"
    scout_cache.mkdir()
    _write_evidence_dir(evidence_dir)
    _write_snapshot(scout_cache, ts="20260406T220000Z", photo_rows=[], price_rows=[])
    (state_root / "manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (state_root / "manifest.json").write_text(
        json.dumps(
            {
                "status": "awaiting_owner_reply",
                "awaiting_owner_reply": True,
                "pending_packet_id": "pkt_owner",
                "pending_packet_type": "owner_decision",
                "decision_deadline_at": "2099-04-07T00:00:00Z",
                "default_option_id": "defer",
                "next_actions": {"defer": "set_idle"},
                "last_evidence_fingerprint": compute_active_evidence_fingerprint(evidence_dir),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_jsonl(
        state_root / "packets.jsonl",
        [
            {
                "event_type": "created",
                "type": "owner_decision",
                "packet_id": "pkt_owner",
                "delivery_status": "sent",
                "delivery_attempts": 1,
                "next_retry_at": None,
                "decision_status": "pending",
                "applied_option_id": None,
                "options": [{"id": "defer", "label": "Отложить", "next_action": "set_idle"}],
            }
        ],
    )

    monkeypatch.setattr("supervisor.main.load_telegram_runtime", lambda **kwargs: _runtime())
    monkeypatch.setattr(
        "supervisor.main.poll_updates",
        lambda runtime, telegram_state: (
            [{"update_id": 42, "callback_query": {"data": "sup|pkt_owner|defer"}}],
            {"last_update_id": 42, "last_poll_ts": "2026-04-06T22:00:00Z"},
        ),
    )

    result = run_supervisor_cycle(
        state_root=state_root,
        scout_cache_dir=scout_cache,
        evidence_dir=evidence_dir,
        dry_run=False,
    )

    telegram_state = json.loads((state_root / "telegram_state.json").read_text(encoding="utf-8"))
    assert result["status"] == "completed"
    assert result["result_kind"] == "owner_reply_applied"
    assert telegram_state["last_update_id"] == 42


def test_run_supervisor_cycle_applies_timeout_default_and_journals(tmp_path, monkeypatch):
    state_root = tmp_path / "supervisor"
    scout_cache = tmp_path / "scout_cache"
    evidence_dir = tmp_path / "evidence"
    scout_cache.mkdir()
    _write_evidence_dir(evidence_dir)
    _write_snapshot(scout_cache, ts="20260406T230000Z", photo_rows=[], price_rows=[])
    (state_root / "manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (state_root / "manifest.json").write_text(
        json.dumps(
            {
                "status": "awaiting_owner_reply",
                "awaiting_owner_reply": True,
                "pending_packet_id": "pkt_owner",
                "pending_packet_type": "owner_decision",
                "decision_deadline_at": "2000-04-07T00:00:00Z",
                "default_option_id": "defer",
                "next_actions": {"defer": "set_idle"},
                "last_evidence_fingerprint": compute_active_evidence_fingerprint(evidence_dir),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_jsonl(
        state_root / "packets.jsonl",
        [
            {
                "event_type": "created",
                "type": "owner_decision",
                "packet_id": "pkt_owner",
                "delivery_status": "sent",
                "delivery_attempts": 1,
                "next_retry_at": None,
                "decision_status": "pending",
                "applied_option_id": None,
                "options": [{"id": "defer", "label": "Отложить", "next_action": "set_idle"}],
            }
        ],
    )

    monkeypatch.setattr("supervisor.main.load_telegram_runtime", lambda **kwargs: _runtime())
    monkeypatch.setattr(
        "supervisor.main.poll_updates",
        lambda runtime, telegram_state: ([], {"last_update_id": 0, "last_poll_ts": "2026-04-06T23:00:00Z"}),
    )

    result = run_supervisor_cycle(
        state_root=state_root,
        scout_cache_dir=scout_cache,
        evidence_dir=evidence_dir,
        dry_run=False,
    )

    packets = (state_root / "packets.jsonl").read_text(encoding="utf-8")
    assert result["status"] == "completed"
    assert result["default_applied_at"] is not None
    assert '"event_type": "default_applied"' in packets
