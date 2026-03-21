-- Migration 028: Backoffice Task Engine — Phase 6
-- Three new tables: employee_actions_log, external_read_snapshots, shadow_rag_log
-- These are NOT reconciliation_* tables. No Core tables touched.

-- 6.3: Audit log of all employee backoffice actions
CREATE TABLE IF NOT EXISTS employee_actions_log (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id         UUID        NOT NULL,
    idempotency_key  TEXT        NOT NULL,
    employee_id      TEXT        NOT NULL,
    employee_role    TEXT        NOT NULL,
    intent_type      TEXT        NOT NULL,   -- check_payment | get_tracking | get_waybill
    risk_level       TEXT        NOT NULL,   -- LOW | MEDIUM | HIGH
    payload_snapshot JSONB       NOT NULL,
    context_snapshot JSONB       NOT NULL,   -- rate window state, active cases at call time
    outcome          TEXT,                   -- success | blocked | rate_limited | forbidden
    outcome_detail   JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT employee_actions_log_idem UNIQUE (idempotency_key)
);
CREATE INDEX IF NOT EXISTS employee_actions_log_employee_ts
    ON employee_actions_log (employee_id, created_at DESC);
CREATE INDEX IF NOT EXISTS employee_actions_log_intent_ts
    ON employee_actions_log (employee_id, intent_type, created_at DESC);

-- 6.8: Snapshot of every external read (INV-ERS invariant)
CREATE TABLE IF NOT EXISTS external_read_snapshots (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id      UUID        NOT NULL,
    snapshot_key  TEXT        NOT NULL,   -- "{provider}:{entity_type}:{entity_id}"
    provider      TEXT        NOT NULL,   -- tbank | cdek | edo
    entity_type   TEXT        NOT NULL,
    entity_id     TEXT        NOT NULL,
    snapshot_data JSONB       NOT NULL,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ext_read_snap_unique UNIQUE (trace_id, snapshot_key)
);
CREATE INDEX IF NOT EXISTS external_read_snapshots_trace
    ON external_read_snapshots (trace_id);

-- 6.9: Shadow log for future RAG / AI assistant training
CREATE TABLE IF NOT EXISTS shadow_rag_log (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id         UUID        NOT NULL,
    employee_id      TEXT        NOT NULL,
    intent_type      TEXT        NOT NULL,
    context_json     JSONB       NOT NULL,   -- full context snapshot for RAG
    response_summary TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS shadow_rag_log_employee_ts
    ON shadow_rag_log (employee_id, created_at DESC);
