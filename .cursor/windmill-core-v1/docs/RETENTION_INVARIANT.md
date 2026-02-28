# INV-RET: Retention Policy Invariant (Core Freeze)

This document defines the retention policy invariant for reconciliation v2.
Retention applies ONLY to reconciliation infrastructure tables and MUST NOT
change business state or replay/verify behavior.

## Scope (tables)

- `reconciliation_audit_log`
- `reconciliation_alerts`
- `reconciliation_suppressions`

## Property 1: Replay Independence

Verify-only replay functions MUST NOT read from the retention-targeted tables.
Deletion of retention-eligible rows MUST NOT alter the output of any verify-only
replay function.

## Property 2: Suppression Safety

Runtime suppression checks MUST filter exclusively on active suppressions.
Expired suppressions are operationally invisible and MAY be deleted after a
post-expiration grace period.

Retention eligibility:

- If `expires_at IS NOT NULL`:
  - `suppression_state = 'expired'` AND `expires_at < NOW() - INTERVAL '30 days'`
- If `expires_at IS NULL`:
  - `suppression_state = 'expired'` AND `created_at < NOW() - INTERVAL '30 days'`

## Property 3: Alert Idempotency Preservation

Pending alerts MUST NOT be deleted. Only delivered or acknowledged alerts may
be deleted after the TTL window.

Retention eligibility:

- `notification_state IN ('sent', 'acked')`
  AND `created_at < NOW() - INTERVAL '90 days'`

Deleting sent/acked alerts removes their UNIQUE `notification_key` rows and
intentionally allows re-alerting after the TTL window if the problem persists
or recurs.

## Property 4: Audit Trail Sufficiency

Audit log rows may be deleted after the TTL window.

Retention eligibility:

- `created_at < NOW() - INTERVAL '30 days'`

Orphan INTENT recovery operates on a 5-minute window; retention TTL MUST be far
larger than that window.

## TTL Schedule

| Table | TTL | Predicate |
|---|---:|---|
| `reconciliation_audit_log` | 30 days | `created_at < NOW() - 30 days` |
| `reconciliation_alerts` | 90 days | `notification_state IN ('sent','acked') AND created_at < NOW() - 90 days` |
| `reconciliation_suppressions` | 30 days after formal expiration | `suppression_state='expired' AND expires_at < NOW() - 30 days` |
| `reconciliation_suppressions` (NULL expires_at) | 30 days after formal expiration | `suppression_state='expired' AND expires_at IS NULL AND created_at < NOW() - 30 days` |

## Execution Constraints

- No partitioning.
- Batched deletes MUST use a CTE subquery pattern (PostgreSQL has no `DELETE ... LIMIT`).
- SQL MUST use hardcoded literals for partial index planner stability.
- Retention MUST run on `audit_conn` only (`autocommit=True`).
- Retention MUST be guarded by `RETENTION_EVERY_NTH_CYCLE` (default: 50).
- Batch size MUST be guarded by `RETENTION_BATCH_SIZE` (default: 1000).
- Per-cycle work MUST be capped by `RETENTION_MAX_BATCHES` (default: 10).

