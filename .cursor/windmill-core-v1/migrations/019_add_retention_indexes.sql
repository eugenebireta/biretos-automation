-- Migration: 019_add_retention_indexes.sql
-- Purpose: Retention indexes for reconciliation infrastructure tables (Option A)
-- Notes: Plain SQL only; idempotent via IF NOT EXISTS. Run manually via psql.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reconciliation_alerts_retention
    ON reconciliation_alerts(created_at)
    WHERE notification_state IN ('sent', 'acked');

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reconciliation_suppressions_retention
    ON reconciliation_suppressions(expires_at)
    WHERE suppression_state = 'expired';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reconciliation_suppressions_retention_null
    ON reconciliation_suppressions(created_at)
    WHERE suppression_state = 'expired' AND expires_at IS NULL;

