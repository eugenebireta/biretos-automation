-- Migration: 016_create_reconciliation_audit_log.sql
-- Purpose: Reconciliation Architecture v2 (P0) — two-phase audit trail (INTENT/OUTCOME)
-- Notes: Plain SQL only; idempotent via IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS reconciliation_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sweep_trace_id UUID NOT NULL,
    rc_code TEXT NOT NULL,
    layer TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN ('INTENT', 'OUTCOME')),
    ic_verdict_before JSONB NULL,
    action_result JSONB NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('pending', 'success', 'noop', 'error', 'rollback', 'crash')),
    error_detail TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reconciliation_audit_sweep_id
    ON reconciliation_audit_log(sweep_trace_id);

CREATE INDEX IF NOT EXISTS idx_reconciliation_audit_orphan_check
    ON reconciliation_audit_log(phase, outcome);

CREATE INDEX IF NOT EXISTS idx_reconciliation_audit_created_at
    ON reconciliation_audit_log(created_at);
