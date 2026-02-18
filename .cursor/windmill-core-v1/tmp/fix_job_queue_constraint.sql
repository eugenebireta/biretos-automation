-- Проверка и исправление constraint на job_queue.status

-- 1. Проверяем текущий constraint
SELECT conname, pg_get_constraintdef(oid) 
FROM pg_constraint 
WHERE conrelid = 'job_queue'::regclass 
  AND contype = 'c'
  AND conname LIKE '%status%';

-- 2. Удаляем старый constraint (если есть неправильный)
DO $$
BEGIN
    -- Пытаемся удалить constraint, если он существует
    ALTER TABLE job_queue DROP CONSTRAINT IF EXISTS job_queue_status_check;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Constraint не найден или уже удален';
END $$;

-- 3. Создаем правильный constraint
ALTER TABLE job_queue 
ADD CONSTRAINT job_queue_status_check 
CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'dispatched'));

-- 4. Проверяем результат
SELECT conname, pg_get_constraintdef(oid) 
FROM pg_constraint 
WHERE conrelid = 'job_queue'::regclass 
  AND contype = 'c'
  AND conname LIKE '%status%';














