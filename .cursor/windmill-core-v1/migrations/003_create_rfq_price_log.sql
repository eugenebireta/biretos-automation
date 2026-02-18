-- Migration: 003_create_rfq_price_log.sql
-- Purpose: Append-only RFQ price audit persistence
-- Date: 2026-02-13

CREATE TABLE IF NOT EXISTS rfq_price_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rfq_id UUID NOT NULL REFERENCES rfq_requests(id) ON DELETE CASCADE,
    run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL CHECK (status IN ('success', 'error', 'skipped')),
    items_total INTEGER NOT NULL DEFAULT 0,
    items_found INTEGER NOT NULL DEFAULT 0,
    error TEXT NULL,
    audit_data JSONB NULL
);

CREATE INDEX IF NOT EXISTS idx_rfq_price_log_rfq_id
    ON rfq_price_log(rfq_id);

CREATE INDEX IF NOT EXISTS idx_rfq_price_log_run_at
    ON rfq_price_log(run_at DESC);
