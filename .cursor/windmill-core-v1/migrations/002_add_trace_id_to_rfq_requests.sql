-- Migration: 002_add_trace_id_to_rfq_requests.sql
-- Purpose: Add trace-based idempotency boundary for RFQ requests
-- Date: 2026-02-13

ALTER TABLE rfq_requests
    ADD COLUMN IF NOT EXISTS trace_id UUID;

-- NOTE:
-- CREATE INDEX CONCURRENTLY must run outside transaction blocks.
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_rfq_requests_trace_id
    ON rfq_requests(trace_id)
    WHERE trace_id IS NOT NULL;
