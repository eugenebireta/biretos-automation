-- Migration: 022_create_alert_telegram_log.sql
-- Purpose: Phase 4.1 Alerting — Telegram alert delivery log (Tier-3)
-- Scope: Tier-3 alerting table only; no DDL on Core or reconciliation_* tables.
-- Notes: Uses UUID + gen_random_uuid() convention with explicit pgcrypto extension safety.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS alert_telegram_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    check_code          TEXT NOT NULL,
    entity_id           TEXT NOT NULL,
    severity            TEXT NOT NULL,
    verdict             TEXT NOT NULL,
    message_text        TEXT NOT NULL,
    chat_id             BIGINT NOT NULL,
    telegram_message_id BIGINT NULL,
    trace_id            UUID NOT NULL,
    cooldown_key        TEXT NOT NULL UNIQUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at             TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_alert_telegram_log_cooldown_key
    ON alert_telegram_log(cooldown_key);

CREATE INDEX IF NOT EXISTS idx_alert_telegram_log_created_at
    ON alert_telegram_log(created_at);
