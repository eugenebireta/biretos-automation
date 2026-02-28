-- Migration: 017_create_reconciliation_suppressions.sql
-- Purpose: Reconciliation Architecture v2 (P0) — suppression/ack state for reconciliation escalations
-- Notes: Plain SQL only; idempotent via IF NOT EXISTS. Assumes review_cases exists (migration 015 depends on it).

CREATE TABLE IF NOT EXISTS reconciliation_suppressions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    check_code TEXT NOT NULL,
    suppression_state TEXT NOT NULL CHECK (suppression_state IN ('active', 'expired')),
    reason TEXT NOT NULL CHECK (reason IN ('wont_fix', 'manual_resolved', 'snooze')),
    expires_at TIMESTAMPTZ NULL,
    governance_case_id UUID NULL REFERENCES review_cases(id) ON DELETE SET NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_reconciliation_suppressions_active_unique
    ON reconciliation_suppressions(entity_type, entity_id, check_code)
    WHERE suppression_state = 'active';

CREATE INDEX IF NOT EXISTS idx_reconciliation_suppressions_expires_at
    ON reconciliation_suppressions(expires_at)
    WHERE suppression_state = 'active';
