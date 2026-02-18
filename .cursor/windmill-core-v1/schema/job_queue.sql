-- Windmill Execution Core v1 - Job Queue Schema
-- PostgreSQL job queue для минимального execution core

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

