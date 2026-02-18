-- RFQ Execution Core Business v1 - RFQ Tables
-- Таблицы для хранения RFQ запросов и элементов

CREATE TABLE IF NOT EXISTS rfq_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source TEXT NOT NULL,  -- telegram, email, manual
    raw_text TEXT,
    parsed_json JSONB,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'processed', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_rfq_requests_created_at 
    ON rfq_requests(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rfq_requests_status 
    ON rfq_requests(status);

CREATE TABLE IF NOT EXISTS rfq_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rfq_id UUID NOT NULL REFERENCES rfq_requests(id) ON DELETE CASCADE,
    line_no INTEGER NOT NULL,
    part_number TEXT,
    qty INTEGER,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rfq_items_rfq_id 
    ON rfq_items(rfq_id);

CREATE INDEX IF NOT EXISTS idx_rfq_items_part_number 
    ON rfq_items(part_number) 
    WHERE part_number IS NOT NULL;






















