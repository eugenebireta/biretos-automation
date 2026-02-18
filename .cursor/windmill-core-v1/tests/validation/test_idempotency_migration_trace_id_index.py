from __future__ import annotations

import re
from pathlib import Path


def _project_root() -> Path:
    # tests/validation/<file>.py -> tests -> project root
    return Path(__file__).resolve().parents[2]


def test_action_idempotency_trace_id_index_migration_exists_and_mentions_index():
    migrations_dir = _project_root() / "migrations"
    candidates = sorted(migrations_dir.glob("0*_add_action_idempotency_trace_id_index.sql"))
    assert candidates, "Expected H2 migration file to exist in migrations/"

    # The migration should be unique (defense against duplicate numbering).
    assert len(candidates) == 1, f"Expected exactly 1 H2 migration file, found: {candidates}"

    text = candidates[0].read_text(encoding="utf-8", errors="ignore").lower()

    assert "idx_ail_trace_id" in text
    assert re.search(r"\bon\s+action_idempotency_log\b", text) is not None

