"""Schema contract test for rev_export_logs (R2 Telegram Export)."""

from pathlib import Path


def test_rev_export_logs_schema_columns():
    """Verify expected columns exist in rev_export_logs schema definition."""
    root = Path(__file__).resolve().parents[1]
    migration_path = root / "migrations" / "027_create_rev_export_logs.sql"
    with open(migration_path, encoding="utf-8") as f:
        content = f.read()

    required_columns = [
        "id BIGSERIAL PRIMARY KEY",
        "trace_id TEXT NOT NULL",
        "user_id TEXT",
        "chat_id TEXT",
        "category TEXT",
        "format TEXT",
        "status TEXT DEFAULT 'pending'",
        "created_at TIMESTAMPTZ DEFAULT now()",
    ]
    for col in required_columns:
        assert col in content, f"Missing column definition: {col}"

    assert "rev_export_logs" in content
    assert "idx_rev_export_logs_trace_id" in content
    assert "idx_rev_export_logs_created_at" in content
