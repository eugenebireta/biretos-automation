---
DATE: 2026-04-07
TITLE: R1 Revenue — Price Integration Wave2 + Canonical Refresh Promote
RISK_LEVEL: LOW
STATUS: COMPLETED (committed 70beec3 to feat/rev-r1-catalog, PR #38)
SCOPE:
  - Wave2 price scout: 6 SKUs from seed_target20 → 1 admissible (1011994 USD 9.95)
  - Merged manifest: downloads/scout_cache/price_manual_manifest_merged.jsonl (11 rows)
  - Canonical evidence refresh promoted: 25 bundles updated
  - InSales export: 13/15 REVIEW_REQUIRED rows have prices
REAL_RUN:
  - price_followup=13 (down from 14), photo_recovery=14
  - review_required=15, draft_only=10, auto_publish=0
KNOWN_GAPS:
  - 8 price-followup SKUs have no product page seed
  - 5 price-followup SKUs blocked by CAPTCHA (Conrad SK/NL, etm.ru, tameson)
  - 14 photo-recovery SKUs need SerpAPI (not configured)
TIER1_CLEAN: true
PINNED_API_CLEAN: true

---
DATE: 2026-04-07
TITLE: R1 Revenue — Price Evidence Integrator
RISK_LEVEL: SEMI
STATUS: COMPLETED (committed to feat/rev-r1-catalog, PR #38)
SCOPE:
  - scripts/price_evidence_integrator.py (NEW — integrate_manifest + build_price_section)
  - tests/enrichment/test_price_evidence_integrator.py (NEW — 32 deterministic tests)
  - downloads/evidence/ — 5 evidence bundles updated (price_status=ACCEPTED)
  - downloads/audits/price_integration_<ts>/ — integration audit trace
TEST_EVIDENCE: 32/32 integrator tests PASS; 798/798 total PASS (zero regression)
GOVERNANCE:
  - SEMI risk. Two-round live API audit (Gemini 3.1 Pro CRITIC + Opus 4.6 JUDGE)
  - Round 1: Gemini CONCERNS (sys.path.insert in proposal, trace_id timestamp)
  - Revision: sys.path at module level, trace_id uses now_fn() timestamp
  - Round 2: Gemini APPROVE + Opus CONCERNS → BATCH_APPROVAL (quality gate passed)
KEY_DECISIONS:
  - Does NOT touch card_status — left to local_catalog_refresh.py
  - field_statuses_v2.price_status + policy_decision_v2.price_status set to ACCEPTED
  - Explicit _PRICE_FIELD_MAP allowlist prevents schema drift
  - Idempotent: overwriting price section with same trace_id is safe
REAL_RUN:
  - 5/5 admissible rows integrated from price_manual_manifest.jsonl (20 rows total)
  - local_catalog_refresh result: review_required=15 (up from 9), draft_only=10, auto_publish=0
  - build_catalog_followup_queues: price_followup=14, photo_recovery=14
TIER1_CLEAN: true
PINNED_API_CLEAN: true

---
DATE: 2026-04-07
TITLE: Meta Orchestrator — M4 Executor Bridge
RISK_LEVEL: SEMI
STATUS: COMPLETED (committed e3c5b77 to feat/rev-r1-catalog, PR #38)
SCOPE:
  - orchestrator/executor_bridge.py (NEW — run()+run_with_collect(), structured error taxonomy)
  - orchestrator/main.py (UPDATED — _run_executor_bridge, auto_execute wiring)
  - orchestrator/config.yaml (UPDATED — auto_execute/auto_pytest/executor_timeout_seconds)
  - tests/orchestrator/test_executor_bridge.py (NEW — 43 deterministic tests)
TEST_EVIDENCE: 43/43 executor_bridge tests PASS; 308/308 orchestrator tests PASS
GOVERNANCE:
  - SEMI risk. Two-round live API audit (Gemini 3.1 Pro + Opus 4.6)
  - Round 1: Gemini REJECT (sys.path.insert, no structured logging, generic Exception)
  - Revision: removed sys.path.insert, added logging, split PERMANENT/TRANSIENT error classes
  - Round 2: Gemini APPROVE + Opus CONCERNS → BATCH_APPROVAL (quality gate passed)
KEY_DECISIONS:
  - auto_execute defaults to false — opt-in; manual fallback always printed on failure
  - PERMANENT errors: FileNotFoundError, PermissionError, UnicodeDecodeError (not retriable)
  - collect_packet failure is non-fatal: result.status stays "completed", packet=None
TIER1_CLEAN: true
PINNED_API_CLEAN: true

---
DATE: 2026-04-07
TITLE: Meta Orchestrator — M3 Decision Synthesizer + Gemini Auditor
RISK_LEVEL: CORE
STATUS: COMPLETED (committed to feat/rev-r1-catalog)
SCOPE:
  - orchestrator/synthesizer.py (NEW — 7-rule engine R1-R7, pure function)
  - orchestrator/main.py (UPDATED — M3 wired; CORE_GATE routes to auditor_system)
  - auditor_system/providers/gemini_auditor.py (NEW — Gemini 3.1 Pro, replaces OpenAI)
  - auditor_system/cli.py (UPDATED — GeminiAuditor replaces OpenAIAuditor)
  - auditor_system/config/models.yaml (UPDATED — gemini+claude-opus-4-6)
  - tests/orchestrator/test_synthesizer.py (NEW — 61 tests)
TEST_EVIDENCE: 61/61 synthesizer tests PASS; 723/723 total PASS (zero regression)
GOVERNANCE:
  - M3 architecture reviewed via live API before implementation (CORE protocol)
  - CRITIC: Gemini 3.1 Pro — CONCERNS (R3 silent strip → BLOCKED, R6 SEMI→ESCALATE)
  - JUDGE: Claude Opus 4.6 — CONCERNS (same + R5 structured field)
  - Manual: Opus chat APPROVED with 2 mandatory fixes; GPT rejected (5 action names)
  - All critical issues resolved in implementation
KEY_DECISIONS:
  - R3: stripped_files non-empty → BLOCKED (not silent strip+proceed)
  - R6: empty scope + SEMI risk → ESCALATE (not NO_OP); LOW → NO_OP
  - R5: addresses_blocker structured field takes priority over "unblock" keyword
  - Gemini replaces OpenAI as CRITIC auditor (quota issue resolved)
TIER1_CLEAN: true
PINNED_API_CLEAN: true

---
DATE: 2026-04-07
TITLE: Meta Orchestrator — M2 Claude Advisor API Integration
RISK_LEVEL: SEMI
STATUS: COMPLETED (committed to feat/rev-r1-catalog)
SCOPE:
  - orchestrator/advisor.py (NEW — Anthropic SDK, JSON parse+extract, retry, escalation write)
  - orchestrator/main.py (UPDATED — _run_advisor(), _build_directive(), advisor escalation gate)
  - tests/orchestrator/test_advisor.py (NEW — 42 tests: success/retry/escalation/missing-key)
TEST_EVIDENCE: 42/42 M2 tests PASS; 662/662 total PASS (zero regression)
KEY_DECISIONS:
  - Error chain: attempt 1 (full context) → attempt 2 (simplified prompt) → ESCALATE
  - ESCALATE writes last_escalation.json, sets fsm_state=awaiting_owner_reply, returns
  - _build_directive() replaces _build_stub_directive() — real next_step+scope from verdict
  - Missing ANTHROPIC_API_KEY → immediate escalation (not exception)
  - issued_at auto-patched if absent in response
TIER1_CLEAN: true
PINNED_API_CLEAN: true

---
DATE: 2026-04-07
TITLE: Meta Orchestrator — M1 Task Intake + Classifier + Context Pruner
RISK_LEVEL: LOW
STATUS: COMPLETED (committed to feat/rev-r1-catalog)
SCOPE:
  - orchestrator/classifier.py (NEW — deterministic risk engine, rules C1-C4 CORE + S1-S3 SEMI)
  - orchestrator/intake.py (NEW — ContextBundle, soft file reads, diff pruning, staleness warn)
  - orchestrator/main.py (UPDATED — _run_intake(), _run_classify(), CORE gate, classify subcommand)
  - tests/orchestrator/test_classifier.py (NEW — 52 tests, all 7 rules covered)
  - tests/orchestrator/test_intake.py (NEW — 27 tests: soft failures, truncation, rendering)
TEST_EVIDENCE: 79/79 M1 tests PASS; 620/620 total PASS (zero regression)
KEY_DECISIONS:
  - CORE gate in cmd_cycle: if risk_class==CORE → fsm_state=awaiting_owner_reply, no directive written
  - classify subcommand added for standalone diagnostic use
  - _build_stub_directive now accepts bundle+classification → embeds risk_line + context section
  - _run_intake/_run_classify are thin wrappers — importable, mockable, testable
TIER1_CLEAN: true
PINNED_API_CLEAN: true

---
DATE: 2026-04-07
TITLE: Meta Orchestrator — M0.5 Artifact Schemas
RISK_LEVEL: LOW
STATUS: COMPLETED (committed to feat/rev-r1-catalog)
SCOPE:
  - orchestrator/schemas/advisor_verdict_v1.json (NEW)
  - orchestrator/schemas/manifest_v1.json (NEW)
  - orchestrator/schemas/escalation_v1.json (NEW)
  - orchestrator/schemas.py (NEW — validate/validate_soft/is_valid, jsonschema draft-07)
  - tests/orchestrator/test_schemas.py (NEW — 53 tests)
TEST_EVIDENCE: 53/53 schema tests PASS; 541/541 total PASS (zero regression)
KEY_DECISIONS:
  - confidence_score rejected from advisor_verdict (AI-driven, violates deterministic rule engine)
  - cost_estimate + affected_sku_count removed from escalation base schema (use affected_entity_count)
  - validate_soft() returns error list, never raises — safe for rule engine use in M3
TIER1_CLEAN: true
PINNED_API_CLEAN: true

---
DATE: 2026-04-06
TITLE: Meta Orchestrator — M0 Execution Interface Spike
RISK_LEVEL: LOW
STATUS: COMPLETED (committed to feat/rev-r1-catalog)
SCOPE:
  - orchestrator/__init__.py (NEW)
  - orchestrator/main.py (NEW — FSM skeleton, one-cycle runner)
  - orchestrator/collect_packet.py (NEW — deterministic git+pytest post-processor)
  - orchestrator/config.yaml (NEW — thresholds)
  - orchestrator/schemas/directive_v1.json (NEW — JSON Schema draft-07)
  - orchestrator/schemas/execution_packet_v1.json (NEW — JSON Schema draft-07)
  - orchestrator/spike_findings.md (NEW — physical interface findings)
  - tests/orchestrator/__init__.py (NEW)
  - tests/orchestrator/conftest.py (NEW)
  - tests/orchestrator/test_collect_packet.py (NEW — 30 mocked tests)
TEST_EVIDENCE: 30/30 orchestrator tests PASS; 509/509 enrichment tests PASS (zero regression)
KEY_FINDINGS:
  - Physical interface: cat directive.md | claude -p (stdin piped to --print mode)
  - FSM: 5 states, 12 transitions defined
  - base_commit auto-resolution: merge-base origin/master → HEAD~1 fallback
  - collect_packet.py: deterministic, mocked, no live API dependencies
TIER1_CLEAN: true
PINNED_API_CLEAN: true

---
DATE: 2026-04-03
TITLE: BVS deterministic merge tool
RISK_LEVEL: SEMI
STATUS: COMPLETED (PR #28 merged to master)
SCOPE:
  - scripts/merge_manifests.py (NEW — deterministic first+second pass merge)
  - tests/enrichment/test_merge_manifests.py (NEW — 18 tests)
  - downloads/scout_cache/bvs_25sku_seed.jsonl (NEW — reproducible seed)
  - downloads/scout_cache/merged_manifest.jsonl (NEW — sanitized deterministic merge output)
TEST_EVIDENCE: 41/41 PASS (18 merge + 23 BVS regression)
EXCLUDED_FROM_PR: captcha_solver fix (separate PR), bvs_25sku_manifest.jsonl (runtime BVS/CDP provenance), evidence_*.json (point demo)
PR: https://github.com/eugenebireta/biretos-automation/pull/28 (MERGED 2026-04-03; merge commit f6c9954)
TIER1_CLEAN: true
PINNED_API_CLEAN: true

---
DATE: 2026-04-03
TITLE: auditor_system Phase 2 — Live Auditors + Pilot Gate (SPEC v3.4)
RISK_LEVEL: SEMI
STATUS: COMPLETED
SCOPE:
  - auditor_system/hard_shell/schema_validator.py (NEW)
  - auditor_system/hard_shell/fallback_handler.py (NEW)
  - auditor_system/hard_shell/run_store.py (MODIFIED — load_run_for_verdict)
  - auditor_system/providers/openai_auditor.py (REPLACED — live Responses API)
  - auditor_system/providers/anthropic_auditor.py (REPLACED — live Messages API)
  - auditor_system/review_runner.py (MODIFIED — FallbackHandler + _gather_safe)
  - auditor_system/cli.py (REPLACED — verdict + pilot + live runner commands)
  - auditor_system/config/models.yaml (MODIFIED — anthropic: claude-sonnet-4-6)
  - auditor_system/config/.env.auditors (NEW — isolated secrets, gitignored)
  - auditor_system/requirements.txt (NEW)
  - auditor_system/tests/test_phase2.py (NEW — 24 deterministic tests)
  - .gitignore (MODIFIED — add .env.auditors)
  - .env root (CLEARED — ANTHROPIC_API_KEY removed)
TEST_EVIDENCE: 38/38 PASS (14 Phase1 + 24 Phase2)
PILOT_GATE:
  LOW  | run_3adda4a0816c | auto_pass        | Anthropic: approve   | owner: approved
  SEMI | run_42cce6d15df3 | batch_approval   | Anthropic: concerns  | owner: approved
  CORE | run_8175dc532f3d | BLOCKED          | OpenAI quota → STOP_OWNER_ALERT (correct)
KNOWN_GAP: OpenAI key has insufficient_quota → Responses API unavailable. FallbackHandler correct.
DPO_RECORDS: 2 written to experience_log/2026-04.jsonl
NEXT_RISK: SEMI

---
DATE: 2026-04-02
TITLE: browser_vision_scout — second-pass price scout (Playwright + Claude Vision)
RISK_LEVEL: SEMI
STATUS: LIVE_VALIDATION_PENDING — NOT COMPLETED
SCOPE:
  - scripts/browser_vision_scout.py (NEW — BrowserFetcher, VisionExtractor, auto-escalation, CLI)
  - tests/enrichment/test_browser_vision_scout.py (NEW — 23 deterministic tests)
TEST_EVIDENCE: 23/23 PASS (unit tests only — no live evidence yet)
NEXT_RISK: SEMI
GOVERNANCE_INCIDENT: |
  PR #22 merged prematurely via auto-merge without owner approval (SEMI violation).
  Owner decision 2026-04-02: no revert, leave as is.
  Task is NOT closed. Must not be treated as completed in any downstream audit.
AWAITING: live dry-run on vseinstrumenti.ru / lemanapro.ru → evidence bundle → owner sign-off
---
DATE: 2026-04-02
TITLE: Governed AI Execution System — Phase 1 hard_shell thin vertical slice
RISK_LEVEL: SEMI
SCOPE:
  - auditor_system/ (21 files: hard_shell, providers, tests, cli)
TEST_EVIDENCE: 14/14 PASS (all Phase 1 readiness criteria)
PR: https://github.com/eugenebireta/biretos-automation/pull/18
COMMIT: 3bfe336
CAPSULE: docs/autopilot/CAPSULE.md
---
DATE: 2026-03-22
TITLE: Governance Doc Closeout — DNA v2.1 + docs/ reorg + MIGRATION_POLICY NLU checks
RISK_LEVEL: LOW
SCOPE:
  - docs/PROJECT_DNA.md (MERGED from PROJECT_DNA_v2_0.md + PROJECT_DNA.md — v2.1, §1b, §6 R4, §7 items 6-9, §10 4 new checklist items)
  - docs/MASTER_PLAN_v1_9_1.md (MOVED from root, TD header fix v1.9.0→v1.9.1)
  - docs/EXECUTION_ROADMAP_v2_3.md (MOVED from root)
  - _archive/ (6 old docs from "old md/": ROADMAP v1.0/v2.0/v2.3-old, MASTER_PLAN v1.4.3/v1.7.2/v1_9_0)
  - CLAUDE.md (all doc path references updated)
  - docs/claude/MIGRATION_POLICY_v1_0.md (CRITIC items 6-9, AUDITOR items 8-10 added)
  - PROJECT_DNA.md, PROJECT_DNA_v2_0.md (DELETED from root)
BRANCH: feat/task-7
COMMITS: 52372fc, a5a9767, 20bbbab, ba15982
SUMMARY: >
  Documentation governance session: merged two DNA files into docs/PROJECT_DNA.md v2.1
  (added §1b hierarchy, R4 Anchor Buyer Liquidation scope, §7 patterns 6-9, §10 4 new
  checklist items). Moved MASTER_PLAN and ROADMAP to docs/. Archived 6 old versions.
  Updated CLAUDE.md paths. Added NLU-specific CRITIC/AUDITOR review checks to
  MIGRATION_POLICY (INV-MBC, shadow isolation, no nested FSM, NLU wrapper check,
  degradation safety). PR #9 still open, awaiting external CRITIC/AUDITOR/JUDGE.
STATUS: CLOSED (doc tasks complete; PR #9 remains open for code review)
---
DATE: 2026-03-22
TITLE: Phase 7 — AI Executive Assistant NLU (Pass 2 complete, PR open)
RISK_LEVEL: CORE
SCOPE:
  - migrations/029_assistant_nlu.sql (NEW)
  - domain/nlu_models.py (NEW)
  - domain/assistant_models.py (NEW)
  - domain/intent_parser.py (NEW)
  - domain/prompt_injection_guard.py (NEW)
  - domain/guardian.py (MODIFIED — guard_nlu_confirmation + whitelist)
  - config/schema.py (MODIFIED — 7 NLU env vars)
  - config/validator.py (MODIFIED — NLU parsing)
  - ru_worker/nlu_confirmation_store.py (NEW)
  - ru_worker/nlu_shadow_log.py (NEW)
  - ru_worker/nlu_sla_tracker.py (NEW)
  - ru_worker/assistant_router.py (NEW)
  - ru_worker/telegram_router.py (MODIFIED — free-text + nlu callbacks)
  - ru_worker/dispatch_action.py (MODIFIED — nlu_parse/nlu_confirm routing)
  - tests/test_intent_parser.py (NEW, 21 tests)
  - tests/test_prompt_injection_guard.py (NEW, 15 tests)
  - tests/test_nlu_confirmation_store.py (NEW, 9 tests)
  - tests/test_nlu_sla_tracker.py (NEW, 7 tests)
  - tests/test_assistant_router.py (NEW, 8 tests)
BRANCH: feat/task-7
COMMIT: df21f3d
PR: https://github.com/eugenebireta/biretos-automation/pull/9
TESTS: 321 passed, 0 failed
SUMMARY: >
  Full Phase 7 implementation: regex-only NLU for 4 intents with
  INV-MBC mandatory button confirmation, graceful degradation L0/L1/L2,
  shadow mode (manual exit), prompt injection guard, SLA tracking,
  5-minute confirmation TTL with atomic consume.
  Awaiting CRITIC/AUDITOR/JUDGE. NO auto-merge.
STATUS: PR_OPEN — awaiting external review
---
DATE: 2026-03-20
TITLE: Task 5.1 — TaskIntent + ActionSnapshot Pydantic v2 Models (CLOSEOUT)
RISK_LEVEL: CORE
SCOPE:
  - .cursor/windmill-core-v1/domain/cdm_models.py (NEW, Tier-2)
  - .cursor/windmill-core-v1/tests/test_cdm_models.py (NEW, 6 tests)
BRANCH: feat/task-5.1
COMMIT: ee54864e2e5eeafe8d502d8e48b64d19676613ae
SUMMARY:
  Added Pydantic v2 BaseModel definitions for TaskIntent and ActionSnapshot
  (domain/cdm_models.py). TaskIntent enforces trace_id min_length=1 (Fail Loud).
  ActionSnapshot enforces Literal[1] schema_version and Literal["cdek_shipment"]
  leaf_worker_type (Fail Loud). 6 deterministic unit tests, no DB, no live API.
  No Tier-1 frozen files touched. No pinned API signatures changed.
  Full suite: 124/124 PASS. Prerequisite for Task 5.2 (Validation на 3 границах).
AUDITOR_VERDICT: PASS
TEST_EVIDENCE: 6/6 PASS (test_cdm_models.py); 124/124 PASS (full suite)
NOTES:
  Bookkeeping recovered after PC migration gap (STATE.md was BUILDER/ACTIVE with
  null evidence; CAPSULE.md was empty). Closed out at seq 25. Task 5.2 SCOUT open.
---
DATE: 2026-03-13
TITLE: R2 Naming Alignment + Write-Prep (NOT MERGED)
RISK_LEVEL: LOW
SCOPE:
  - PROJECT_DNA.md
  - MASTER_PLAN_v1_8_0.md
  - EXECUTION_ROADMAP_v2_2.md
  - docs/howto/R2_EXPORT_PREP.md
  - feat/rev-r2-export branch (migrations/027, test_rev_export_logs_schema, telegram_router /export stub)
SUMMARY:
  A) DONE: DNA sync to v2.0; docs naming alignment to rev_export_logs in all 4 files.
  B) WRITE-PREP DONE, NOT MERGED: feat/rev-r2-export has migration 027, schema test, /export stub.
  C) BLOCKED: Revenue gate not open, merge R2 batch forbidden until Track A blockers closed.
  D) BLOCKERS: Tier-1 Hash (CRLF-only, infra follow-up pending); governance pytest (approve_case_with_correction); CI green not confirmed.
NOTES:
  R2 is NOT fully complete. Merge prohibited. Track A must close first.
---
DATE: 2026-03-02
TITLE: Image Tool Ban — Permanent Enforcement
RISK_LEVEL: LOW
SCOPE:
  - .cursorrules
  - .cursor/rules/risk_router.mdc
  - ai_engineering/agent_behavior_rules.txt
  - .cursor/rules/autopilot_ux.mdc
SUMMARY:
  Implemented 4-layer tool governance to permanently disable image/diagram generation tools in Cursor.
  Tools are framed as DISABLED/mocked. Self-abort logic added. Mermaid fallback enforced.
ARCH_VERDICT: APPROVE
SMOKE_TEST: PASS (Mermaid, no image tool call)
NOTES:
  MULTIMODEL_TRACE explicitly disambiguated from multimodal capabilities.
---
