"""
test_gateway_bridge_integration.py — End-to-end test: Gateway inbox -> Bridge -> outbox.

Simulates the full cycle without real Telegram: writes to inbox in gateway
format, runs bridge, verifies outbox contains correct response.
Tests that bridge does NOT re-process entries after restart.
"""
from __future__ import annotations

import json
import os
import sys

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)

import owner_bridge as bridge  # noqa: E402


def _patch(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "MANIFEST_PATH", tmp_path / "manifest.json")
    monkeypatch.setattr(bridge, "INBOX_PATH", tmp_path / "owner_inbox.jsonl")
    monkeypatch.setattr(bridge, "OUTBOX_PATH", tmp_path / "owner_outbox.jsonl")
    monkeypatch.setattr(bridge, "BRIDGE_STATE_PATH", tmp_path / "bridge_state.json")
    monkeypatch.setattr(bridge, "DLQ_PATH", tmp_path / "owner_dlq.jsonl")
    monkeypatch.setattr(bridge, "BRIDGE_LOG_PATH", tmp_path / "bridge.log")
    monkeypatch.setattr(bridge, "LOCK_PATH", tmp_path / "orchestrator.lock")


def _write_manifest(tmp_path, data):
    (tmp_path / "manifest.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _read_manifest(tmp_path):
    return json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))


def _append_inbox(tmp_path, entry):
    """Append one gateway-format inbox entry."""
    p = tmp_path / "owner_inbox.jsonl"
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read_outbox(tmp_path):
    p = tmp_path / "owner_outbox.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


class TestFullCycle:
    """Simulate: owner sends message -> bridge processes -> outbox has response."""

    def test_approve_full_cycle(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "park_reason": "#blocker_loop: failed 3 times",
            "current_task_id": "fix-auth",
            "trace_id": "orch_test_001",
        })

        # Simulate gateway writing to inbox
        _append_inbox(tmp_path, {
            "ts": "2026-04-10T12:00:00Z",
            "msg_id": 100,
            "update_id": 500001,
            "chat_id": 123456,
            "text": "ок",
            "source": "telegram_gateway",
        })

        # Bridge processes
        count = bridge.process_all_pending()
        assert count == 1

        # Manifest updated
        m = _read_manifest(tmp_path)
        assert m["fsm_state"] == "ready"
        assert m.get("park_reason") is None

        # Outbox has response
        outbox = _read_outbox(tmp_path)
        assert len(outbox) == 1
        assert "Принято" in outbox[0]["text"]
        assert outbox[0]["event_type"] == "bridge_approve"

    def test_no_reprocess_after_restart(self, tmp_path, monkeypatch):
        """After processing, restarting bridge does NOT re-process old entries."""
        _patch(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {
            "fsm_state": "blocked",
            "park_reason": "#test",
        })
        _append_inbox(tmp_path, {
            "ts": "2026-04-10T12:00:00Z",
            "msg_id": 200,
            "update_id": 500002,
            "chat_id": 123456,
            "text": "ок",
            "source": "telegram_gateway",
        })

        # First run
        count1 = bridge.process_all_pending()
        assert count1 == 1
        assert _read_manifest(tmp_path)["fsm_state"] == "ready"

        # "Restart" — set manifest back to blocked
        _write_manifest(tmp_path, {"fsm_state": "blocked"})

        # Second run — should NOT re-process the same entry
        count2 = bridge.process_all_pending()
        assert count2 == 0
        assert _read_manifest(tmp_path)["fsm_state"] == "blocked"  # not changed!

    def test_no_reprocess_entry_without_update_id(self, tmp_path, monkeypatch):
        """Old-format entries (no update_id) tracked by line index, not re-processed."""
        _patch(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "park_reason": "#test",
        })

        # Old format entry — no update_id, no msg_id
        _append_inbox(tmp_path, {
            "ts": "2026-04-10T10:00:00Z",
            "text": "старое сообщение без update_id, достаточно длинное",
        })

        # First run processes it
        count1 = bridge.process_all_pending()
        assert count1 == 1

        # Reset manifest to park state
        _write_manifest(tmp_path, {
            "fsm_state": "blocked",
            "park_reason": "#test2",
        })

        # Second run — must NOT re-process (line cursor advanced)
        count2 = bridge.process_all_pending()
        assert count2 == 0
        assert _read_manifest(tmp_path)["fsm_state"] == "blocked"

    def test_mixed_entries_sequential(self, tmp_path, monkeypatch):
        """Multiple entries processed in order, each gets correct response."""
        _patch(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "park_reason": "#test",
            "pending_decision": {
                "question": "Что делать?",
                "options": {"A": "Добавить", "B": "Удалить"},
            },
        })

        _append_inbox(tmp_path, {
            "ts": "2026-04-10T12:00:00Z", "msg_id": 300,
            "update_id": 600001, "chat_id": 123, "text": "/status",
            "source": "telegram_gateway",
        })
        _append_inbox(tmp_path, {
            "ts": "2026-04-10T12:00:01Z", "msg_id": 301,
            "update_id": 600002, "chat_id": 123, "text": "A",
            "source": "telegram_gateway",
        })

        count = bridge.process_all_pending()
        assert count == 2

        m = _read_manifest(tmp_path)
        assert m["owner_decision"] == "A"
        assert m["fsm_state"] == "ready"

        outbox = _read_outbox(tmp_path)
        assert len(outbox) == 2
        assert "bridge_status" in outbox[0]["event_type"]
        assert "bridge_decision" in outbox[1]["event_type"]

    def test_daemon_single_cycle(self, tmp_path, monkeypatch):
        """run_once() works as expected."""
        _patch(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {"fsm_state": "blocked"})
        _append_inbox(tmp_path, {
            "ts": "2026-04-10T12:00:00Z", "msg_id": 400,
            "update_id": 700001, "chat_id": 123, "text": "нет",
            "source": "telegram_gateway",
        })

        count = bridge.run_once()
        assert count == 1
        assert _read_manifest(tmp_path)["fsm_state"] == "blocked"  # reject = no change
