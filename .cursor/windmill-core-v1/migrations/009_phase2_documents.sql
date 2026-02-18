BEGIN;

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES order_ledger(order_id) ON DELETE CASCADE,
    trace_id UUID NULL,
    document_type TEXT NOT NULL
        CHECK (document_type IN ('invoice', 'upd', 'waybill', 'act', 'credit_note')),
    document_number TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    status TEXT NOT NULL CHECK (status IN ('draft', 'issued', 'sent', 'cancelled', 'superseded')),
    provider_code TEXT NULL,
    provider_document_id TEXT NULL,
    generation_key TEXT UNIQUE NOT NULL,
    hash_algorithm_version TEXT NOT NULL DEFAULT 'v1',
    amount_minor BIGINT NULL,
    currency TEXT NULL,
    content_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    pdf_url TEXT NULL,
    raw_provider_response JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_number, revision)
);

CREATE INDEX IF NOT EXISTS idx_documents_order_type_status
    ON documents(order_id, document_type, status, revision DESC);

CREATE INDEX IF NOT EXISTS idx_documents_trace_id
    ON documents(trace_id)
    WHERE trace_id IS NOT NULL;

COMMIT;
