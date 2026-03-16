CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS shopware_media_map (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_number TEXT NOT NULL,
    media_url TEXT NOT NULL,
    shopware_media_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_shopware_media_map_product_url
    ON shopware_media_map (product_number, media_url);

CREATE INDEX IF NOT EXISTS ix_shopware_media_map_product
    ON shopware_media_map (product_number);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trigger_shopware_media_map_updated_at'
    ) THEN
        CREATE TRIGGER trigger_shopware_media_map_updated_at
            BEFORE UPDATE ON shopware_media_map
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at_timestamp();
    END IF;
END
$$;
