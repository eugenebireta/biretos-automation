"""Test that manifest reset clears stale artifacts.

trace_id: orch_20260408T184728Z_3be09d
Deterministic test — no live API, no unmocked time/randomness.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Repo root on sys.path so supervisor package is importable.
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from scripts.supervisor.manifest import DEFAULT_MANIFEST, load_manifest, write_manifest


TRACE_ID = "orch_20260408T184728Z_3be09d"
IDEMPOTENCY_KEY = "test-manifest-reset-stale-001"

# Fields that represent stale runtime artifacts from a previous cycle.
STALE_ARTIFACT_FIELDS: dict[str, object] = {
    "trace_id": "old_trace_abc123",
    "status": "awaiting_owner_reply",
    "write_phase": "pre_action",
    "awaiting_owner_reply": True,
    "pending_packet_id": "pkt_stale_999",
    "pending_packet_type": "owner_decision",
    "decision_deadline_at": "2026-04-01T00:00:00Z",
    "default_option_id": "opt_a",
    "default_applied_at": "2026-04-01T01:00:00Z",
    "next_actions": {"opt_a": "run_enrichment", "opt_b": "skip"},
    "last_action": "send_decision_packet",
    "last_rule": "RULE 5",
    "last_dispatch_id": "dsp_old_777",
    "last_evidence_fingerprint": "fp_stale_aaa",
    "post_refresh_fingerprint": "fp_stale_bbb",
    "refresh_generation": 42,
    "last_rebuild_generation": 41,
    "rerun_intent_id": "rerun_old_555",
    "result_kind": "owner_packet_sent",
}


@pytest.fixture()
def state_dir(tmp_path: Path) -> Path:
    """Provide an isolated state directory with a stale manifest seeded."""
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(
        json.dumps(STALE_ARTIFACT_FIELDS, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return tmp_path


def test_load_manifest_merges_defaults(state_dir: Path) -> None:
    """load_manifest should return stale data when the file contains it."""
    manifest = load_manifest(state_dir)
    assert manifest["pending_packet_id"] == "pkt_stale_999"
    assert manifest["awaiting_owner_reply"] is True
    assert manifest["rerun_intent_id"] == "rerun_old_555"


def test_reset_clears_stale_artifacts(state_dir: Path) -> None:
    """Writing DEFAULT_MANIFEST then reloading must clear every stale field."""
    # Precondition: stale data is present.
    before = load_manifest(state_dir)
    assert before["pending_packet_id"] == "pkt_stale_999"

    # ── Reset: overwrite with clean defaults ──
    write_manifest(state_dir, dict(DEFAULT_MANIFEST))

    # ── Verify all stale artifacts are gone ──
    after = load_manifest(state_dir)
    for key, default_value in DEFAULT_MANIFEST.items():
        assert after[key] == default_value, (
            f"Field '{key}' not reset: got {after[key]!r}, expected {default_value!r}"
        )

    # Explicit checks on the most critical stale fields.
    assert after["pending_packet_id"] is None
    assert after["pending_packet_type"] is None
    assert after["awaiting_owner_reply"] is False
    assert after["next_actions"] == {}
    assert after["last_dispatch_id"] is None
    assert after["rerun_intent_id"] is None
    assert after["decision_deadline_at"] is None
    assert after["default_option_id"] is None
    assert after["default_applied_at"] is None
    assert after["result_kind"] == ""
    assert after["status"] == "ready"
    assert after["write_phase"] == "terminal"


def test_reset_is_idempotent(state_dir: Path) -> None:
    """Resetting twice produces the same clean state."""
    write_manifest(state_dir, dict(DEFAULT_MANIFEST))
    first = load_manifest(state_dir)

    write_manifest(state_dir, dict(DEFAULT_MANIFEST))
    second = load_manifest(state_dir)

    assert first == second


def test_reset_removes_extra_keys(state_dir: Path) -> None:
    """Keys that exist in stale manifest but not in DEFAULT_MANIFEST
    should not survive a reset."""
    # Seed extra non-standard key.
    stale = dict(STALE_ARTIFACT_FIELDS)
    stale["_debug_leftover"] = "should_vanish"
    write_manifest(state_dir, stale)

    loaded = load_manifest(state_dir)
    assert "_debug_leftover" in loaded  # merged from file

    # Reset.
    write_manifest(state_dir, dict(DEFAULT_MANIFEST))
    after = load_manifest(state_dir)
    assert "_debug_leftover" not in after
