import json
import sys
from datetime import datetime, timezone
from pathlib import Path


_scripts = Path(__file__).resolve().parents[2] / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from supervisor.reader import select_latest_snapshot
from supervisor.rules import determine_next_action


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_snapshot(
    root: Path,
    *,
    ts: str,
    photo_rows: list[dict],
    price_rows: list[dict],
    schema_version: str = "followup_queue_v2",
    fingerprint: str = "sha256:test",
) -> Path:
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
                "queue_schema_version": schema_version,
                "source_evidence_fingerprint": fingerprint,
                "photo_recovery_queue_path": str(photo_path),
                "price_followup_queue_path": str(price_path),
                "photo_recovery_count": len(photo_rows),
                "price_followup_count": len(price_rows),
                "source_bundle_count": 5,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return summary_path


def test_select_latest_snapshot_ignores_legacy_summary(tmp_path):
    legacy = tmp_path / "refreshed_catalog_followup_summary_20260406T100000Z.json"
    legacy.write_text(
        json.dumps({"generated_at": "2026-04-06T10:00:00Z", "photo_recovery_count": 1}),
        encoding="utf-8",
    )
    _write_snapshot(
        tmp_path,
        ts="20260406T110000Z",
        photo_rows=[{"pn": "A", "action_code": "photo_recovery"}],
        price_rows=[{"pn": "B", "action_code": "scout_price"}],
    )

    snapshot = select_latest_snapshot(tmp_path)

    assert snapshot is not None
    assert snapshot.snapshot_id == "snap_20260406T110000Z"
    assert snapshot.scout_price_count == 1


def test_determine_next_action_prefers_photo_then_price(tmp_path):
    _write_snapshot(
        tmp_path,
        ts="20260406T120000Z",
        photo_rows=[{"pn": "A", "action_code": "photo_recovery"}],
        price_rows=[
            {"pn": "B", "action_code": "scout_price"},
            {"pn": "C", "action_code": "blocked_owner_review"},
        ],
    )
    snapshot = select_latest_snapshot(tmp_path)

    decision = determine_next_action(
        manifest={"status": "ready", "last_evidence_fingerprint": "sha256:test"},
        snapshot=snapshot,
        current_evidence_fingerprint="sha256:test",
        packet_states={},
        photo_limit=3,
        price_limit=7,
    )

    assert decision.rule_name == "RULE 4"
    assert decision.kind == "launch"
    assert decision.action == "photo_pipeline"
    assert decision.command_spec is not None
    assert decision.command_spec.params["limit"] == 3


def test_determine_next_action_owner_packet_for_non_executable_backlog(tmp_path):
    _write_snapshot(
        tmp_path,
        ts="20260406T130000Z",
        photo_rows=[],
        price_rows=[
            {"pn": "B", "action_code": "blocked_owner_review"},
            {"pn": "C", "action_code": "admissibility_review"},
        ],
    )
    snapshot = select_latest_snapshot(tmp_path)

    decision = determine_next_action(
        manifest={"status": "ready", "last_evidence_fingerprint": "sha256:test"},
        snapshot=snapshot,
        current_evidence_fingerprint="sha256:test",
        packet_states={},
    )

    assert decision.rule_name == "RULE 8"
    assert decision.kind == "packet"
    assert decision.packet is not None
    assert decision.packet["type"] == "owner_decision"
    assert decision.packet["affected_sku_count"] == 2


def test_determine_next_action_refresh_rebuild_and_churn_flow(tmp_path):
    _write_snapshot(
        tmp_path,
        ts="20260406T140000Z",
        photo_rows=[],
        price_rows=[],
        fingerprint="sha256:fp1",
    )
    snapshot = select_latest_snapshot(tmp_path)

    refresh = determine_next_action(
        manifest={"status": "ready", "last_evidence_fingerprint": "sha256:old"},
        snapshot=snapshot,
        current_evidence_fingerprint="sha256:new",
        packet_states={},
    )
    assert refresh.rule_name == "RULE 5A"
    assert refresh.action == "refresh"

    rebuild = determine_next_action(
        manifest={
            "status": "ready",
            "last_action": "refresh",
            "refresh_generation": 1,
            "last_rebuild_generation": 0,
            "post_refresh_fingerprint": "sha256:new",
            "last_evidence_fingerprint": "sha256:new",
        },
        snapshot=snapshot,
        current_evidence_fingerprint="sha256:new",
        packet_states={},
    )
    assert rebuild.rule_name == "RULE 5B"
    assert rebuild.action == "rebuild_queues"

    churn = determine_next_action(
        manifest={
            "status": "ready",
            "last_action": "refresh",
            "refresh_generation": 1,
            "last_rebuild_generation": 0,
            "post_refresh_fingerprint": "sha256:new",
            "last_evidence_fingerprint": "sha256:new",
        },
        snapshot=snapshot,
        current_evidence_fingerprint="sha256:newer",
        packet_states={},
    )
    assert churn.rule_name == "RULE 5C"
    assert churn.result_kind == "deferred"


def test_determine_next_action_force_rerun_allows_same_dispatch(tmp_path):
    _write_snapshot(
        tmp_path,
        ts="20260406T150000Z",
        photo_rows=[{"pn": "A", "action_code": "photo_recovery"}],
        price_rows=[],
    )
    snapshot = select_latest_snapshot(tmp_path)
    first = determine_next_action(
        manifest={"status": "ready", "last_evidence_fingerprint": "sha256:test"},
        snapshot=snapshot,
        current_evidence_fingerprint="sha256:test",
        packet_states={},
    )

    blocked = determine_next_action(
        manifest={
            "status": "completed",
            "last_evidence_fingerprint": "sha256:test",
            "last_dispatch_id": first.dispatch_id,
        },
        snapshot=snapshot,
        current_evidence_fingerprint="sha256:test",
        packet_states={},
    )
    assert blocked.result_kind == "duplicate_dispatch_blocked"

    rerun = determine_next_action(
        manifest={
            "status": "completed",
            "last_evidence_fingerprint": "sha256:test",
            "last_dispatch_id": first.dispatch_id,
        },
        snapshot=snapshot,
        current_evidence_fingerprint="sha256:test",
        packet_states={},
        now=datetime(2026, 4, 6, 15, 0, 0, tzinfo=timezone.utc),
        force_rerun=True,
    )
    assert rerun.kind == "launch"
    assert rerun.rerun_intent_id.startswith("rerun_")


def test_determine_next_action_uses_configured_price_limit(tmp_path):
    _write_snapshot(
        tmp_path,
        ts="20260406T151500Z",
        photo_rows=[],
        price_rows=[{"pn": "B", "action_code": "scout_price"}],
    )
    snapshot = select_latest_snapshot(tmp_path)

    decision = determine_next_action(
        manifest={"status": "ready", "last_evidence_fingerprint": "sha256:test"},
        snapshot=snapshot,
        current_evidence_fingerprint="sha256:test",
        packet_states={},
        price_limit=2,
    )

    assert decision.rule_name == "RULE 5"
    assert decision.command_spec is not None
    assert decision.command_spec.params["limit"] == 2
