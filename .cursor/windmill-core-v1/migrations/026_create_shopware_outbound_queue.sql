-- Phase C: outbound queue for Core -> Shopware synchronization.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS shopware_outbound_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance        TEXT NOT NULL CHECK (instance IN ('ru', 'int')),
    entity_type     TEXT NOT NULL CHECK (entity_type IN ('product', 'price', 'stock', 'order_status')),
    entity_id       TEXT NOT NULL,
    payload         JSONB NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'confirmed', 'failed')),
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    next_retry_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error      TEXT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    trace_id        UUID NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_shopware_outbound_queue_status_retry
    ON shopware_outbound_queue (status, next_retry_at);

CREATE INDEX IF NOT EXISTS ix_shopware_outbound_queue_instance_entity
    ON shopware_outbound_queue (instance, entity_type, entity_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trigger_shopware_outbound_queue_updated_at'
    ) THEN
        CREATE TRIGGER trigger_shopware_outbound_queue_updated_at
            BEFORE UPDATE ON shopware_outbound_queue
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at_timestamp();
    END IF;
END
$$;
