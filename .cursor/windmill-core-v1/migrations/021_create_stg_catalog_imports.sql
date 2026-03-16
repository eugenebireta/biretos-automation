-- Migration: 021_create_stg_catalog_imports.sql
-- Purpose: R1 Mass Catalog Pipeline — Per-row import records (Tier-3 Revenue adapter)
-- Row FSM: pending → syncing → done | failed  (linear)
-- Photo FSM: none → pending → uploaded | failed  (optional, non-blocking)
-- Scope: stg_* namespace only; no DDL on Core or reconciliation_* tables.
-- Retention: 6 months after publication (Revenue Artifacts class, MASTER_PLAN_PATCH v1.7.3).
-- Notes: Plain SQL only; idempotent via IF NOT EXISTS / constraint names.

CREATE TABLE IF NOT EXISTS stg_catalog_imports (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID        NOT NULL
                                REFERENCES stg_catalog_jobs(id) ON DELETE CASCADE,
    trace_id        UUID        NOT NULL,
    idempotency_key TEXT        NOT NULL,
    row_idx         INTEGER     NOT NULL,

    -- Normalised catalog fields (mandatory)
    mpn             TEXT        NOT NULL,
    brand           TEXT        NOT NULL,
    title           TEXT        NOT NULL,

    -- Optional pricing
    price_minor     BIGINT      NULL,
    currency        TEXT        NULL DEFAULT 'RUB',

    -- Raw source payload (preserved for audit / re-processing)
    raw_payload     JSONB       NOT NULL DEFAULT '{}',

    -- Photo pipeline (optional; failure must not block sync)
    photo_url       TEXT        NULL,
    photo_status    TEXT        NOT NULL DEFAULT 'none'
                                CHECK (photo_status IN ('none', 'pending', 'uploaded', 'failed')),

    -- Sync state machine
    sync_status     TEXT        NOT NULL DEFAULT 'pending'
                                CHECK (sync_status IN ('pending', 'syncing', 'done', 'failed')),
    sync_error      TEXT        NULL,

    -- Result reference from external catalog platform
    external_id     TEXT        NULL,
    published_at    TIMESTAMPTZ NULL,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT stg_catalog_imports_idempotency_key_uniq UNIQUE (idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_stg_catalog_imports_job_id
    ON stg_catalog_imports(job_id);

CREATE INDEX IF NOT EXISTS idx_stg_catalog_imports_trace_id
    ON stg_catalog_imports(trace_id);

CREATE INDEX IF NOT EXISTS idx_stg_catalog_imports_sync_status
    ON stg_catalog_imports(sync_status);

-- Deduplication lookup (exact MPN + Brand, per R1 Hard Stop rules)
CREATE INDEX IF NOT EXISTS idx_stg_catalog_imports_mpn_brand
    ON stg_catalog_imports(mpn, brand);

-- Retention: partial index over published rows for cleanup queries
CREATE INDEX IF NOT EXISTS idx_stg_catalog_imports_published_at
    ON stg_catalog_imports(published_at)
    WHERE published_at IS NOT NULL;
