-- Migration: 001_create_tasks_table.sql
-- Purpose: Minimal operational spine for RFQ pipeline
-- Date: 2026-02-12
--
-- MINIMAL OPERATIONAL SPINE — DO NOT EXTEND
-- This table provides trace_id tracking and replay capability.
-- Do NOT add workflow engine, DLQ, or complex orchestration.

-- Create tasks table
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY,
    trace_id UUID NOT NULL,
    task_type TEXT NOT NULL,  -- e.g. "rfq_v1"
    status TEXT NOT NULL,      -- new | processing | done | failed
    payload JSONB NOT NULL,
    error TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_tasks_trace_id ON tasks(trace_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

-- Add comment to table
COMMENT ON TABLE tasks IS 'Minimal operational spine for task tracking and replay. DO NOT EXTEND.';
COMMENT ON COLUMN tasks.trace_id IS 'Unique identifier for tracing task execution across systems';
COMMENT ON COLUMN tasks.task_type IS 'Type of task (e.g., rfq_v1, order_processing)';
COMMENT ON COLUMN tasks.status IS 'Task status: new | processing | done | failed';
COMMENT ON COLUMN tasks.payload IS 'Original task payload for replay capability';
COMMENT ON COLUMN tasks.error IS 'Error message if task failed';
