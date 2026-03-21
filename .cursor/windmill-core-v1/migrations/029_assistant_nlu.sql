-- Migration 029: AI Executive Assistant NLU tables. Phase 7.
-- Two tables: nlu_pending_confirmations (INV-MBC) + nlu_sla_log (7.8).

-- ---------------------------------------------------------------------------
-- NLU pending confirmations (TTL 5 min, atomically consumed)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nlu_pending_confirmations (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        TEXT        NOT NULL,
    employee_id     TEXT        NOT NULL,
    employee_role   TEXT        NOT NULL DEFAULT 'operator',
    parsed_intent_type TEXT     NOT NULL,
    parsed_entities JSONB       NOT NULL DEFAULT '{}',
    model_version   TEXT        NOT NULL DEFAULT '',
    prompt_version  TEXT        NOT NULL DEFAULT '',
    confidence      NUMERIC(5,4),
    status          TEXT        NOT NULL DEFAULT 'pending',
    expires_at      TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '5 minutes',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_nlu_confirm_status
        CHECK (status IN ('pending', 'confirmed', 'expired', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_nlu_pending_expires
    ON nlu_pending_confirmations(expires_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_nlu_pending_employee
    ON nlu_pending_confirmations(employee_id, created_at);

-- ---------------------------------------------------------------------------
-- NLU SLA log (append-only, retention 90 days)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nlu_sla_log (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id            TEXT        NOT NULL,
    employee_id         TEXT        NOT NULL,
    intent_type         TEXT,
    model_version       TEXT,
    prompt_version      TEXT,
    degradation_level   SMALLINT    NOT NULL DEFAULT 0,
    parse_duration_ms   INTEGER,
    total_duration_ms   INTEGER,
    status              TEXT        NOT NULL,   -- ok/fallback/failed/shadow/button_only/injection_rejected
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nlu_sla_created
    ON nlu_sla_log(created_at);

CREATE INDEX IF NOT EXISTS idx_nlu_sla_employee
    ON nlu_sla_log(employee_id, created_at);
