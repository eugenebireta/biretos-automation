BEGIN;

CREATE TABLE IF NOT EXISTS config_snapshots (
    policy_hash TEXT PRIMARY KEY,
    config_content JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_config_snapshots_created_at
    ON config_snapshots (created_at DESC);

COMMIT;
