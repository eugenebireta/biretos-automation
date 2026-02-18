BEGIN;

CREATE TABLE IF NOT EXISTS payment_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES order_ledger(order_id) ON DELETE CASCADE,
    trace_id UUID NULL,
    transaction_type TEXT NOT NULL
        CHECK (transaction_type IN ('charge', 'refund', 'chargeback', 'adjustment')),
    provider_code TEXT NOT NULL,
    provider_transaction_id TEXT NOT NULL,
    amount_minor BIGINT NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'confirmed', 'failed', 'reversed')),
    status_changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    idempotency_key TEXT UNIQUE NOT NULL,
    raw_provider_response JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_payment_transactions_provider_ref
    ON payment_transactions(provider_code, provider_transaction_id);

CREATE INDEX IF NOT EXISTS idx_payment_transactions_order_status
    ON payment_transactions(order_id, status, transaction_type);

CREATE INDEX IF NOT EXISTS idx_payment_transactions_trace_id
    ON payment_transactions(trace_id)
    WHERE trace_id IS NOT NULL;

COMMIT;
