"""
test_resume_watcher.py — Tests for resume_watcher.py polling launcher.

Tests: should_spawn logic, sidecar state, cooldown, consecutive spawn cap,
singleton lock, run_once integration.
"""
from __future__ import annotations

import json
import os
import sys
import time

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)

import resume_watcher as watcher  # noqa: E402


# ── Helpers ─────────────────────────────────────────────────────────────

def _patch(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, "MANIFEST_PATH", tmp_path / "manifest.json")
    monkeypatch.setattr(watcher, "MAIN_PY", tmp_path / "fake_main.py")
    monkeypatch.setattr(watcher, "WATCHER_LOCK_PATH", tmp_path / "watcher.lock")
    monkeypatch.setattr(watcher, "WATCHER_STATE_PATH", tmp_path / "watcher_state.json")
    monkeypatch.setattr(watcher, "WATCHER_LOG_PATH", tmp_path / "watcher.log")
    monkeypatch.setattr(watcher, "ROOT", tmp_path)


def _write_manifest(tmp_path, data):
    (tmp_path / "manifest.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _write_fake_main(tmp_path, script="import sys; sys.exit(0)"):
    """Write a fake main.py that exits immediately."""
    (tmp_path / "fake_main.py").write_text(script, encoding="utf-8")


def _fresh_state():
    return {
        "last_spawned_at": None,
        "last_manifest_updated_at": None,
        "consecutive_spawns": 0,
        "total_spawns": 0,
    }


# ── should_spawn ───────────────────────────────────────────────────────

class TestShouldSpawn:

    def test_ready_spawns(self):
        manifest = {"fsm_state": "ready", "updated_at": "2026-04-10T15:00:00Z"}
        state = _fresh_state()
        ok, reason = watcher.should_spawn(manifest, state, cooldown=30)
        assert ok is True
        assert reason == "ready"

    def test_non_ready_skips(self):
        for fsm in ("idle", "blocked", "awaiting_owner_reply", "processing", "error"):
            manifest = {"fsm_state": fsm}
            state = _fresh_state()
            ok, reason = watcher.should_spawn(manifest, state, cooldown=30)
            assert ok is False
            assert f"fsm_state={fsm}" in reason

    def test_cooldown_blocks(self):
        manifest = {"fsm_state": "ready", "updated_at": "2026-04-10T15:01:00Z"}
        state = _fresh_state()
        state["last_spawned_at"] = time.time() - 5  # 5s ago
        ok, reason = watcher.should_spawn(manifest, state, cooldown=30)
        assert ok is False
        assert "cooldown" in reason

    def test_cooldown_expired_allows(self):
        manifest = {"fsm_state": "ready", "updated_at": "2026-04-10T15:01:00Z"}
        state = _fresh_state()
        state["last_spawned_at"] = time.time() - 60  # 60s ago
        ok, reason = watcher.should_spawn(manifest, state, cooldown=30)
        assert ok is True

    def test_same_updated_at_skips(self):
        ts = "2026-04-10T15:00:00Z"
        manifest = {"fsm_state": "ready", "updated_at": ts}
        state = _fresh_state()
        state["last_manifest_updated_at"] = ts
        ok, reason = watcher.should_spawn(manifest, state, cooldown=30)
        assert ok is False
        assert "same manifest.updated_at" in reason

    def test_different_updated_at_spawns(self):
        manifest = {"fsm_state": "ready", "updated_at": "2026-04-10T15:02:00Z"}
        state = _fresh_state()
        state["last_manifest_updated_at"] = "2026-04-10T15:00:00Z"
        ok, reason = watcher.should_spawn(manifest, state, cooldown=30)
        assert ok is True

    def test_consecutive_spawns_cap(self):
        manifest = {"fsm_state": "ready", "updated_at": "2026-04-10T15:00:00Z"}
        state = _fresh_state()
        state["consecutive_spawns"] = watcher.MAX_CONSECUTIVE_SPAWNS
        ok, reason = watcher.should_spawn(manifest, state, cooldown=30)
        assert ok is False
        assert "consecutive_spawns" in reason


# ── Sidecar state persistence ──────────────────────────────────────────

class TestSidecarState:

    def test_save_and_load(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        state = {"last_spawned_at": 12345.0, "last_manifest_updated_at": "ts1",
                 "consecutive_spawns": 2, "total_spawns": 10}
        watcher._save_watcher_state(state)
        loaded = watcher._load_watcher_state()
        assert loaded == state

    def test_load_missing_returns_default(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        state = watcher._load_watcher_state()
        assert state["last_spawned_at"] is None
        assert state["consecutive_spawns"] == 0

    def test_load_corrupt_returns_default(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        (tmp_path / "watcher_state.json").write_text("not json", encoding="utf-8")
        state = watcher._load_watcher_state()
        assert state["last_spawned_at"] is None


# ── read_manifest ──────────────────────────────────────────────────────

class TestReadManifest:

    def test_read_valid(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {"fsm_state": "ready"})
        m = watcher.read_manifest()
        assert m["fsm_state"] == "ready"

    def test_read_missing_returns_none(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        assert watcher.read_manifest() is None

    def test_read_corrupt_returns_none(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        (tmp_path / "manifest.json").write_text("{bad", encoding="utf-8")
        assert watcher.read_manifest() is None


# ── spawn_main ─────────────────────────────────────────────────────────

class TestSpawnMain:

    def test_spawn_updates_state(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        _write_fake_main(tmp_path)
        manifest = {"fsm_state": "ready", "updated_at": "ts1"}
        state = _fresh_state()

        proc = watcher.spawn_main(state, manifest)
        assert proc is not None
        proc.wait()

        assert state["total_spawns"] == 1
        assert state["consecutive_spawns"] == 1
        assert state["last_manifest_updated_at"] == "ts1"
        assert state["last_spawned_at"] is not None

    def test_spawn_increments_consecutive_on_same_ts(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        _write_fake_main(tmp_path)
        manifest = {"fsm_state": "ready", "updated_at": "ts1"}
        state = _fresh_state()
        state["last_manifest_updated_at"] = "ts1"
        state["consecutive_spawns"] = 2

        proc = watcher.spawn_main(state, manifest)
        proc.wait()

        assert state["consecutive_spawns"] == 3

    def test_spawn_resets_consecutive_on_new_ts(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        _write_fake_main(tmp_path)
        manifest = {"fsm_state": "ready", "updated_at": "ts2"}
        state = _fresh_state()
        state["last_manifest_updated_at"] = "ts1"
        state["consecutive_spawns"] = 4

        proc = watcher.spawn_main(state, manifest)
        proc.wait()

        assert state["consecutive_spawns"] == 1
        assert state["last_manifest_updated_at"] == "ts2"


# ── run_once integration ──────────────────────────────────────────────

class TestRunOnce:

    def test_spawns_on_ready(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {"fsm_state": "ready", "updated_at": "ts1"})
        _write_fake_main(tmp_path)

        result = watcher.run_once(cooldown=0)
        assert result is True

        state = watcher._load_watcher_state()
        assert state["total_spawns"] == 1

    def test_no_spawn_on_blocked(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {"fsm_state": "blocked"})

        result = watcher.run_once(cooldown=0)
        assert result is False

    def test_no_spawn_without_manifest(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)

        result = watcher.run_once(cooldown=0)
        assert result is False

    def test_no_respawn_same_updated_at(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {"fsm_state": "ready", "updated_at": "ts1"})
        _write_fake_main(tmp_path)

        # First spawn
        result1 = watcher.run_once(cooldown=0)
        assert result1 is True

        # Second — same updated_at, should skip
        result2 = watcher.run_once(cooldown=0)
        assert result2 is False

    def test_respawn_on_new_updated_at(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {"fsm_state": "ready", "updated_at": "ts1"})
        _write_fake_main(tmp_path)

        result1 = watcher.run_once(cooldown=0)
        assert result1 is True

        # Manifest updated — new ts
        _write_manifest(tmp_path, {"fsm_state": "ready", "updated_at": "ts2"})
        result2 = watcher.run_once(cooldown=0)
        assert result2 is True

        state = watcher._load_watcher_state()
        assert state["total_spawns"] == 2

    def test_child_exit_code_logged(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        _write_manifest(tmp_path, {"fsm_state": "ready", "updated_at": "ts1"})
        _write_fake_main(tmp_path, "import sys; print('hello'); sys.exit(1)")

        watcher.run_once(cooldown=0)

        log = (tmp_path / "watcher.log").read_text(encoding="utf-8")
        assert "hello" in log


# ── Singleton lock ────────────────────────────────────────────────────

class TestSingleton:

    def test_acquire_and_release(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        fh = watcher.acquire_singleton()
        assert fh is not None
        watcher.release_singleton(fh)

    def test_double_acquire_fails(self, tmp_path, monkeypatch):
        _patch(tmp_path, monkeypatch)
        fh1 = watcher.acquire_singleton()
        assert fh1 is not None

        fh2 = watcher.acquire_singleton()
        assert fh2 is None  # second acquire must fail

        watcher.release_singleton(fh1)
