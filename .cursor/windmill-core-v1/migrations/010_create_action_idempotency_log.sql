BEGIN;

CREATE TABLE IF NOT EXISTS action_idempotency_log (
    idempotency_key TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    request_hash TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('processing', 'succeeded', 'failed')),
    lease_token UUID NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 1 CHECK (attempt_count >= 1),
    last_error TEXT NULL,
    result_ref JSONB NULL,
    trace_id UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ail_sweep
    ON action_idempotency_log (status, expires_at)
    WHERE status = 'processing';

CREATE INDEX IF NOT EXISTS idx_ail_created
    ON action_idempotency_log (created_at);

COMMIT;
