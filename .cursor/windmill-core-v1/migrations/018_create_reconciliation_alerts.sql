-- Migration: 018_create_reconciliation_alerts.sql
-- Purpose: Reconciliation Architecture v2 (P1) — L3 structural check alerts (idempotent, anti-spam)
-- Notes: Plain SQL only; idempotent via IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS reconciliation_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sweep_trace_id UUID NOT NULL,
    check_code TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM')),
    verdict_snapshot JSONB NOT NULL,
    notification_state TEXT NOT NULL DEFAULT 'pending' CHECK (notification_state IN ('pending', 'sent', 'acked')),
    notification_key TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ NULL,
    acked_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_reconciliation_alerts_pending
    ON reconciliation_alerts(notification_state)
    WHERE notification_state = 'pending';
