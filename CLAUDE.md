# CLAUDE.md — Biretos Automation

## CHAT LIVENESS OVERRIDE (highest priority)

If the user message is a short liveness check or tiny conversational prompt
(examples: "ты тут?", "ok", "ping", "проверь связь"), Claude MUST:

1. Reply in one short sentence immediately.
2. Not start any workflow/pipeline/phase protocol.
3. Not run tools, not scan files, not propose plan, not require approvals.
4. Ignore task-completion automation rules for that turn.

This override applies only to that single liveness/conversational turn.

## ENRICHMENT DATA RULES (mandatory, never forget)

### Rule 1 — Read from normalized{}, not raw fields
Evidence data is in `normalized{}` block. NEVER check raw `dr_price`/`dr_image_url` to assess coverage.
- Price → `normalized.best_price`
- Photo → `normalized.best_photo_url`
- Description → `normalized.best_description`
- To assess gaps: run `python scripts/evidence_coverage_report.py` FIRST.

### Rule 2 — Phased pipeline, NEVER one mega-prompt
DR enrichment uses a phased architecture (see `scripts/MANIFEST.json` → `full_enrichment_pipeline`):
1. Phase 1: Identity Recon (Haiku) — product_type, series, designation only
2. Phase 2: Market Recon (Haiku) — unit vs pack, dangerous distributors
3. Gate A: identity must be resolved before proceeding
4. Phase 3A: Price (GPT Think) + Phase 3B: Content (Opus ext) — parallel
5. NEVER combine all into one "find everything" prompt

### Rule 3 — Filename ≠ brand
Source Excel "honeywell new.xlsx" contains mixed brands: Dell, NVIDIA, Phoenix Contact, SAIA, Weidmüller, Moxa, Xerox, Sony, etc. NEVER assume brand from filename. Brand comes from `structured_identity.confirmed_manufacturer` (set by Phase 1 recon), not from the Excel filename.

### Rule 4 — Model assignments
- Haiku: cheap recon (phases 1-2)
- GPT Think: price scouting (phase 3A)
- Opus ext: content/specs/photos (phase 3B)
- Gemini: NEVER (fabricates prices and product identities)

## SCRIPT AWARENESS (mandatory pre-flight)

Before doing ANY of these tasks manually, FIRST check `scripts/MANIFEST.json`
and run the existing script:

- Generating DR prompts → `scripts/dr_prompt_generator.py`
- Importing DR results → `scripts/dr_results_import.py`
- Merging to evidence → `scripts/merge_research_to_evidence.py`
- Downloading documents → `scripts/download_documents.py`
- Exporting to CSV/Excel → `scripts/export_pipeline.py`
- Any enrichment/catalog task → `ls scripts/` and grep for keywords FIRST

**NEVER write ad-hoc Python for tasks that existing scripts already handle.**
**NEVER invent product data — always pull from evidence files.**
All scripts support `--dry-run` — use it first.

See `memory/reference_operations_map.md` for the full task→script mapping.

## Управление неявными знаниями (KNOW_HOW.md)

Код документирует себя сам через `git log`. Файл `KNOW_HOW.md` предназначен СТРОГО
для фиксации внешних и неявных знаний, которые невозможно вывести из исходного кода.

ТВОЯ ОБЯЗАННОСТЬ:
Если в процессе диалога, анализа данных или дебага ты обнаруживаешь новую критическую
информацию, ты должен САМОСТОЯТЕЛЬНО предложить записать её в `KNOW_HOW.md`.

ЧТО ПИШЕМ:
- `#platform` — неочевидное поведение внешних платформ (API, лимиты, переключения режимов LLM)
- `#rule` — доменные правила и специфика данных (форматы PN, суффиксы, мусор в лотах)
- `#bug` — плавающие ошибки, связанные с окружением или грязными данными
- `#data_quirk` — аномалии в данных, coverage gaps, quality patterns. Примеры:
  "evidence: expected_category wrong in 92% (344/374)",
  "evidence: weak identity 30% SKUs — worse DR results",
  "brand X: N SKUs, coverage Y%, description gap Z%"

ПРАВИЛО МАСШТАБА: числовые факты в KNOW_HOW требуют команду-источник.
Не "33+ PEHA", а `grep -c` / `wc -l` / скрипт подсчёта → точное число и процент.
Никогда не экстраполировать масштаб из одного примера.

ПОСЛЕ BATCH PROCESSING: обязательно записать хотя бы один `#data_quirk` —
coverage, quality, аномалии. Даже если "всё нормально" — зафиксировать метрики.

СТРОГО ЗАПРЕЩЕНО писать:
- Изменения в коде (добавление функций, рефакторинг, фиксы)
- Изменение конфигураций (включение флагов, настройки)
- Структуру директорий и архитектуру (это README или архитектурные доки)
- Инструкции по установке инструментов (это README)

Формат: `YYYY-MM-DD | #тег | scope: Суть и почему это важно`

KNOW_HOW ownership:
- SCOUT и BUILDER могут записать открытие с тегом `#draft`
- AUDITOR — финальный валидатор: подтверждает, дополняет или удаляет `#draft` записи
- Финальная запись (без `#draft`) появляется до закрытия задачи

## VERIFICATION REMINDER

Before changing code, define the verification path first.
Prefer baseline -> change -> re-check.
If no automated checks exist, state the validation gap explicitly.

## IDENTITY

Post-Core Freeze. Corrective execution track active:
Phase 0 loss prevention -> Phase 1 governance codification.

Read these files before ANY code change:
1. `docs/PROJECT_DNA.md`
2. `docs/MASTER_PLAN_v1_9_2.md`
3. `docs/EXECUTION_ROADMAP_v2_3.md`
4. `docs/claude/MIGRATION_POLICY_v1_0.md`
5. `docs/autopilot/STATE.md`

Source of truth priority:
`docs/PROJECT_DNA.md` → `docs/MASTER_PLAN_v1_9_2.md` → `docs/EXECUTION_ROADMAP_v2_3.md` → `docs/claude/MIGRATION_POLICY_v1_0.md` → `docs/autopilot/STATE.md`

## CURRENT TRACK

Default execution order until the owner explicitly reopens a later track:
1. `Phase 0` — loss prevention / safety / repo integrity
2. `Phase 1` — governance codification in authoritative files
3. Only after that may `Stage 8.1` / local review fabric / runtime shadow gate continue

Presence of Stage 8.1 code in the repo does NOT authorize expanding that track.

Do not modify these files as part of corrective governance batches unless the owner
explicitly opens a separate Stage 8.1 batch:
- `auditor_system/review_runner.py`
- `auditor_system/hard_shell/approval_router.py`
- `auditor_system/hard_shell/contracts.py`

## PROTECTED GOVERNANCE SURFACE

These modules enforce execution constraints. They CANNOT be modified by
LOW or SEMI executor paths. Changes require explicit owner approval as
a separate governance batch:

- `orchestrator/acceptance_checker.py` — acceptance gates (A1-A5+)
- `orchestrator/synthesizer.py` — risk floor, gate semantics
- `orchestrator/guardian.py` — task intent / action validation
- `auditor_system/hard_shell/` — post-audit bridge, approval routing
- `orchestrator/collect_packet.py` — pytest parser, evidence collection

Reason: executor must never modify its own constraints. If executor needs
a gate change to pass — that is an escalation to owner, not a fix.

## FROZEN FILES (19) — NEVER TOUCH

See `docs/PROJECT_DNA.md` §3 for full list.
Any change = architectural violation.
If you are unsure whether a file is frozen — check §3 first.

## PINNED API — NEVER CHANGE SIGNATURES

See `docs/PROJECT_DNA.md` §4. These function signatures are immutable:

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

See `docs/PROJECT_DNA.md` §5 + §5b. Summary:

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

## NLU TABLES (Phase 7)

`nlu_pending_confirmations` and `nlu_sla_log` do NOT use `rev_*` prefix.
These are Core Backoffice infrastructure tables (AI Assistant layer),
not Revenue Tier-3 tables. They are owned by the Governance/Backoffice
domain, not by Revenue workers.

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
- Workflow compression is allowed only as defined in `docs/PROJECT_DNA.md` §12 and `MIGRATION_POLICY_v1_0.md`
- `CRITIC`, `AUDITOR`, `JUDGE` remain external and separate

## R1 / PHASE A BATCH EXECUTION

For `R1` / `Phase A` / Revenue Tier-3 / `SEMI` work, default execution mode is
bounded batch execution under
`docs/policies/R1_PHASE_A_BATCH_EXECUTION_STANDARD_v1_0.md`.

- One logical change-set per batch
- One risk class per batch
- One narrow outcome per batch
- One policy surface maximum per batch
- No out-of-scope files
- No multi-agent runtime
- No substantial return without evidence pack
- If scope breaks or evidence pack is incomplete, self-reject and reopen the batch

## AUTOPILOT PROTOCOL

After completing any task:

1. Update `docs/autopilot/STATE.md` with new phase/status
2. Write `CAPSULE.md` summary
3. Append to `docs/_governance/COMPLETED_LOG.md`
4. Classify next task risk: `LOW` / `SEMI` / `CORE`
5. Do NOT merge to `master`
6. Wait for external review
7. Show final diff summary and risk classification

## OPERATIONAL PARAMETERS

### Global task timeout
Formula: `executor_timeout × (max_retries + 1) × 2`.
Default: 600 × 4 × 2 = 4800s (~80 min) for all risk levels.
After timeout → forced STOP + park in `STATE.md` with `#TIMEOUT`. Not crash, not retry.

### Budget limits
- Per-run: $0.50 soft warning (log, don't block)
- Daily: $5.00 hard stop — all tasks parked until next day
- Owner override: explicit only

### Orphan cleanup
At start of each new trace:
- Check for uncommitted files from prior cycles
- If found → log in experience, clean working directory
- If orphan doesn't belong to current trace → log + escalate, don't delete silently

### API fallback
If external API returns error or timeout:
1. One retry after 60s
2. If still failing → park task in `STATE.md` with `parked_api_outage`
3. Owner notification
4. No model substitution (Gemini CRITIC ≠ Claude CRITIC — changes governance)

### Acceptance gate A6 (test modification warning)
If executor modified test files that existed before task started → WARNING flag.
Not a block — a flag for AUDITOR to verify "test was fixed, not weakened".

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

Workflow differs by risk level:

### 🟢 LOW
1. Commit → push → PR → auto-merge (`gh pr merge --auto --merge`)
2. Show PR number, diff --stat, pytest result
3. STOP. PR merges when CI passes.

### 🟡 SEMI
1. Commit → push → PR
2. Show PR number, diff --stat, pytest result
3. **WAIT for owner ACCEPT** — no auto-merge
4. After owner says "ACCEPT" → run `gh pr merge --auto --merge`

### 🔴 CORE
1. Commit → push → PR
2. Show owner the PR number: "Send this PR number to JUDGE chat for review"
3. After owner pastes "OK" → run `gh pr merge --auto --merge`
4. Owner's "OK" means external reviewers approved. Owner does not review code.

Do all steps automatically without asking (except waiting for approval on SEMI/CORE).

## MANDATORY PIPELINE FOR EVERY TASK

Every task goes through roles according to risk level.
Role templates: `docs/prompt_library/roles/`

### Pipeline by risk level

**🟢 LOW:**
`SCOUT/ARCHITECT/PLANNER/BUILDER (compressed) → AUDITOR → auto ship`
Compression allowed, but: deterministic gates mandatory, AUDITOR must be
a separate pass (not same breath as BUILDER). `can_ship` only after acceptance.

**🟡 SEMI:**
`SCOUT → ARCHITECT → external CRITIC → PLANNER → BUILDER → external AUDITOR → OWNER ACCEPT`
CRITIC and AUDITOR must be external (separate context, not self-review).
JUDGE is not required for SEMI but may be invoked by owner.

**🔴 CORE:**
`Pass 1: SCOUT + ARCHITECT → WAITING_FOR_OK → Pass 2: PLANNER + BUILDER → external CRITIC → external AUDITOR → external JUDGE → owner decision`

### Relay rule

Every role produces an artifact (Report/Verdict).
Without artifact the role is NOT considered complete.
Next role starts only after receiving the previous role's artifact.

### Task completion rule

- **LOW**: closed when AUDITOR wrote `can_ship: YES`.
- **SEMI**: closed when AUDITOR `can_ship: YES` AND owner `ACCEPT`.
- **CORE**: closed when AUDITOR `can_ship: YES` AND JUDGE `APPROVE` AND owner `ACCEPT`.

"I did everything" without AUDITOR REPORT = task is NOT closed.
Agent CANNOT report "done" before receiving `can_ship: YES`.

### Defect discovery rule

If agent finds a defect AFTER saying "done" —
that is an AUDITOR failure, not a coincidence.
Agent MUST fix the defect and re-run AUDITOR.

### Self-check before reporting

Agent CANNOT write "done" or "completed" until:
1. Tests ran (if any exist)
2. Result checked against task requirements
3. Explicitly answered: "can this be used right now — yes/no"

If there are defects — fix first, report second.

## NEVER

- Merge to `master` directly
- Modify Tier-1 files (see `docs/PROJECT_DNA.md` §3)
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
- Revert format or rules of `KNOW_HOW.md` — current format is architectural decision (PROJECT_DNA.md §9)
- Add code changes, config changes, or install instructions to `KNOW_HOW.md` — only external know-how (#platform, #rule, #bug, #data_quirk)
- Restore deleted `KNOW_HOW.md` entries or `scripts/hooks/pre-commit` — removals were deliberate
