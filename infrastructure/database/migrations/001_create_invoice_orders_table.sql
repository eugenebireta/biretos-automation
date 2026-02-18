-- Migration: Create invoice_orders table
-- Description: Таблица для хранения связи invoice_id ↔ order_id
-- Author: Biretos Automation
-- Date: 2025-01-15

CREATE TABLE IF NOT EXISTS invoice_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tbank_invoice_id VARCHAR(255) NOT NULL UNIQUE,
    internal_order_id UUID NOT NULL UNIQUE,
    insales_order_id INTEGER,
    source VARCHAR(50) NOT NULL DEFAULT 'tbank',
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    metadata JSONB,
    CONSTRAINT invoice_orders_tbank_invoice_id_key UNIQUE (tbank_invoice_id)
);

-- Индексы для оптимизации запросов
CREATE INDEX IF NOT EXISTS idx_invoice_orders_tbank_invoice_id ON invoice_orders(tbank_invoice_id);
CREATE INDEX IF NOT EXISTS idx_invoice_orders_insales_order_id ON invoice_orders(insales_order_id);
CREATE INDEX IF NOT EXISTS idx_invoice_orders_status ON invoice_orders(status);
CREATE INDEX IF NOT EXISTS idx_invoice_orders_created_at ON invoice_orders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_invoice_orders_source ON invoice_orders(source);

-- Комментарии к таблице и полям
COMMENT ON TABLE invoice_orders IS 'Хранение связи между счетами внешних провайдеров и заказами в InSales';
COMMENT ON COLUMN invoice_orders.tbank_invoice_id IS 'ID счёта от Т-Банка (UNIQUE для идемпотентности)';
COMMENT ON COLUMN invoice_orders.internal_order_id IS 'Внутренний UUID заказа (для ссылок между системами)';
COMMENT ON COLUMN invoice_orders.insales_order_id IS 'ID заказа в InSales (может быть NULL, если создание не удалось)';
COMMENT ON COLUMN invoice_orders.source IS 'Источник события (tbank, alphabank, cdek, и т.д.)';
COMMENT ON COLUMN invoice_orders.status IS 'Статус обработки: pending, created, failed';
COMMENT ON COLUMN invoice_orders.metadata IS 'JSONB с полным payload и дополнительными данными для аудита';








