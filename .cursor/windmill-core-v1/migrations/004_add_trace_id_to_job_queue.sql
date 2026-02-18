BEGIN;

ALTER TABLE job_queue
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

ALTER TABLE job_queue
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

ALTER TABLE job_queue
    ADD COLUMN IF NOT EXISTS trace_id UUID;

CREATE INDEX IF NOT EXISTS idx_job_queue_trace_id
    ON job_queue (trace_id)
    WHERE trace_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_job_queue_processing_updated_at
    ON job_queue (status, updated_at)
    WHERE status = 'processing';

CREATE OR REPLACE FUNCTION update_job_queue_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trigger_job_queue_updated_at'
    ) THEN
        CREATE TRIGGER trigger_job_queue_updated_at
            BEFORE UPDATE ON job_queue
            FOR EACH ROW
            EXECUTE FUNCTION update_job_queue_updated_at();
    END IF;
END
$$;

COMMIT;
