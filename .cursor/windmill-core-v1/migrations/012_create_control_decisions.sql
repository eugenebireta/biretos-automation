BEGIN;

CREATE TABLE IF NOT EXISTS control_decisions (
    id BIGSERIAL,
    trace_id UUID NULL,
    decision_seq INTEGER NOT NULL CHECK (decision_seq >= 1),
    gate_name TEXT NOT NULL,
    verdict TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    decision_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    reference_snapshot JSONB NULL,
    replay_config_status TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

DO $$
DECLARE
    start_month DATE := date_trunc('month', CURRENT_DATE)::date;
    next_month DATE := (date_trunc('month', CURRENT_DATE) + INTERVAL '1 month')::date;
    after_next_month DATE := (date_trunc('month', CURRENT_DATE) + INTERVAL '2 month')::date;
    part_this_month TEXT := 'control_decisions_' || to_char(start_month, 'YYYYMM');
    part_next_month TEXT := 'control_decisions_' || to_char(next_month, 'YYYYMM');
BEGIN
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF control_decisions
         FOR VALUES FROM (%L) TO (%L)',
        part_this_month,
        start_month,
        next_month
    );

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF control_decisions
         FOR VALUES FROM (%L) TO (%L)',
        part_next_month,
        next_month,
        after_next_month
    );
END $$;

CREATE INDEX IF NOT EXISTS idx_control_decisions_trace_created
    ON control_decisions (trace_id, created_at DESC)
    WHERE trace_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_control_decisions_gate_created
    ON control_decisions (gate_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_control_decisions_policy_hash
    ON control_decisions (policy_hash);

CREATE UNIQUE INDEX IF NOT EXISTS idx_control_decisions_trace_seq_created
    ON control_decisions (trace_id, decision_seq, created_at)
    WHERE trace_id IS NOT NULL;

COMMIT;
