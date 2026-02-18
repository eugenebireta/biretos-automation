-- H2: Index action_idempotency_log(trace_id) for faster trace-based debugging.
--
-- Use CONCURRENTLY to avoid long blocking on large tables in production.
-- IMPORTANT: Postgres forbids CREATE INDEX CONCURRENTLY inside a transaction block,
-- so this migration must NOT wrap the statement in BEGIN/COMMIT.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ail_trace_id
    ON action_idempotency_log (trace_id);

