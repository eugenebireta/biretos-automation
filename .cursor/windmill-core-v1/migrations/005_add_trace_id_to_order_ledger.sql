BEGIN;

ALTER TABLE order_ledger
    ADD COLUMN IF NOT EXISTS trace_id UUID;

CREATE INDEX IF NOT EXISTS idx_order_ledger_trace_id
    ON order_ledger (trace_id)
    WHERE trace_id IS NOT NULL;

COMMIT;
