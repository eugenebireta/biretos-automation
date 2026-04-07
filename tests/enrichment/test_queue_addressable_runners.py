import json
import sys
from pathlib import Path

import pandas as pd
import pytest


_scripts = Path(__file__).resolve().parents[2] / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

import photo_pipeline
import run_price_only_scout_pilot as price_pilot


def _write_photo_catalog(path: Path) -> None:
    df = pd.DataFrame(
        [
            {
                photo_pipeline.INPUT_COL_PN: "PN-2",
                photo_pipeline.INPUT_COL_NAME: "Second",
                photo_pipeline.INPUT_COL_OUR_PRICE: "200",
                photo_pipeline.INPUT_COL_CATEGORY: "Cat",
            },
            {
                photo_pipeline.INPUT_COL_PN: "PN-1",
                photo_pipeline.INPUT_COL_NAME: "First",
                photo_pipeline.INPUT_COL_OUR_PRICE: "100",
                photo_pipeline.INPUT_COL_CATEGORY: "Cat",
            },
        ]
    )
    df.to_csv(path, sep="\t", encoding="utf-16", index=False)


def test_photo_pipeline_load_run_dataframe_filters_queue_and_preserves_queue_order(tmp_path):
    input_file = tmp_path / "catalog.tsv"
    queue_path = tmp_path / "photo_queue.jsonl"
    _write_photo_catalog(input_file)
    queue_rows = [
        {
            "queue_schema_version": "followup_queue_v2",
            "snapshot_id": "snap_test",
            "pn": "PN-1",
            "action_code": "photo_recovery",
        },
        {
            "queue_schema_version": "followup_queue_v2",
            "snapshot_id": "snap_test",
            "pn": "PN-2",
            "action_code": "blocked_owner_review",
        },
    ]
    queue_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in queue_rows) + "\n",
        encoding="utf-8",
    )

    df = photo_pipeline.load_run_dataframe(
        input_file=input_file,
        queue_path=queue_path,
    )

    assert list(df[photo_pipeline.INPUT_COL_PN]) == ["PN-1"]


def test_photo_pipeline_queue_fails_closed_on_unknown_schema(tmp_path):
    queue_path = tmp_path / "photo_queue.jsonl"
    queue_path.write_text(
        json.dumps(
            {
                "queue_schema_version": "v1",
                "pn": "PN-1",
                "action_code": "photo_recovery",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported queue schema version"):
        photo_pipeline.load_queue_part_numbers(
            queue_path,
            allowed_action_codes={"photo_recovery"},
        )


def test_price_pilot_queue_only_processes_scout_price_actions():
    queue_request = {
        "requested_pns": ["PN-2", "PN-1"],
    }
    catalog_rows = [
        {"pn": "PN-1", "name": "First"},
        {"pn": "PN-2", "name": "Second"},
        {"pn": "PN-3", "name": "Third"},
    ]
    candidate_index = {
        "PN-1": [{"url": "https://example.com/1"}],
        "PN-2": [{"url": "https://example.com/2"}],
        "PN-3": [{"url": "https://example.com/3"}],
    }

    selected = price_pilot.select_queue_seeded_rows(
        queue_request=queue_request,
        catalog_rows=catalog_rows,
        candidate_index=candidate_index,
        limit=20,
    )

    assert [row["pn"] for row in selected] == ["PN-2", "PN-1"]


def test_price_pilot_load_queue_request_skips_non_scout_actions(tmp_path):
    queue_path = tmp_path / "price_queue.jsonl"
    queue_rows = [
        {
            "queue_schema_version": "followup_queue_v2",
            "snapshot_id": "snap_test",
            "pn": "PN-1",
            "action_code": "scout_price",
        },
        {
            "queue_schema_version": "followup_queue_v2",
            "snapshot_id": "snap_test",
            "pn": "PN-2",
            "action_code": "blocked_owner_review",
        },
        {
            "queue_schema_version": "followup_queue_v2",
            "snapshot_id": "snap_test",
            "pn": "PN-3",
            "action_code": "stale_truth_reconcile",
        },
    ]
    queue_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in queue_rows) + "\n",
        encoding="utf-8",
    )

    request = price_pilot.load_queue_request(queue_path)

    assert request["requested_pns"] == ["PN-1"]
    assert request["requested_count"] == 1
    assert request["queue_schema_version"] == "followup_queue_v2"
    assert request["skipped_action_counts"] == {
        "blocked_owner_review": 1,
        "stale_truth_reconcile": 1,
    }
