DO $$
DECLARE
    _constraint_name TEXT;
BEGIN
    -- Drop any CHECK constraints on review_cases that reference "status".
    FOR _constraint_name IN (
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace ns ON ns.oid = rel.relnamespace
        WHERE rel.relname = 'review_cases'
          AND con.contype = 'c'
          AND pg_get_constraintdef(con.oid) LIKE '%status%'
    ) LOOP
        EXECUTE format('ALTER TABLE review_cases DROP CONSTRAINT %I', _constraint_name);
    END LOOP;

    ALTER TABLE review_cases
    ADD CONSTRAINT review_cases_status_check
    CHECK (
        status IN (
            'open',
            'assigned',
            'approved',
            'executing',
            'executed',
            'rejected',
            'expired',
            'cancelled'
        )
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
