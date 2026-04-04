from __future__ import annotations

from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_review_cases_create_migration_exists_before_015():
    migrations = sorted((_project_root() / "migrations").iterdir(), key=lambda p: p.name)
    names = [p.name for p in migrations]
    create_name = "014b_create_review_cases.sql"
    assert create_name in names
    assert "015_add_review_cases_executing_status.sql" in names
    assert names.index(create_name) < names.index("015_add_review_cases_executing_status.sql")


def test_review_cases_migration_contains_core_columns():
    content = (_project_root() / "migrations" / "014b_create_review_cases.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS review_cases" in content
    assert "idempotency_key TEXT NOT NULL" in content
    assert "escalation_level INTEGER NOT NULL DEFAULT 0" in content
    assert "action_snapshot JSONB NOT NULL" in content


def test_shadow_rag_additive_migration_tracks_live_hybrid_schema():
    content = (_project_root() / "migrations" / "030_add_nlu_columns_to_shadow_rag_log.sql").read_text(encoding="utf-8")
    for column in (
        "raw_text_hash",
        "entities JSONB",
        "confidence NUMERIC",
        "model_version TEXT",
        "prompt_version TEXT",
        "parse_duration_ms INTEGER",
    ):
        assert column in content
