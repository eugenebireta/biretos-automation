-- Migration: добавление полей для Local PC worker polling
-- Если таблица job_queue уже существует, выполнить этот файл для обновления

-- Добавляем статус 'dispatched' в CHECK constraint
ALTER TABLE job_queue DROP CONSTRAINT IF EXISTS job_queue_status_check;
ALTER TABLE job_queue ADD CONSTRAINT job_queue_status_check 
    CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'dispatched'));

-- Добавляем поле job_token (UUID)
ALTER TABLE job_queue ADD COLUMN IF NOT EXISTS job_token UUID;

-- Добавляем поле dispatched_at (TIMESTAMPTZ)
ALTER TABLE job_queue ADD COLUMN IF NOT EXISTS dispatched_at TIMESTAMPTZ;

-- Обновляем индекс для включения статуса 'dispatched'
DROP INDEX IF EXISTS idx_job_queue_status_created;
CREATE INDEX IF NOT EXISTS idx_job_queue_status_created 
    ON job_queue(status, created_at) 
    WHERE status IN ('pending', 'failed', 'dispatched');

-- Добавляем поле result JSONB (для хранения результатов выполнения)
ALTER TABLE job_queue ADD COLUMN IF NOT EXISTS result JSONB;

