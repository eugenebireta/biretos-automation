-- Phase C: inbound event store for Shopware webhook gateway.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS shopware_inbound_events (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance          TEXT NOT NULL CHECK (instance IN ('ru', 'int')),
    event_id          TEXT NOT NULL UNIQUE,
    event_type        TEXT NOT NULL,
    payload           JSONB NOT NULL,
    idempotency_key   TEXT NOT NULL UNIQUE,
    trace_id          UUID NOT NULL,
    processing_status TEXT NOT NULL DEFAULT 'queued'
        CHECK (processing_status IN ('queued', 'processed', 'failed')),
    error_text        TEXT NULL,
    received_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at      TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS ix_shopware_inbound_events_instance_received
    ON shopware_inbound_events (instance, received_at);

CREATE INDEX IF NOT EXISTS ix_shopware_inbound_events_status_received
    ON shopware_inbound_events (processing_status, received_at);
