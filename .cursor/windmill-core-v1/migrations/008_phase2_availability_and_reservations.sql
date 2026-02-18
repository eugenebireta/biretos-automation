BEGIN;

CREATE TABLE IF NOT EXISTS availability_snapshot (
    product_id UUID NOT NULL,
    warehouse_code TEXT NOT NULL,
    sku TEXT NOT NULL,
    quantity_on_hand INTEGER NOT NULL DEFAULT 0,
    quantity_reserved INTEGER NOT NULL DEFAULT 0,
    quantity_available INTEGER NOT NULL DEFAULT 0,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (product_id, warehouse_code),
    CHECK (quantity_on_hand >= 0),
    CHECK (quantity_reserved >= 0)
);

CREATE INDEX IF NOT EXISTS idx_availability_snapshot_sku
    ON availability_snapshot(sku, warehouse_code);

CREATE TABLE IF NOT EXISTS stock_ledger_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL,
    sku TEXT NOT NULL,
    warehouse_code TEXT NOT NULL,
    change_type TEXT NOT NULL
        CHECK (change_type IN ('receipt', 'sale', 'adjustment', 'reservation', 'release', 'return')),
    quantity_delta INTEGER NOT NULL,
    reference_type TEXT NOT NULL,
    reference_id UUID NULL,
    trace_id UUID NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stock_ledger_product_warehouse
    ON stock_ledger_entries(product_id, warehouse_code, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_stock_ledger_reference
    ON stock_ledger_entries(reference_type, reference_id);

CREATE INDEX IF NOT EXISTS idx_stock_ledger_trace_id
    ON stock_ledger_entries(trace_id)
    WHERE trace_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES order_ledger(order_id) ON DELETE CASCADE,
    line_item_id UUID NOT NULL REFERENCES order_line_items(id) ON DELETE CASCADE,
    product_id UUID NOT NULL,
    sku_snapshot TEXT NOT NULL,
    warehouse_code TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    status TEXT NOT NULL CHECK (status IN ('active', 'released', 'converted', 'expired')),
    fulfillment_event_id UUID NOT NULL,
    trace_id UUID NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    released_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_reservations_order_line_status
    ON reservations(order_id, line_item_id, status);

CREATE INDEX IF NOT EXISTS idx_reservations_product_warehouse_status
    ON reservations(product_id, warehouse_code, status);

CREATE INDEX IF NOT EXISTS idx_reservations_trace_id
    ON reservations(trace_id)
    WHERE trace_id IS NOT NULL;

COMMIT;
