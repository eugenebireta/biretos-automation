-- Migration: 020_create_stg_catalog_jobs.sql
-- Purpose: R1 Mass Catalog Pipeline — Job-level FSM table (Tier-3 Revenue adapter)
-- FSM: pending → parsing → syncing → done | failed  (linear, max 5 states)
-- Scope: stg_* namespace only; no DDL on Core or reconciliation_* tables.
-- Retention: per MASTER_PLAN_PATCH v1.7.3 Revenue Artifacts class.
-- Notes: Plain SQL only; idempotent via IF NOT EXISTS / constraint names.

CREATE TABLE IF NOT EXISTS stg_catalog_jobs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        UUID        NOT NULL,
    idempotency_key TEXT        NOT NULL,
    job_state       TEXT        NOT NULL DEFAULT 'pending'
                                CHECK (job_state IN ('pending', 'parsing', 'syncing', 'done', 'failed')),
    source_type     TEXT        NOT NULL
                                CHECK (source_type IN ('csv', 'excel', 'json')),
    source_ref      TEXT        NOT NULL,
    total_rows      INTEGER     NOT NULL DEFAULT 0,
    parsed_rows     INTEGER     NOT NULL DEFAULT 0,
    synced_rows     INTEGER     NOT NULL DEFAULT 0,
    failed_rows     INTEGER     NOT NULL DEFAULT 0,
    error_detail    TEXT        NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT stg_catalog_jobs_idempotency_key_uniq UNIQUE (idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_stg_catalog_jobs_trace_id
    ON stg_catalog_jobs(trace_id);

CREATE INDEX IF NOT EXISTS idx_stg_catalog_jobs_state
    ON stg_catalog_jobs(job_state);

CREATE INDEX IF NOT EXISTS idx_stg_catalog_jobs_created_at
    ON stg_catalog_jobs(created_at);
