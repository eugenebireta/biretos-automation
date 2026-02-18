CREATE TABLE IF NOT EXISTS shopware_operations (
    id UUID PRIMARY KEY,
    product_number TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    attempt INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE shopware_operations
    ADD COLUMN IF NOT EXISTS attempt INTEGER NOT NULL DEFAULT 0;

ALTER TABLE shopware_operations
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE UNIQUE INDEX IF NOT EXISTS ux_shopware_product_hash
   ON shopware_operations (product_number, content_hash);

CREATE INDEX IF NOT EXISTS ix_shopware_status_created
   ON shopware_operations (status, created_at);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_proc
        WHERE proname = 'set_updated_at_timestamp'
    ) THEN
        CREATE FUNCTION set_updated_at_timestamp()
        RETURNS TRIGGER AS $func$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $func$ LANGUAGE plpgsql;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trigger_shopware_operations_updated_at'
    ) THEN
        CREATE TRIGGER trigger_shopware_operations_updated_at
            BEFORE UPDATE ON shopware_operations
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at_timestamp();
    END IF;
END
$$;
