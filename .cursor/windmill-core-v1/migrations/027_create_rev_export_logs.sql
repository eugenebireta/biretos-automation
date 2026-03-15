-- Migration: 027_create_rev_export_logs.sql
-- Purpose: R2 Telegram Export — audit trail table (Revenue Tier-3)
-- Scope: rev_export_logs only; no reconciliation_*; no Core tables.

CREATE TABLE IF NOT EXISTS rev_export_logs (
    id BIGSERIAL PRIMARY KEY,
    trace_id TEXT NOT NULL,
    user_id TEXT,
    chat_id TEXT,
    category TEXT,
    format TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rev_export_logs_trace_id
    ON rev_export_logs(trace_id);

CREATE INDEX IF NOT EXISTS idx_rev_export_logs_created_at
    ON rev_export_logs(created_at);
