-- Create mock order_ledger entry for testing
INSERT INTO order_ledger (
    order_id,
    insales_order_id,
    invoice_request_key,
    state,
    customer_data,
    metadata,
    state_history
) VALUES (
    gen_random_uuid(),
    'TEST-001',
    'test-key-001',
    'pending',
    '{"companyName": "Тестовая Компания", "name": "Иван Иванов"}'::jsonb,
    '{"invoiceNumber": "INV-001", "totalAmount": 10000}'::jsonb,
    '[]'::jsonb
)
ON CONFLICT (insales_order_id) DO NOTHING
RETURNING order_id, insales_order_id;






















