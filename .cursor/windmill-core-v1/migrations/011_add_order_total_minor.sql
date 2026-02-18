BEGIN;

ALTER TABLE order_ledger
    ADD COLUMN IF NOT EXISTS order_total_minor BIGINT NULL;

UPDATE order_ledger
SET order_total_minor = ROUND((metadata->>'totalAmount')::numeric * 100)
WHERE metadata->>'totalAmount' IS NOT NULL
  AND metadata->>'totalAmount' ~ '^-?[0-9]+(\.[0-9]+)?$'
  AND order_total_minor IS NULL;

COMMIT;
