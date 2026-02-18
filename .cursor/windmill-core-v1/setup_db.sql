-- Setup script for biretos_automation database
-- Run as: psql -U postgres -d biretos_automation -f setup_db.sql

-- Job Queue Schema
CREATE TABLE IF NOT EXISTS job_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'dispatched')),
    idempotency_key TEXT UNIQUE,
    job_token UUID,
    dispatched_at TIMESTAMPTZ,
    result JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    error TEXT
);

-- Индексы для эффективного polling
CREATE INDEX IF NOT EXISTS idx_job_queue_status_created 
    ON job_queue(status, created_at) 
    WHERE status IN ('pending', 'failed', 'dispatched');

CREATE INDEX IF NOT EXISTS idx_job_queue_idempotency 
    ON job_queue(idempotency_key) 
    WHERE idempotency_key IS NOT NULL;

-- Функция для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_job_queue_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_job_queue_updated_at
    BEFORE UPDATE ON job_queue
    FOR EACH ROW
    EXECUTE FUNCTION update_job_queue_updated_at();

-- Order Ledger Schema
CREATE TABLE IF NOT EXISTS order_ledger (
    order_id UUID PRIMARY KEY,
    insales_order_id TEXT UNIQUE NOT NULL,
    invoice_request_key TEXT UNIQUE NOT NULL,
    tbank_invoice_id TEXT UNIQUE,
    cdek_uuid TEXT UNIQUE,
    tbank_consignment_id TEXT UNIQUE,
    state TEXT NOT NULL,
    state_history JSONB NOT NULL DEFAULT '[]'::JSONB,
    customer_data JSONB,
    delivery_data JSONB,
    error_log JSONB NOT NULL DEFAULT '[]'::JSONB,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_order_ledger_tbank_invoice
    ON order_ledger (tbank_invoice_id);

CREATE INDEX IF NOT EXISTS idx_order_ledger_state
    ON order_ledger (state);

CREATE INDEX IF NOT EXISTS idx_order_ledger_updated_at
    ON order_ledger (updated_at);

-- Grant permissions to biretos_user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO biretos_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO biretos_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO biretos_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO biretos_user;






















