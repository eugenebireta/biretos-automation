# Database Migrations

This directory contains SQL migrations for the windmill-core-v1 database.

## Running Migrations

Migrations should be run manually in order:

```bash
psql -h <host> -U <user> -d <database> -f 001_create_tasks_table.sql
psql -h <host> -U <user> -d <database> -f 002_add_trace_id_to_rfq_requests.sql
psql -h <host> -U <user> -d <database> -f 003_create_rfq_price_log.sql
psql -h <host> -U <user> -d <database> -f 004_create_shopware_operations.sql
psql -h <host> -U <user> -d <database> -f 004_add_trace_id_to_job_queue.sql
psql -h <host> -U <user> -d <database> -f 005_add_trace_id_to_order_ledger.sql
```

## Migration List

- `001_create_tasks_table.sql` - Creates tasks table for minimal operational spine
- `002_add_trace_id_to_rfq_requests.sql` - Adds `trace_id` to `rfq_requests` and unique partial index for idempotency
- `003_create_rfq_price_log.sql` - Creates append-only `rfq_price_log` table for price audit persistence
- `004_create_shopware_operations.sql` - Creates `shopware_operations` table and indexes
- `004_add_trace_id_to_job_queue.sql` - Adds `trace_id` to `job_queue` and indexes for trace lookup + zombie sweeper
- `005_add_trace_id_to_order_ledger.sql` - Adds `trace_id` to `order_ledger` and trace index

## Naming Convention

Migrations are named: `NNN_description.sql` where NNN is a zero-padded sequence number.

## Important

**MINIMAL OPERATIONAL SPINE — DO NOT EXTEND**

The tasks table is intentionally minimal. Do NOT add:
- Workflow engine features
- Dead letter queue (DLQ)
- Complex orchestration
- Additional state management

Keep it simple: trace_id + status + replay.
