"""
test_owner_bridge.py — Tests for owner_bridge.py deterministic FSM processor.

Tests the transition matrix: input classification, manifest mutations,
outbox responses, idempotency, DLQ.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)

import owner_bridge as bridge  # noqa: E402


# ── Helpers ─────────────────────────────────────────────────────────────

def _write_manifest(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def _read_manifest(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))


def _write_inbox(tmp_path: Path, entries: list[dict]) -> Path:
    p = tmp_path / "owner_inbox.jsonl"
    lines = [json.dumps(e, ensure_ascii=False) for e in entries]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _read_outbox(tmp_path: Path) -> list[dict]:
    p = tmp_path / "owner_outbox.jsonl"
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    return [json.loads(ln) for ln in lines if ln.strip()]


def _read_dlq(tmp_path: Path) -> list[dict]:
    p = tmp_path / "owner_dlq.jsonl"
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    return [json.loads(ln) for ln in lines if ln.strip()]


def _patch_paths(tmp_path, monkeypatch):
    """Point all bridge paths to tmp_path."""
    monkeypatch.setattr(bridge, "MANIFEST_PATH", tmp_path / "manifest.json")
    monkeypatch.setattr(bridge, "INBOX_PATH", tmp_path / "owner_inbox.jsonl")
    monkeypatch.setattr(bridge, "OUTBOX_PATH", tmp_path / "owner_outbox.jsonl")
    monkeypatch.setattr(bridge, "BRIDGE_STATE_PATH", tmp_path / "bridge_state.json")
    monkeypatch.setattr(bridge, "DLQ_PATH", tmp_path / "owner_dlq.jsonl")
    monkeypatch.setattr(bridge, "BRIDGE_LOG_PATH", tmp_path / "bridge.log")
    monkeypatch.setattr(bridge, "LOCK_PATH", tmp_path / "orchestrator.lock")


# ── classify_input ──────────────────────────────────────────────────────

class TestClassifyInput:

    def test_approve_words(self):
        m = {"fsm_state": "awaiting_owner_reply"}
        for word in ("ок", "ok", "да", "yes", "го", "давай", "продолжай"):
            assert bridge.classify_input(word, m)[0] == "approve"

    def test_reject_words(self):
        m = {"fsm_state": "blocked"}
        for word in ("нет", "no", "стоп", "stop"):
            assert bridge.classify_input(word, m)[0] == "reject"

    def test_status_always_works(self):
        for state in ("ready", "idle", "awaiting_owner_reply"):
            m = {"fsm_state": state}
            assert bridge.classify_input("/status", m)[0] == "status"

    def test_decision_with_pending(self):
        m = {
            "fsm_state": "awaiting_owner_reply",
            "pending_decision": {"question": "?", "options": {"A": "Yes", "B": "No"}},
        }
        typ, payload = bridge.classify_input("A", m)
        assert typ == "decision"
        assert payload["key"] == "A"
        assert payload["text"] == "Yes"

    def test_decision_lowercase(self):
        m = {
            "fsm_state": "awaiting_owner_reply",
            "pending_decision": {"question": "?", "options": {"A": "Y", "B": "N"}},
        }
        typ, payload = bridge.classify_input("b", m)
        assert typ == "decision"
        assert payload["key"] == "B"

    def test_decision_invalid_option(self):
        m = {
            "fsm_state": "awaiting_owner_reply",
            "pending_decision": {"question": "?", "options": {"A": "Y", "B": "N"}},
        }
        # "C" not in options, too short for freetext
        typ, _ = bridge.classify_input("C", m)
        assert typ == "too_short"

    def test_freetext_in_park_state(self):
        m = {"fsm_state": "blocked"}
        typ, payload = bridge.classify_input("попробуй другой подход", m)
        assert typ == "freetext"
        assert payload["instruction"] == "попробуй другой подход"

    def test_freetext_in_idle_is_chat(self):
        m = {"fsm_state": "idle"}
        typ, payload = bridge.classify_input("какой статус проекта", m)
        assert typ == "chat"
        assert payload["message"] == "какой статус проекта"

    def test_freetext_in_ready_is_chat(self):
        m = {"fsm_state": "ready"}
        typ, payload = bridge.classify_input("сколько SKU без описаний", m)
        assert typ == "chat"
        assert payload["message"] == "сколько SKU без описаний"

    def test_task_command_creates_new_task(self):
        m = {"fsm_state": "idle"}
        typ, payload = bridge.classify_input("/task обнови каталог PEHA", m)
        assert typ == "new_task"
        assert payload["instruction"] == "обнови каталог PEHA"

    def test_task_command_too_short(self):
        m = {"fsm_state": "idle"}
        typ, _ = bridge.classify_input("/task ок", m)
        assert typ == "too_short"

    def test_approve_in_idle_is_no_pending(self):
        m = {"fsm_state": "idle"}
        typ, _ = bridge.classify_input("ок", m)
        assert typ == "no_pending_state"

    def test_too_short(self):
        m = {"fsm_state": "awaiting_owner_reply"}
        typ, _ = bridge.classify_input("хм", m)
        assert typ == "too_short"

    def test_all_park_states_accept_approve(self):
        for state in bridge.PARK_STATES:
            m = {"fsm_state": state}
            typ, _ = bridge.classify_input("ок", m)
            assert typ == "approve", f"State {state} rejected approve"


# ── process_inbox_entry: approve ────────────────────────────────────────

class TestApprove:

    def test_approve_resumes_ready(self, tmp_path, monkeypatch):
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "park_reason": "#blocker_loop",
            "current_task_id": "fix-auth",
        })
        entry = {"update_id": 100, "text": "ок", "ts": "2026-04-10T12:00:00Z"}
        state = {"last_processed_update_id": 0, "processed_count": 0}

        ok = bridge.process_inbox_entry(entry, state)

        assert ok is True
        m = _read_manifest(tmp_path)
        assert m["fsm_state"] == "ready"
        assert m.get("park_reason") is None
        assert m.get("last_verdict") is None

        outbox = _read_outbox(tmp_path)
        assert len(outbox) == 1
        assert "Принято" in outbox[0]["text"]

        assert state["last_processed_update_id"] == 100
        assert state["processed_count"] == 1

    def test_approve_all_park_states(self, tmp_path, monkeypatch):
        _patch_paths(tmp_path, monkeypatch)
        for i, state in enumerate(bridge.PARK_STATES, start=200):
            _write_manifest(tmp_path, {"fsm_state": state})
            entry = {"update_id": i, "text": "ok"}
            bstate = {"last_processed_update_id": i - 1}
            ok = bridge.process_inbox_entry(entry, bstate)
            assert ok is True
            assert _read_manifest(tmp_path)["fsm_state"] == "ready"


# ── process_inbox_entry: reject ─────────────────────────────────────────

class TestReject:

    def test_reject_keeps_parked(self, tmp_path, monkeypatch):
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {
            "fsm_state": "blocked",
            "park_reason": "#blocker",
        })
        entry = {"update_id": 101, "text": "нет"}
        state = {"last_processed_update_id": 0}

        ok = bridge.process_inbox_entry(entry, state)

        assert ok is True
        m = _read_manifest(tmp_path)
        assert m["fsm_state"] == "blocked"  # unchanged
        assert m.get("park_reason") == "#blocker"  # unchanged

        outbox = _read_outbox(tmp_path)
        assert "паузе" in outbox[-1]["text"]


# ── process_inbox_entry: decision ───────────────────────────────────────

class TestDecision:

    def test_decision_a(self, tmp_path, monkeypatch):
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "pending_decision": {
                "question": "Что делать?",
                "options": {"A": "Добавить", "B": "Исправить"},
            },
        })
        entry = {"update_id": 102, "text": "A"}
        state = {"last_processed_update_id": 0}

        ok = bridge.process_inbox_entry(entry, state)

        assert ok is True
        m = _read_manifest(tmp_path)
        assert m["owner_decision"] == "A"
        assert m["owner_decision_text"] == "Добавить"
        assert m["fsm_state"] == "ready"
        assert m.get("pending_decision") is None


# ── process_inbox_entry: freetext ───────────────────────────────────────

class TestFreetext:

    def test_freetext_saves_instruction(self, tmp_path, monkeypatch):
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "park_reason": "#blocker",
        })
        text = "попробуй другой подход — используй gemini"
        entry = {"update_id": 103, "text": text}
        state = {"last_processed_update_id": 0}

        ok = bridge.process_inbox_entry(entry, state)

        assert ok is True
        m = _read_manifest(tmp_path)
        assert m["owner_instruction"] == text
        assert m["fsm_state"] == "ready"
        assert m.get("park_reason") is None

        outbox = _read_outbox(tmp_path)
        assert "инструкцию" in outbox[-1]["text"].lower()


# ── process_inbox_entry: new_task ──────────────────────────────────────

class TestNewTask:

    def test_new_task_via_command(self, tmp_path, monkeypatch):
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {"fsm_state": "idle"})
        text = "/task Обнови каталог — добавь описания для PEHA"
        entry = {"update_id": 110, "text": text}
        state = {"last_processed_update_id": 0}

        ok = bridge.process_inbox_entry(entry, state)

        assert ok is True
        m = _read_manifest(tmp_path)
        assert m["fsm_state"] == "ready"
        assert "Обнови каталог" in m["current_sprint_goal"]
        assert m["current_task_id"].startswith("tg-")

        outbox = _read_outbox(tmp_path)
        assert "Принял задачу" in outbox[-1]["text"]


# ── process_inbox_entry: status ─────────────────────────────────────────

class TestStatus:

    def test_status_no_mutation(self, tmp_path, monkeypatch):
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {
            "fsm_state": "ready",
            "current_task_id": "test-task",
        })
        entry = {"update_id": 104, "text": "/status"}
        state = {"last_processed_update_id": 0}

        ok = bridge.process_inbox_entry(entry, state)

        assert ok is True
        m = _read_manifest(tmp_path)
        assert m["fsm_state"] == "ready"  # unchanged

        outbox = _read_outbox(tmp_path)
        assert "test-task" in outbox[-1]["text"]


# ── Idempotency ─────────────────────────────────────────────────────────

class TestIdempotency:

    def test_duplicate_update_id_skipped(self, tmp_path, monkeypatch):
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {"fsm_state": "blocked"})
        entry = {"update_id": 50, "text": "ок"}
        state = {"last_processed_update_id": 50}  # already processed

        ok = bridge.process_inbox_entry(entry, state)

        assert ok is True  # skipped
        assert _read_manifest(tmp_path)["fsm_state"] == "blocked"  # not changed

    def test_double_approve_safe(self, tmp_path, monkeypatch):
        """Second approve when state already ready = no-op."""
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "park_reason": "#test",
        })
        entry1 = {"update_id": 60, "text": "ок"}
        entry2 = {"update_id": 61, "text": "ок"}
        state = {"last_processed_update_id": 0}

        bridge.process_inbox_entry(entry1, state)
        assert _read_manifest(tmp_path)["fsm_state"] == "ready"

        # Second approve — state is now ready (not in PARK_STATES)
        bridge.process_inbox_entry(entry2, state)
        m = _read_manifest(tmp_path)
        assert m["fsm_state"] == "ready"  # still ready, idempotent

        outbox = _read_outbox(tmp_path)
        # Second approve classified as no_pending_state — safe no-op
        assert "ready" in outbox[-1]["text"]


# ── DLQ ─────────────────────────────────────────────────────────────────

class TestDLQ:

    def test_empty_text_goes_to_dlq(self, tmp_path, monkeypatch):
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {"fsm_state": "blocked"})
        entry = {"update_id": 70, "text": ""}
        state = {"last_processed_update_id": 0}

        ok = bridge.process_inbox_entry(entry, state)

        assert ok is True
        dlq = _read_dlq(tmp_path)
        assert len(dlq) == 1
        assert dlq[0]["reason"] == "empty_text"


# ── process_all_pending (integration) ───────────────────────────────────

class TestProcessAll:

    def test_full_cycle(self, tmp_path, monkeypatch):
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "park_reason": "#blocker",
        })
        _write_inbox(tmp_path, [
            {"update_id": 80, "text": "/status", "ts": "2026-04-10T12:00:00Z"},
            {"update_id": 81, "text": "ок", "ts": "2026-04-10T12:00:01Z"},
        ])

        count = bridge.process_all_pending()

        assert count == 2
        m = _read_manifest(tmp_path)
        assert m["fsm_state"] == "ready"

        outbox = _read_outbox(tmp_path)
        assert len(outbox) == 2  # status reply + approve reply

        bstate = bridge._load_bridge_state()
        assert bstate["last_processed_update_id"] == 81
        assert bstate["processed_count"] == 2

    def test_cursor_persisted_after_each_entry(self, tmp_path, monkeypatch):
        """Cursor saved after each entry — crash-safe."""
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "park_reason": "#test",
        })
        _write_inbox(tmp_path, [
            {"update_id": 85, "text": "/status"},
            {"update_id": 86, "text": "ок"},
        ])

        # Process first entry only by simulating partial run
        bridge.process_all_pending()

        # Cursor should be at 86 (both processed)
        bstate = bridge._load_bridge_state()
        assert bstate["last_processed_update_id"] == 86

        # Simulate restart: re-run with same inbox
        _write_manifest(tmp_path, {"fsm_state": "blocked"})
        count = bridge.process_all_pending()
        assert count == 0  # all already processed — cursor survived "restart"
        assert _read_manifest(tmp_path)["fsm_state"] == "blocked"  # not mutated

    def test_already_processed_skipped(self, tmp_path, monkeypatch):
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {"fsm_state": "blocked"})
        _write_inbox(tmp_path, [
            {"update_id": 90, "text": "ок"},
            {"update_id": 91, "text": "нет"},
        ])
        # Pretend update 90 already processed
        bridge._save_bridge_state({
            "last_processed_update_id": 90,
            "processed_count": 5,
        })

        count = bridge.process_all_pending()

        assert count == 1  # only update 91
        # Reject doesn't change state
        assert _read_manifest(tmp_path)["fsm_state"] == "blocked"


# ── Query/Task split (Wave 5) ─────────────────────────────────────────


class TestQueryTaskSplit:
    """Fast path: QUERY/COMMAND skip manifest lock, TASK takes lock."""

    def test_status_command_skips_lock(self, tmp_path, monkeypatch):
        """COMMAND stream uses fast path — no manifest mutation."""
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {
            "fsm_state": "running",
            "current_task_id": "task-42",
        })
        entry = {"update_id": 500, "text": "/status"}
        state = {"last_processed_update_id": 0, "processed_count": 0}

        ok = bridge.process_inbox_entry(entry, state)

        assert ok is True
        # Manifest untouched
        m = _read_manifest(tmp_path)
        assert m["fsm_state"] == "running"
        # Response in outbox
        outbox = _read_outbox(tmp_path)
        assert any("task-42" in o["text"] for o in outbox)
        # Event type tagged correctly
        assert outbox[-1]["event_type"] == "bridge_status"

    def test_chat_query_skips_lock(self, tmp_path, monkeypatch):
        """QUERY stream uses fast path — no lock, Anthropic (Claude) for Q&A."""
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {"fsm_state": "idle"})
        # Mock chat_engine to avoid real Anthropic call
        import chat_engine
        import chat_session
        monkeypatch.setattr(chat_engine, "_load_anthropic_key", lambda: "fake-key")
        monkeypatch.setattr(chat_session, "load_history", lambda: [])
        monkeypatch.setattr(chat_session, "save_turn", lambda u, a: None)
        # Mock Anthropic client
        import types as _types
        fake_content = _types.SimpleNamespace(text="Ответ от Claude")
        fake_response = _types.SimpleNamespace(content=[fake_content])
        fake_client = _types.SimpleNamespace(
            messages=_types.SimpleNamespace(
                create=lambda **kw: fake_response
            )
        )
        monkeypatch.setattr("anthropic.Anthropic",
                            lambda **kw: fake_client,
                            raising=False)

        entry = {"update_id": 501, "text": "как работает gateway?"}
        state = {"last_processed_update_id": 0, "processed_count": 0}

        ok = bridge.process_inbox_entry(entry, state)

        assert ok is True
        outbox = _read_outbox(tmp_path)
        assert any("Claude" in o["text"] for o in outbox)
        assert outbox[-1]["event_type"] == "bridge_chat"
        # Manifest untouched
        m = _read_manifest(tmp_path)
        assert m["fsm_state"] == "idle"

    def test_approve_takes_fsm_path(self, tmp_path, monkeypatch):
        """TASK stream takes FSM path — acquires lock, mutates manifest."""
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "park_reason": "#test",
        })
        entry = {"update_id": 502, "text": "ок"}
        state = {"last_processed_update_id": 0, "processed_count": 0}

        ok = bridge.process_inbox_entry(entry, state)

        assert ok is True
        m = _read_manifest(tmp_path)
        assert m["fsm_state"] == "ready"  # FSM mutated

    def test_query_does_not_block_when_manifest_locked(self, tmp_path, monkeypatch):
        """QUERY should succeed even if manifest is locked by orchestrator."""
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {"fsm_state": "running"})

        # Simulate locked manifest — make _acquire_manifest_lock return None
        monkeypatch.setattr(bridge, "_acquire_manifest_lock", lambda: None)

        entry = {"update_id": 503, "text": "/status"}
        state = {"last_processed_update_id": 0, "processed_count": 0}

        ok = bridge.process_inbox_entry(entry, state)

        # Should succeed — fast path doesn't need lock
        assert ok is True
        outbox = _read_outbox(tmp_path)
        assert len(outbox) >= 1

    def test_task_blocked_when_manifest_locked(self, tmp_path, monkeypatch):
        """TASK should return False when manifest is locked."""
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
        })

        # Simulate locked manifest
        monkeypatch.setattr(bridge, "_acquire_manifest_lock", lambda: None)

        entry = {"update_id": 504, "text": "ок"}
        state = {"last_processed_update_id": 0, "processed_count": 0}

        ok = bridge.process_inbox_entry(entry, state)

        # Should fail — FSM path needs lock
        assert ok is False
        # No outbox written
        outbox = _read_outbox(tmp_path)
        assert len(outbox) == 0

    def test_mixed_stream_ordering(self, tmp_path, monkeypatch):
        """Process queue with mixed COMMAND + TASK entries."""
        _patch_paths(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {
            "fsm_state": "awaiting_owner_reply",
            "park_reason": "#test",
        })
        _write_inbox(tmp_path, [
            {"update_id": 600, "text": "/status"},
            {"update_id": 601, "text": "ок"},
            {"update_id": 602, "text": "/status"},
        ])

        count = bridge.process_all_pending()

        assert count == 3
        outbox = _read_outbox(tmp_path)
        assert len(outbox) == 3
        # First status, then approve, then status again
        assert outbox[0]["event_type"] == "bridge_status"
        assert outbox[1]["event_type"] == "bridge_approve"
        assert outbox[2]["event_type"] == "bridge_status"

    def test_read_only_streams_constant(self):
        """Verify _READ_ONLY_STREAMS includes only non-mutating streams."""
        from inbox_router import Stream
        assert Stream.QUERY in bridge._READ_ONLY_STREAMS
        assert Stream.COMMAND in bridge._READ_ONLY_STREAMS
        assert Stream.TASK not in bridge._READ_ONLY_STREAMS
        assert Stream.CALLBACK not in bridge._READ_ONLY_STREAMS
