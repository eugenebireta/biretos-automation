BEGIN;

DO $$
DECLARE
    _child_tables  TEXT[] := ARRAY[
        'payment_transactions', 'shipments', 'documents',
        'order_line_items', 'reservations', 'reservations'
    ];
    _child_cols    TEXT[] := ARRAY[
        'order_id', 'order_id', 'order_id',
        'order_id', 'order_id', 'line_item_id'
    ];
    _parent_tables TEXT[] := ARRAY[
        'order_ledger', 'order_ledger', 'order_ledger',
        'order_ledger', 'order_ledger', 'order_line_items'
    ];
    _parent_cols   TEXT[] := ARRAY[
        'order_id', 'order_id', 'order_id',
        'order_id', 'order_id', 'id'
    ];
    _i     INT;
    _cname TEXT;
BEGIN
    FOR _i IN 1 .. array_length(_child_tables, 1) LOOP
        SELECT con.conname INTO _cname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        WHERE rel.relname = _child_tables[_i]
          AND con.contype = 'f'
          AND con.confrelid = (SELECT oid FROM pg_class WHERE relname = _parent_tables[_i])
          AND EXISTS (
              SELECT 1
              FROM unnest(con.conkey) k
              JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k
              WHERE a.attname = _child_cols[_i]
          );

        IF _cname IS NOT NULL THEN
            EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', _child_tables[_i], _cname);
        END IF;

        EXECUTE format(
            'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES %I(%I) ON DELETE RESTRICT',
            _child_tables[_i],
            _child_tables[_i] || '_' || _child_cols[_i] || '_fkey',
            _child_cols[_i],
            _parent_tables[_i],
            _parent_cols[_i]
        );
    END LOOP;
END $$;

COMMIT;
