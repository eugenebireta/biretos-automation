BEGIN;

ALTER TABLE shadow_rag_log
    ADD COLUMN IF NOT EXISTS raw_text_hash TEXT,
    ADD COLUMN IF NOT EXISTS entities JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS confidence NUMERIC,
    ADD COLUMN IF NOT EXISTS model_version TEXT,
    ADD COLUMN IF NOT EXISTS prompt_version TEXT,
    ADD COLUMN IF NOT EXISTS parse_duration_ms INTEGER;

CREATE INDEX IF NOT EXISTS idx_shadow_rag_log_intent_created
    ON shadow_rag_log (intent_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_shadow_rag_log_raw_text_hash
    ON shadow_rag_log (raw_text_hash)
    WHERE raw_text_hash IS NOT NULL;

COMMIT;
