"""Tests for shadow adjudication and development memory generation."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from shadow_adjudication import (
    assign_review_priority,
    build_adjudication_queue,
    build_blocker_register,
    build_development_memory,
    build_reviewer_packets,
    build_shadow_usefulness_summary,
    materialize_shadow_artifacts,
)

RUN_DIR = Path(__file__).resolve().parents[2] / "downloads" / "audits" / "phase_a_v2_sanity_20260326T213348Z"


def test_priority_prefers_policy_too_strict_with_contradictions():
    priority, score = assign_review_priority(
        ["policy_too_strict_candidate"],
        ["contradiction_in_evidence"],
        ["upstream_missing_signal"],
    )
    assert priority == "P1"
    assert score >= 100


def test_adjudication_queue_replays_from_existing_artifact():
    queue = build_adjudication_queue(RUN_DIR)
    assert queue
    first = queue[0]
    assert first["run_id"] == "phase_a_v2_sanity_20260326T213348Z"
    assert first["source_artifact_refs"]["bundle"].endswith(".json")
    assert Path(first["source_artifact_refs"]["bundle"]).exists()


def test_blocker_register_and_usefulness_summary_build():
    queue = build_adjudication_queue(RUN_DIR)
    blocker_register = build_blocker_register(RUN_DIR, queue)
    usefulness = build_shadow_usefulness_summary(RUN_DIR, queue)
    assert blocker_register["strongest_blocker"]["category"] == "still_blocked_for_broader_run"
    assert usefulness["deterministic_still_authoritative"] is True
    assert usefulness["broader_controlled_run"] == "NO"


def test_reviewer_packets_reference_existing_artifacts():
    queue = build_adjudication_queue(RUN_DIR)
    packets = build_reviewer_packets(RUN_DIR, queue, top_n=3)
    assert packets
    for packet in packets:
        assert Path(packet["artifact_refs"]["bundle"]).exists()
        assert packet["deterministic_status"] == "DRAFT_ONLY"


def test_development_memory_contains_one_next_work_item():
    queue = build_adjudication_queue(RUN_DIR)
    blocker_register = build_blocker_register(RUN_DIR, queue)
    usefulness = build_shadow_usefulness_summary(RUN_DIR, queue)
    memory = build_development_memory(RUN_DIR, queue, blocker_register, usefulness)
    assert memory["next_approved_work_item"]["title"]
    assert memory["source_run_id"] == "phase_a_v2_sanity_20260326T213348Z"
    assert "verifier_policy_version" in memory["policy_schema_versions"]


def test_materialize_shadow_artifacts_writes_all_outputs(tmp_path: Path):
    memory_path = tmp_path / "memory.json"
    outputs = materialize_shadow_artifacts(RUN_DIR, memory_path=memory_path)
    assert outputs["queue"].exists()
    assert outputs["blocker_register"].exists()
    assert outputs["usefulness_summary"].exists()
    assert outputs["reviewer_packets"].exists()
    assert outputs["development_memory"].exists()

