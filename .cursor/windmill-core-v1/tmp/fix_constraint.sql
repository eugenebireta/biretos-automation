-- Исправление constraint на job_queue.status
-- Удаляем старый constraint с пробелами
ALTER TABLE job_queue DROP CONSTRAINT IF EXISTS job_queue_status_check;

-- Создаем правильный constraint без пробелов
ALTER TABLE job_queue ADD CONSTRAINT job_queue_status_check 
CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'dispatched'));














