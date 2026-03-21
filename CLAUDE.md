# CLAUDE.md — Biretos Automation

## IDENTITY

Post-Core Freeze. Tier-3 Revenue development active.

Read these files before ANY code change:
1. `PROJECT_DNA_v2_0.md`
2. `MASTER_PLAN_v1_9_0.md`
3. `EXECUTION_ROADMAP_v2_3.md`
4. `docs/claude/MIGRATION_POLICY_v1_0.md`
5. `docs/autopilot/STATE.md`

Source of truth priority:
`PROJECT_DNA_v2_0.md` → `MASTER_PLAN_v1_9_0.md` → `EXECUTION_ROADMAP_v2_3.md` → `docs/claude/MIGRATION_POLICY_v1_0.md` → `docs/autopilot/STATE.md`

## FROZEN FILES (19) — NEVER TOUCH

See `PROJECT_DNA_v2_0.md` §3 for full list.
Any change = architectural violation.
If you are unsure whether a file is frozen — check §3 first.

## PINNED API — NEVER CHANGE SIGNATURES

See `PROJECT_DNA_v2_0.md` §4. These function signatures are immutable:

- `_derive_payment_status()`
- `_extract_order_total_minor()`
- `recompute_order_cdek_cache_atomic()`
- `update_shipment_status_atomic()`
- `_ensure_snapshot_row()`
- `InvoiceStatusRequest`
- `ShipmentTrackingStatusRequest`

You may change function bodies.
You may NOT change names, arguments, or return types.

## ABSOLUTE PROHIBITIONS

See `PROJECT_DNA_v2_0.md` §5 + §5b. Summary:

Tier-3 code CANNOT:
- `INSERT/UPDATE/DELETE` on `reconciliation_audit_log`, `reconciliation_alerts`, `reconciliation_suppressions`
- Raw DML on `order_ledger`, `shipments`, `payment_transactions`, `reservations`, `stock_ledger_entries`, `availability_snapshot`, `documents`
- Import from `domain.reconciliation_service`, `domain.reconciliation_alerts`, `domain.reconciliation_verify`, `domain.structural_checks`, `domain.observability_service`
- `ALTER/DROP` `reconciliation_*` tables in `migrations/020+`

## REVENUE TABLES (§5b)

- Always prefix: `rev_*` / `stg_*` / `lot_*`
- No direct `JOIN` with Core tables
- Read Core only through read-only views
- Linear FSM only, max 5 states
- No nested FSM, no branching states, no custom retry orchestrators

## EVERY NEW TIER-3 MODULE MUST HAVE

1. `trace_id` from payload
2. `idempotency_key` for side-effects
3. No commit inside domain operations — commit only at worker boundary
4. No logging of secrets or raw payload
5. Structured error logging: `error_class` (`TRANSIENT` / `PERMANENT` / `POLICY_VIOLATION`), `severity` (`WARNING` / `ERROR`), `retriable` (`true/false`)
6. No silent exception swallowing
7. Runnable in isolation (entry point or test with stub dependencies)
8. At least one deterministic test (no live API, no unmocked time/randomness)
9. Structured log at decision boundary: `trace_id`, key inputs, outcome
10. Webhook workers must validate signature (HMAC) BEFORE processing
11. Inbound event dedup: external `event_id` as `idempotency_key` via `INSERT ON CONFLICT DO NOTHING`

## RISK CLASSIFICATION

Before any commit, classify the change:

- 🟢 **LOW**: Tier-3 only, no Core touch → commit to feature branch
- 🟡 **SEMI**: Tier-2 body changes, new Tier-3 with financial side-effects → flag for review
- 🔴 **CORE**: Tier-1 adjacent, schema, FSM, Guardian, invariants → STOP and use Strict Mode

Do NOT change risk classification without owner approval.

## CORE STRICT MODE

For 🔴 CORE tasks, you MUST follow this exact sequence:

### Pass 1 — SCOUT + ARCHITECT only
- Analyze code
- Design architecture
- Produce plan
- Do NOT write implementation code
- End with `WAITING_FOR_OK`

### Pass 2 — PLANNER + BUILDER
- Start only after owner approves Pass 1 result
- Implement the approved plan
- Run tests
- Commit to feature branch

### After Pass 2
- Show `git diff --stat`
- Do NOT merge
- Wait for external `CRITIC`, `AUDITOR`, `JUDGE`

## MIGRATION POLICY

See `docs/claude/MIGRATION_POLICY_v1_0.md`.

Key rule:
- `LOW/SEMI` may use relaxed execution
- `CORE` must always use Strict Mode
- Workflow compression is allowed only as defined in `PROJECT_DNA_v2_0.md` §12 and `MIGRATION_POLICY_v1_0.md`
- `CRITIC`, `AUDITOR`, `JUDGE` remain external and separate

## AUTOPILOT PROTOCOL

After completing any task:

1. Update `docs/autopilot/STATE.md` with new phase/status
2. Write `CAPSULE.md` summary
3. Append to `docs/_governance/COMPLETED_LOG.md`
4. Classify next task risk: `LOW` / `SEMI` / `CORE`
5. Do NOT merge to `master`
6. Wait for external review
7. Show final diff summary and risk classification

## PARALLELIZATION

- Only ONE major branch active at a time
- Safety (`infra/*`) and Revenue (`feat/rev-*`) alternate in 3–5 day sprints
- `feat/rev-*` branches must NOT touch `core/`, `domain/reconciliation/`, `infra/`

## Claude Code Operational Guardrails

1. **Executor, not judge.** Claude Code may act as combined SCOUT / ARCHITECT / PLANNER / BUILDER when workflow compression is allowed. It must never act as final CRITIC, AUDITOR, or JUDGE for its own work.

2. **Owner of truth stays outside.** Core / repo governance remain source of truth. Claude Code must not present itself as owner of truth.

3. **No irreversible repo authority without explicit owner approval.** No push, no merge, no branch protection changes, no deleting branches, no rewriting history, no edits to source-of-truth governance docs unless explicitly requested.

4. **CORE work requires external review.** Strict Mode for CORE. External CRITIC / AUDITOR / JUDGE required before final approval.

5. **Evidence-first approval.** No "safe / done / approved" claim without: git diff / touched files, test evidence, CI status if applicable, relevant DNA checklist facts.

6. **One major branch at a time.** Do not open or advance parallel major tracks unless explicitly requested.

7. **Max autonomy cap for CORE.** At most 2 autonomous passes on one CORE package before stopping for external review or owner decision.

8. **Cursor role.** Cursor is treated as read-only dashboard / diff review surface during CORE sessions, not as a parallel writer.

9. **Guardrail conflicts.** If any guardrail conflicts with a direct owner instruction — stop and ask for explicit confirmation instead of assuming.

## WORKFLOW RULE

After completing any task:
1. Commit changes with descriptive message
2. Push to current branch
3. Create PR via "gh pr create"
4. Enable auto-merge via "gh pr merge --auto --merge"
5. Show PR number, diff --stat, and pytest result
6. STOP. PR will merge automatically when CI passes.

For 🔴 CORE tasks: do steps 1-3 only. Do NOT enable auto-merge until owner confirms that external CRITIC/AUDITOR/JUDGE review is complete. When owner says "review passed" — enable auto-merge via "gh pr merge --auto --merge".

This is the full cycle. Do all steps automatically without asking.

## NEVER

- Merge to `master` directly
- Modify Tier-1 files (see `PROJECT_DNA_v2_0.md` §3)
- `ALTER/DROP` `reconciliation_*` tables
- Import from `domain.reconciliation_*`
- DML on Core business tables from Tier-3
- Bypass Guardian for Core mutations
- Create plans, audits, or meta-documents instead of code when implementation is requested
- Skip `WAITING_FOR_OK` between Pass 1 and Pass 2 for CORE tasks
- Change risk classification of a task without owner approval
- Ignore `docs/claude/MIGRATION_POLICY_v1_0.md`
- Ignore `docs/autopilot/STATE.md`
- Give owner manual git commands (`git add`, `git commit`, `git push`) — Claude Code does this autonomously
- Use `git add -A` — only add specific files that were changed by the task