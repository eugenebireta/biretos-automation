BEGIN;

-- Phase 2 (v2.1): additive order_ledger columns for explicit transition timestamps.
ALTER TABLE order_ledger
    ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS payment_status TEXT NOT NULL DEFAULT 'unpaid',
    ADD COLUMN IF NOT EXISTS payment_status_changed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1;

ALTER TABLE order_ledger
    DROP CONSTRAINT IF EXISTS order_ledger_payment_status_check;

ALTER TABLE order_ledger
    ADD CONSTRAINT order_ledger_payment_status_check
    CHECK (payment_status IN ('unpaid', 'partially_paid', 'paid', 'overpaid', 'refund_pending', 'refunded'));

CREATE INDEX IF NOT EXISTS idx_order_ledger_payment_status
    ON order_ledger(payment_status);

CREATE INDEX IF NOT EXISTS idx_order_ledger_status_changed_at
    ON order_ledger(status_changed_at DESC)
    WHERE status_changed_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_order_ledger_payment_status_changed_at
    ON order_ledger(payment_status_changed_at DESC)
    WHERE payment_status_changed_at IS NOT NULL;

-- Phase 2 (v2.1): canonical line items for allocation/unpack tracking.
CREATE TABLE IF NOT EXISTS order_line_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES order_ledger(order_id) ON DELETE CASCADE,
    line_seq INTEGER NOT NULL,
    product_id UUID NULL,
    sku_snapshot TEXT NOT NULL,
    name_snapshot TEXT NOT NULL,
    attributes_snapshot JSONB NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    price_unit_minor BIGINT NOT NULL,
    tax_rate_bps INTEGER NOT NULL DEFAULT 0,
    line_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (line_status IN ('pending', 'reserved', 'allocated', 'shipped', 'delivered', 'cancelled', 'backordered')),
    supplier_ref TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (order_id, line_seq)
);

CREATE INDEX IF NOT EXISTS idx_order_line_items_order
    ON order_line_items(order_id, line_seq);

CREATE INDEX IF NOT EXISTS idx_order_line_items_status
    ON order_line_items(line_status);

-- Phase 2 (v2.1): 1:N shipments model. order_ledger.cdek_uuid remains a legacy cache.
CREATE TABLE IF NOT EXISTS shipments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES order_ledger(order_id) ON DELETE CASCADE,
    trace_id UUID NULL,
    shipment_seq INTEGER NOT NULL CHECK (shipment_seq > 0),
    carrier_code TEXT NOT NULL,
    carrier_external_id TEXT NULL,
    service_tariff TEXT NULL,
    current_status TEXT NOT NULL
        CHECK (current_status IN ('created', 'label_ready', 'handed_over', 'in_transit', 'delivered', 'exception', 'returned', 'cancelled')),
    status_changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cost_quoted_minor BIGINT NULL,
    cost_actual_minor BIGINT NULL,
    cost_currency TEXT NULL,
    packages JSONB NOT NULL DEFAULT '[]'::jsonb,
    address_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    status_history JSONB NOT NULL DEFAULT '[]'::jsonb,
    carrier_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (order_id, shipment_seq)
);

CREATE INDEX IF NOT EXISTS idx_shipments_order_status
    ON shipments(order_id, current_status, shipment_seq DESC);

CREATE INDEX IF NOT EXISTS idx_shipments_carrier_external
    ON shipments(carrier_code, carrier_external_id)
    WHERE carrier_external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_shipments_trace_id
    ON shipments(trace_id)
    WHERE trace_id IS NOT NULL;

COMMIT;
