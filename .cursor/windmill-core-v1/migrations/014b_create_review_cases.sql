BEGIN;

CREATE TABLE IF NOT EXISTS review_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id UUID NOT NULL,
    order_id UUID NULL,
    gate_name TEXT NOT NULL,
    original_verdict TEXT NOT NULL,
    original_decision_seq INTEGER NOT NULL CHECK (original_decision_seq >= 0),
    policy_hash TEXT NOT NULL,
    action_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    resume_context JSONB NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'assigned', 'approved', 'executing', 'executed', 'rejected', 'expired', 'cancelled')),
    sla_deadline_at TIMESTAMPTZ NULL,
    escalation_level INTEGER NOT NULL DEFAULT 0 CHECK (escalation_level >= 0),
    idempotency_key TEXT NOT NULL,
    assigned_to TEXT NULL,
    assigned_at TIMESTAMPTZ NULL,
    resolved_at TIMESTAMPTZ NULL,
    resolved_by TEXT NULL,
    resolution_decision_seq INTEGER NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_review_cases_trace_created
    ON review_cases (trace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_review_cases_status_deadline
    ON review_cases (status, sla_deadline_at)
    WHERE status IN ('open', 'assigned', 'approved', 'executing');

CREATE INDEX IF NOT EXISTS idx_review_cases_order
    ON review_cases (order_id, created_at DESC)
    WHERE order_id IS NOT NULL;

COMMIT;
