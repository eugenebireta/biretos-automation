-- Migration 020: stg_catalog_jobs
-- R1 Mass Catalog Pipeline — job-level state machine.
--
-- FSM (linear, max 5 states per DNA §5b):
--   pending → parsing → syncing → done / failed
--
-- Rules:
--   - Tier-3 staging table only (stg_ prefix per DNA §5b).
--   - Core tables are NOT touched by this migration.
--   - idempotency_key is the external dedup key (INSERT ON CONFLICT DO NOTHING).

CREATE TABLE IF NOT EXISTS stg_catalog_jobs (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id         TEXT        NOT NULL,
    idempotency_key  TEXT        NOT NULL,
    source_filename  TEXT,
    brand            TEXT        NOT NULL DEFAULT '',
    row_count        INTEGER     NOT NULL DEFAULT 0,
    status           TEXT        NOT NULL DEFAULT 'pending',
    error            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT stg_catalog_jobs_idempotency_key_uq UNIQUE (idempotency_key),
    CONSTRAINT stg_catalog_jobs_status_chk CHECK (
        status IN ('pending', 'parsing', 'syncing', 'done', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS idx_stg_catalog_jobs_trace_id
    ON stg_catalog_jobs (trace_id);

CREATE INDEX IF NOT EXISTS idx_stg_catalog_jobs_status
    ON stg_catalog_jobs (status);
