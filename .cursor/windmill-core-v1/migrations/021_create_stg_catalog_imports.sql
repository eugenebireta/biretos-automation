-- Migration 021: stg_catalog_imports
-- R1 Mass Catalog Pipeline — per-row import state.
--
-- FSM (linear, max 5 states per DNA §5b):
--   pending → syncing → done / failed / review_required
--
-- Rules:
--   - Tier-3 staging table only (stg_ prefix per DNA §5b).
--   - Core tables are NOT touched.
--   - idempotency_key per row = dedup guard (INSERT ON CONFLICT DO NOTHING).
--   - error_class: TRANSIENT | PERMANENT | POLICY_VIOLATION per DNA §7.

CREATE TABLE IF NOT EXISTS stg_catalog_imports (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id           UUID        NOT NULL REFERENCES stg_catalog_jobs (id),
    trace_id         TEXT        NOT NULL,
    idempotency_key  TEXT        NOT NULL,
    brand            TEXT        NOT NULL,
    part_number      TEXT        NOT NULL,
    name             TEXT,
    qty              INTEGER,
    approx_price     NUMERIC(18, 4),
    confidence       TEXT        NOT NULL DEFAULT 'LOW',
    review_reason    TEXT,
    photo_url        TEXT,
    status           TEXT        NOT NULL DEFAULT 'pending',
    shopware_op_id   TEXT,
    error_class      TEXT,
    error            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT stg_catalog_imports_idempotency_key_uq UNIQUE (idempotency_key),
    CONSTRAINT stg_catalog_imports_confidence_chk CHECK (
        confidence IN ('HIGH', 'MEDIUM', 'LOW')
    ),
    CONSTRAINT stg_catalog_imports_status_chk CHECK (
        status IN ('pending', 'syncing', 'done', 'failed', 'review_required')
    ),
    CONSTRAINT stg_catalog_imports_error_class_chk CHECK (
        error_class IS NULL
        OR error_class IN ('TRANSIENT', 'PERMANENT', 'POLICY_VIOLATION')
    )
);

CREATE INDEX IF NOT EXISTS idx_stg_catalog_imports_job_id
    ON stg_catalog_imports (job_id);

CREATE INDEX IF NOT EXISTS idx_stg_catalog_imports_status
    ON stg_catalog_imports (status);

CREATE INDEX IF NOT EXISTS idx_stg_catalog_imports_part_number
    ON stg_catalog_imports (part_number);
