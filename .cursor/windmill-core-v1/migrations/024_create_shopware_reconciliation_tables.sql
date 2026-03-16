-- RC-8: Shopware sync reconciliation artifacts (Tier-3 safety telemetry)
-- Scope: creates dedicated RC-8 tables; does not modify reconciliation_* tables.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS shopware_reconciliation_audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        UUID NOT NULL,
    instance        TEXT NOT NULL,
    check_code      TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    core_value      JSONB NOT NULL,
    external_value  JSONB NOT NULL,
    drift_value     NUMERIC NULL,
    severity        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shopware_rc8_audit_trace
    ON shopware_reconciliation_audit_log(trace_id);

CREATE INDEX IF NOT EXISTS idx_shopware_rc8_audit_created
    ON shopware_reconciliation_audit_log(created_at);

CREATE INDEX IF NOT EXISTS idx_shopware_rc8_audit_instance_check
    ON shopware_reconciliation_audit_log(instance, check_code);

CREATE TABLE IF NOT EXISTS shopware_reconciliation_alerts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id            UUID NOT NULL,
    instance            TEXT NOT NULL,
    check_code          TEXT NOT NULL,
    severity            TEXT NOT NULL,
    message_text        TEXT NOT NULL,
    cooldown_key        TEXT NOT NULL UNIQUE,
    notification_state  TEXT NOT NULL DEFAULT 'pending',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shopware_rc8_alerts_created
    ON shopware_reconciliation_alerts(created_at);

CREATE INDEX IF NOT EXISTS idx_shopware_rc8_alerts_state
    ON shopware_reconciliation_alerts(notification_state);
