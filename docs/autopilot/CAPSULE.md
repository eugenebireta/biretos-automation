# Task Capsule

Task_ID: bvs-second-pass-scout
Risk: SEMI
Date: 2026-04-02
Branch: feat/rev-r1-catalog
Status: LIVE_VALIDATION_PENDING — NOT COMPLETED
Governance note: PR #22 merged prematurely (auto-merge without owner approval).
Owner decision 2026-04-02: no revert. Task not closed until live evidence produced.

## What was built

browser_vision_scout.py — second-pass price scout for bot-blocked (403/401/498) and
JS-rendered (200/no-lineage) product URLs.

NOT Anthropic Computer Use tool. Uses Playwright (real Chromium/Edge) + Claude
Messages API image input (Vision) for price extraction and PN lineage confirmation.

Components:
- BrowserFetcher: Playwright context manager, auto browser channel (msedge→chrome→bundled),
  headless default, cookie banner helper (benign only), no CAPTCHA bypass
- VisionExtractor: Claude Vision API, auto-escalation Sonnet→Opus on low confidence,
  structured JSON extraction (price, currency, pn_confirmed, stock_status, page_class)
- materialize_bvs_record(): same manifest schema as price_manual_scout.py + additive fields
- load_first_pass_candidates(): filter by http_status {401,403,498} OR 200/no-lineage
- Full CLI: --seed, --manifest, --first-pass-manifest, --headed, --browser-channel,
  --vision-model, --no-escalation, --save-all-screenshots

Tests: 23/23 PASS (deterministic, mock Playwright + mock Anthropic)

## Dependencies
- playwright 1.57.0 — already installed
- anthropic — requires: pip install anthropic

## Files changed
- scripts/browser_vision_scout.py (NEW, 490 lines)
- tests/enrichment/test_browser_vision_scout.py (NEW, 280 lines)
- docs/autopilot/STATE.md (updated)
- docs/autopilot/CAPSULE.md (this file)
- docs/_governance/COMPLETED_LOG.md (appended)

## Governance
- Tier-1 frozen files: CLEAN
- Pinned API signatures: CLEAN
- price_manual_scout.py: NOT MODIFIED

---

# Previous Capsule

Task_ID: auditor-system-phase1
Risk: SEMI
Date: 2026-04-02
PR: https://github.com/eugenebireta/biretos-automation/pull/18 (auto-merge enabled)
Commit: 3bfe336

## What was built

Governed AI Execution System — Phase 1 thin vertical slice (SPEC v3.4).

21 files in `auditor_system/`:
- `hard_shell/contracts.py` — Pydantic models: TaskPack, AuditVerdict, SurfaceClassification, ProtocolRun
- `hard_shell/context_assembler.py` — rule-based surface classifier (19 TIER1_FILES, 9 OPUS_SURFACES, keyword→surface map)
- `hard_shell/model_selector.py` — Trigger A/B/C model selection (Sonnet default, Opus for OPUS_SURFACES, escalation on gate failure)
- `hard_shell/quality_gate.py` — deterministic pass/fail (reject+critical → fail; both 3+ warnings → fail; conflict → fail)
- `hard_shell/approval_router.py` — AUTO_PASS / BATCH_APPROVAL / INDIVIDUAL_REVIEW / BLOCKED routing + owner_summary.md
- `hard_shell/experience_sink.py` — DPO-ready JSONL (approved→experience_log/, rejected→anti_patterns/, guard on missing verdict)
- `hard_shell/run_store.py` — artifact persistence in runs/<run_id>/ (12 artifact files per run)
- `providers/mock_builder.py` + `providers/mock_auditor.py` — deterministic mocks, no external calls
- `providers/openai_auditor.py` + `providers/anthropic_auditor.py` — Phase 2 stubs (NotImplementedError)
- `review_runner.py` — bounded 2-round protocol orchestrator
- `cli.py` — dry-run and single-task entry points
- `tests/test_dry_run.py` — 14 tests

## Test evidence

14/14 PASS — all Phase 1 readiness criteria:
- Full cycle artifacts in runs/<run_id>/ (12 files)
- ModelSelector: LOW→Sonnet, fsm/guardian keywords→Opus
- Escalation: Sonnet gate fail → Opus retry
- QualityGate: critical reject → INDIVIDUAL_REVIEW
- ApprovalRouter: LOW+approve→AUTO_PASS, SEMI+approve→BATCH_APPROVAL, CORE→INDIVIDUAL_REVIEW
- owner_summary.md readable with task title + route
- ExperienceSink: JSONL written after owner verdict; RuntimeError if called before verdict
- Surface mismatch: ContextAssembler∪Builder declared → effective_surface union, Opus selected
- Tier-1 file → tier1_files surface → Opus

## Dependency note

Requires `pyyaml` (not yet in requirements.txt). Install: `pip install pyyaml`.

## Next (Phase 2)

- Wire live OpenAI auditor (Responses API + json_schema, NOT Chat Completions + JSON mode)
- Wire live Anthropic auditor (run in separate process without ANTHROPIC_API_KEY in env)
- Add `pyyaml` to requirements.txt
- OwnerQueue, BatchPackBuilder, FallbackHandler (scope-excluded from Phase 1)
