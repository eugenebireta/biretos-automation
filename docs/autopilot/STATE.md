# Autopilot State v2

schema_version: 2
transition_seq: 65
transition_ts: "2026-04-07T16:30:00Z"

## Current
active_task: "R1 Revenue — Price Scout Resolution (suffix-variant lineage + trust expansion)"
task_id: "R1-revenue-price-scout-resolution"
phase: COMPLETED
status: CLOSED
phase_owner: "Owner/Eugene"
risk_level: LOW
pipeline: [BUILDER]
pr_branch: "feat/rev-r1-catalog"
pr_number: 38
now:
  - step: "Price scout resolution — suffix-variant PN matching, trust domain expansion, URL refresh for 6 ambiguous seeds"
    actions:
      - "pn_match.py: strip_known_suffix() + suffix-variant fallback in extract_structured_pn_flags"
      - "trust.py: 7 new industrial domains (sima-land, vseinstrumenti, specregion, pksafety, dmsupply, transcat, instrumart)"
      - "4 seeds updated with accessible URLs (specregion for harnesses, DM Supply for 129464N/U, instrumart for 129625-L3)"
      - "129464N/U: admissible_public_price ($640.44, DM Supply, lineage=True)"
      - "1011893-RU + 1011894-RU: lineage=True via suffix-variant matching (surface_conflict pending stabilization)"
      - "Final: 6 admissible_public_price, 5 ambiguous_offer/review_required"
      - "Evaluation report (honeywell.xlsx) provides reference prices for all 17 SKU"
known_gap: |
  SURFACE_CONFLICT (new sources): 1011893-RU, 1011894-RU — lineage=True but surface_conflict with prior runs
    — will stabilize after 2+ pipeline runs; currently flagged as review_required
  MANUFACTURER_PN_NOT_VISIBLE: 129625-L3 (GA-USB1-IR distributor code), 121679-L3 (no accessible URL)
    — distributor pages don't show manufacturer PN; lineage unconfirmable by automation
    — evaluation report reference prices: 129625-L3=55352₽, 121679-L3=17169₽
  NO_PUBLIC_PRICE: 1015021 (rfq_only on all found pages), 121679-L3 (no page found)
    — evaluation report reference: 1015021=1255₽, 121679-L3=17169₽
  STRUCTURAL_PN_COLLISION: 8 PEHA items (00020211, 101411, 104011, 105411, 106511, 109411, 125711, 127411)
    — mislabeled as industrial sensors/valves but are Peha electrical switch covers
    — prices exist on Conrad but pipeline rejects due to category_mismatch
    — needs catalog reclassification or explicit category_mismatch override
  photo_recovery=14 SKU remaining
awaiting: "Owner decision: (A) reclassify PEHA items in catalog, OR (B) switch track to next R1 phase or Infrastructure."

## Previous (seq 60 — M4 Executor Bridge)
prev_active_task: "Meta Orchestrator — M4 Executor Bridge"
prev_task_id: "meta-orchestrator-m4-executor-bridge"
prev_phase: COMPLETED
prev_status: CLOSED
prev_exit: "executor_bridge.py run()+run_with_collect(), 43 tests, SEMI BATCH_APPROVAL. 308/308 orchestrator tests PASS."

## Previous (seq 59 — M3 synthesizer)
prev_active_task: "Meta Orchestrator — M3 Decision Synthesizer + Gemini Auditor"

prev_task_id: "meta-orchestrator-m3-synthesizer"
prev_phase: COMPLETED
prev_status: CLOSED
prev_exit: "synthesizer.py 7-rule engine + Gemini 3.1 Pro auditor. CORE audit via API: BATCH_APPROVAL. 61/61 M3 tests PASS."

## Previous (seq 50 — BVS deterministic merge tool)
prev_active_task: "BVS deterministic merge tool"
prev_task_id: "bvs-merge-tool"
prev_phase: BUILDER
prev_status: COMPLETED
prev_exit: "PR #28 merged; 41/41 tests PASS; bvs_25sku_seed.jsonl + merged_manifest.jsonl committed."

## Previous (seq 48 — auditor_system Phase 2)
prev_active_task: "auditor_system Phase 2 — Live Auditors + Pilot Gate (SPEC v3.4)"
prev_task_id: "auditor-system-phase2"
prev_phase: BUILDER
prev_status: PR_OPEN
prev_exit: "Phase 2 complete: 38/38 tests, live auditors, pilot gate. OpenAI quota gap remains."

## Previous (seq 44 — Governed AI Execution System Phase 1)
prev_active_task: "Governed AI Execution System — Phase 1 complete, PR #18 auto-merge enabled"
prev_task_id: "auditor-system-phase1"
prev_phase: AUDITOR
prev_status: PR_OPEN
prev_exit: "Phase 1 auditor_system thin vertical slice: 14/14 tests pass, PR #18 auto-merge enabled."

## Previous (seq 42 — Pack A Cleanup Gate)
prev_active_task: "R1 Enrichment - Pack A Cleanup Gate"
prev_task_id: "R1-pack-a-cleanup-gate"
prev_phase: BUILDER
prev_status: COMPLETED
prev_actions:
  - "RECON/HANDOFF audit completed 2026-04-02: three owner decisions recorded (Q1/Q2/Q3)"
  - "6 AUTO_PUBLISH SKU downgraded to REVIEW_REQUIRED (LEGACY_AUTO_PUBLISH_HOLDOUT): evidence_033588.17, evidence_1000106, evidence_1006186, evidence_1006187, evidence_1012539, evidence_1061200000"
  - "Pack A committed (6bbfbb2 + ee8dff3): catalog_seed, local_catalog_refresh, build_catalog_followup_queues, photo_enhance_local, photo_quarantine_stale + all artifacts"
prev_exit: "Pack A cleanly committed. 6 SKU holdout in place. AUTO_PUBLISH=0 in canonical 25-SKU slice."

## Previous (seq 41 — Local Catalog Refresh Overlay)
prev_active_task: "R1 Enrichment - Local Catalog Refresh Overlay"
prev_task_id: "R1-local-catalog-refresh-overlay"
prev_phase: BUILDER
prev_status: ACTIVE
prev_now:
  - step: "1. Local Catalog Refresh Overlay"
    actions:
      - "The stale rejected derivative quarantine pass is complete: downloads/photos_enhanced now holds only 11 active accepted placeholders and 14 stale rejected derivatives were moved into downloads/photos_enhanced_quarantine with a structured move manifest and summary"
      - "A new seed loader in scripts/catalog_seed.py now reads UTF-16 honeywell_insales_import.csv and exposes seeded description, description_source, site placement, product type, brand, and our_price_raw for reuse across local catalog refresh work"
      - "photo_pipeline.py now feeds content_seed into build_evidence_bundle and persists seeded description metadata into product_data.json so future bounded pipeline runs do not throw away the local import description and placement fields"
      - "export_pipeline.py now exports description_source, site placement, product type, and image status, prefers merchandising image_local_path when present, and no longer falls back to raw rejected-photo paths in InSales CSV output"
      - "A bounded overlay runner landed in scripts/local_catalog_refresh.py: instead of rebuilding old evidence from scratch, it starts from a known-good evidence slice, overlays seeded content, attaches accepted enhanced placeholder images, applies current photo_verdict overrides, and refreshes canonical downloads/evidence, downloads/export, and product_data.json without opening a second evidence-truth path"
      - "Canonical refresh was promoted from downloads/audits/phase_a_v2_sanity_20260326T202323Z/evidence onto the current workspace: refreshed_bundle_count=25, content_seeded_count=25, merchandising_attached_count=10, photo_rejected_count=14, exported_rows=15, cards={auto_publish:6, review_required:9, draft_only:10}, and policy_card_status_mismatch_count=11 is now surfaced explicitly in refresh_trace instead of being hidden"
      - "The rejected-photo override for 1050000000 is now reflected in canonical evidence/export: photo verdict is REJECT with user_feedback_2026_04_01_image_not_related_to_sku, card_status is REVIEW_REQUIRED, and the export image field is blank instead of a bad raw photo"
      - "A follow-up queue builder landed in scripts/build_catalog_followup_queues.py and generated refreshed_catalog_photo_recovery_queue_20260331T215334Z.jsonl (14 rows) plus refreshed_catalog_price_followup_queue_20260331T215334Z.jsonl (15 rows) so the next scout batch can start from an operational backlog instead of manual triage"
    exit: "The current 25-SKU local Honeywell slice is now content-seeded, reject-safe, and merchandising-aware: accepted placeholders flow to export, rejected photos are blanked, and the next bounded scout work is explicitly queued."
next:
  - "Run the next bounded scout batch from the generated follow-up queues: recover better photos for the 14 rejected-photo SKU and keep the same placeholder/evidence separation"
  - "Close price follow-up on the 15 queued SKU with manual/Codex scout on admissible sources before any marketplace-specific attribute work"
  - "After the next scout batch, decide whether to do a bounded cleanup pass on the 11 historical policy_card_status mismatches that were preserved from the legacy base evidence for operational continuity"
  - "Keep Ozon category/attribute work downstream from the current photo/price backlog unless the owner explicitly reprioritizes marketplace preparation first"
TODO later: "Hold broader provider expansion, TTL work, generative photo variation, and marketplace-specific category layers until the refreshed local catalog slice proves stable and the queued photo/price follow-up batches materially reduce REVIEW_REQUIRED and DRAFT_ONLY coverage gaps"
todo_later_items:
  - "Price-only scout pilot stays bounded to one brand and 20-30 SKU with explicit success gates"
  - "Provider expansion beyond the current adapters stays parked until the pilot proves the seam is sufficient"
  - "TTL decay and further evidence lifecycle policy remain follow-up work after the pilot"
  - "Local enhancement must remain non-generative and derivative-only; raw product photos remain canonical evidence inputs"
awaiting: "owner prioritization between the generated photo_recovery_queue (14 SKU) and price_followup_queue (15 SKU) for the next manual scout batch"

## Task 7 Closeout
task_7_status: MERGED
task_7_pr: "https://github.com/eugenebireta/biretos-automation/pull/9"
task_7_branch: "feat/task-7"
task_7_commit: "df21f3d"
task_7_merged_ts: "2026-03-22T18:38:49Z"
task_7_ci: "SUCCESS (321 tests)"
task_7_judge_verdict: "MERGE_APPROVED (JUDGE verdict 2026-03-23)"

## Integrity
integrity_hash: "sha256:pending-regeneration"

## Evidence
last_phase_output_hash: null
builder_test_evidence: "39/39 PASS targeted tests across catalog_seed, local_catalog_refresh, export fallback guards, photo_enhance, photo_quarantine, and follow-up queue generation; canonical local refresh promoted 25 bundles with content_seeded_count=25, merchandising_attached_count=10, photo_rejected_count=14, policy_card_status_mismatch_count=11, exported_rows=15, and generated follow-up queues of 14 photo-recovery rows plus 15 price-followup rows"
changed_files:
  - "scripts/catalog_seed.py"
  - "scripts/local_catalog_refresh.py"
  - "scripts/build_catalog_followup_queues.py"
  - "scripts/export_pipeline.py"
  - "scripts/photo_pipeline.py"
  - "scripts/photo_enhance_local.py"
  - "scripts/photo_quarantine_stale.py"
  - "tests/enrichment/test_catalog_seed.py"
  - "tests/enrichment/test_local_catalog_refresh.py"
  - "tests/enrichment/test_build_catalog_followup_queues.py"
  - "tests/enrichment/test_export_phase_a_v2.py"
  - "tests/enrichment/test_photo_enhance_local.py"
  - "tests/enrichment/test_photo_quarantine_stale.py"
  - "downloads/photo_verdict.json"
  - "downloads/scout_cache/photo_enhance_seed_all25_recheck.jsonl"
  - "downloads/scout_cache/photo_enhance_manifest_all25_recheck.jsonl"
  - "downloads/scout_cache/photo_quarantine_manifest_all25.jsonl"
  - "downloads/scout_cache/photo_quarantine_summary_all25.json"
  - "downloads/audits/local_catalog_refresh_20260331T215126Z/"
  - "downloads/scout_cache/refreshed_catalog_photo_recovery_queue_20260331T215334Z.jsonl"
  - "downloads/scout_cache/refreshed_catalog_price_followup_queue_20260331T215334Z.jsonl"
  - "downloads/scout_cache/refreshed_catalog_followup_summary_20260331T215334Z.json"
capsule_ref: "docs/autopilot/CAPSULE.md"

## Multimodel
model_trace: [Opus, Gemini, Codex, Opus, Auto, Gemini, Codex, Gemini, Auto, Gemini, Opus, Gemini, Auto, Codex, Gemini, Auto]
multimodel_check: OK

## Circuit Breaker
fail_count: 0
last_fail_class: null
same_class_streak: 0

## Judge
judge_verdict: null
judge_pack_hash: null

## History Tail (last 5 transitions, FIFO)
history:
  - seq: 21
    phase: SCOUT
    status: PENDING
    ts: "2026-03-03T09:05:36Z"
    actor: "Agent/Codex"
  - seq: 22
    phase: POST_AUDIT_LOGGER
    status: ACTIVE
    ts: "2026-03-03T09:33:22Z"
    actor: "Agent/Codex"
  - seq: 23
    phase: SCOUT
    status: PENDING
    ts: "2026-03-03T09:33:23Z"
    actor: "Agent/Codex"
  - seq: 24
    phase: BUILDER
    status: ACTIVE
    ts: "2026-03-18T00:00:00Z"
    actor: "migration-reset"
    note: "PC migration gap: state reset to BUILDER/ACTIVE; code already committed at ee54864"
  - seq: 25
    phase: SCOUT
    status: PENDING
    ts: "2026-03-20T00:00:00Z"
    actor: "Agent/Sonnet"
    note: "Task 5.1 closeout: AUDITOR PASS + POST_AUDIT_LOGGER complete; CAPSULE.md filled; advancing to Task 5.2"
  - seq: 26
    phase: BUILDER
    status: PR_OPEN
    ts: "2026-03-22T00:00:00Z"
    actor: "Agent/Sonnet"
    note: "Phase 7 Pass 2 complete: 19 files, 321 tests pass. PR #9 open. Awaiting CRITIC/AUDITOR/JUDGE."
  - seq: 27
    phase: POST_AUDIT_LOGGER
    status: PR_OPEN
    ts: "2026-03-22T00:00:00Z"
    actor: "Agent/Sonnet"
    note: "Governance doc closeout: docs/ reorg (DNA merge v2.1, MASTER_PLAN/ROADMAP moved, _archive), MIGRATION_POLICY NLU checks added. 4 commits pushed to feat/task-7. PR #9 still awaiting external review."
  - seq: 28
    phase: MONITOR
    status: ACTIVE
    ts: "2026-03-22T00:00:00Z"
    actor: "Agent/Sonnet"
    note: "Task 7 MERGED (PR #9, CI SUCCESS, judge PASS). Advancing to Этап 8 — Stability Gate."
  - seq: 29
    phase: SCOUT
    status: ACTIVE
    ts: "2026-03-31T00:00:00Z"
    actor: "Owner/Codex"
    note: "R1 Enrichment re-scoped to disposition gap closure: owner re-scope, route hardening, bounded proof batch."
  - seq: 30
    phase: SCOUT
    status: ACTIVE
    ts: "2026-03-31T05:25:35Z"
    actor: "Owner/Codex"
    note: "1006186 proven closed on CAP-09B; live residual narrowed to 1012541 only."
  - seq: 31
    phase: SCOUT
    status: ACTIVE
    ts: "2026-03-31T07:37:32Z"
    actor: "Owner/Codex"
    note: "1012541 proven closed on CAP-09B; remaining_no_price_family_count=0 and remaining_ambiguous_tail_count=0. Awaiting next bounded R1 work item."
  - seq: 32
    phase: SCOUT
    status: ACTIVE
    ts: "2026-03-31T08:30:00Z"
    actor: "Owner/Codex"
    note: "Proof batch closed on 1006186, 1011994, 104011, and 1012541 with 368 tests pass. NEXT queue set to N1 provider adapter seam, N2 evidence schema hardening, and N3 price-only scout pilot."
  - seq: 33
    phase: SCOUT
    status: ACTIVE
    ts: "2026-03-31T10:15:00Z"
    actor: "Owner/Codex"
    note: "N1 provider adapter seam and N2 evidence schema hardening confirmed in code: injectable chat/search adapters, negative_evidence, explicit price_date alias, and split evidence_paths. Advancing to N3 price-only scout pilot."
  - seq: 34
    phase: SCOUT
    status: ACTIVE
    ts: "2026-03-31T19:49:18Z"
    actor: "Owner/Codex"
    note: "N3 bounded price-only scout pilot runner landed together with photo workspace hygiene. Pilot artifact price_only_scout_pilot_20260331T194918Z confirms exact product lineage on 15/15 seeded SKU with zero surface conflicts, but OpenAI quota exhaustion held the slice to 15/20 and collapsed live price extraction to no_price_found."
  - seq: 35
    phase: SCOUT
    status: ACTIVE
    ts: "2026-03-31T20:12:08Z"
    actor: "Owner/Codex"
    note: "N3 manual proof batch landed: price_manual_seed plus price_manual_scout closed a 5-SKU trusted slice with public_price=5/5, exact_product_lineage_confirmed_count=5, surface_conflict_count=0, and no OpenAI quota dependency."
  - seq: 36
    phase: SCOUT
    status: ACTIVE
    ts: "2026-03-31T20:37:43Z"
    actor: "Owner/Codex"
    note: "N3 manual robustness batch landed: 20/20 manual-seeded Honeywell SKU processed with exact_product_lineage_confirmed_count=20, surface_conflict_count=0, transient_failure_row_count=0, price_status_counts={public_price:11, ambiguous_offer:4, no_price_found:5}, and explicit fx_gap_count=1."
  - seq: 41
    phase: BUILDER
    status: ACTIVE
    ts: "2026-03-31T21:53:34Z"
    actor: "Owner/Codex"
    note: "Photo stale-derivative quarantine completed, local catalog refresh overlay promoted onto the 25-SKU canonical Honeywell slice with seeded content plus placeholder merchandising, rejected raw images blanked in export, follow-up queues generated for 14 photo-recovery SKU and 15 price-followup SKU, and 11 inherited policy_card_status mismatches made explicit in refresh_trace for later bounded cleanup."
  - seq: 42
    phase: BUILDER
    status: ACTIVE
    ts: "2026-04-02T00:00:00Z"
    actor: "Agent/ClaudeCode"
    note: "Pack A cleanup gate: RECON/HANDOFF audit completed, 6 AUTO_PUBLISH SKU downgraded to REVIEW_REQUIRED holdout (owner Q1 decision), Pack A new scripts committed (10/10 tests pass), Pack B and Pack D deferred as separate gates."

  - seq: 48
    ts: "2026-04-02T22:12:08Z"
    actor: review_runner
    action: "verdict_approved"
    detail: "Stage 8.1 — approved via auditor_system"
    run_id: "run_9b2fc417617f"

## Task 5.1 Closeout (2026-03-20)
task_5_1_status: CLOSED
task_5_1_commit: "ee54864e2e5eeafe8d502d8e48b64d19676613ae"
task_5_1_branch: "feat/task-5.1"
task_5_1_changed_files:
  - ".cursor/windmill-core-v1/domain/cdm_models.py"
  - ".cursor/windmill-core-v1/tests/test_cdm_models.py"
task_5_1_test_evidence: "6/6 PASS (test_cdm_models.py); 124/124 PASS (full suite)"
task_5_1_auditor_verdict: PASS
task_5_1_capsule: "docs/autopilot/CAPSULE.md"

## R2_PREP_STATUS (2026-03-18)
A_DONE:
  - PROJECT_DNA.md synced to authoritative DNA v2.0
  - R2 docs naming alignment: PROJECT_DNA, MASTER_PLAN_v1_8_0, EXECUTION_ROADMAP_v2_2, docs/howto/R2_EXPORT_PREP — canonical name rev_export_logs
B_MERGED:
  - feat/rev-r2-export merged to master via PR #2 (1605aa1) — CONFIRMED
  - files on master: migrations/027_create_rev_export_logs.sql, tests/test_rev_export_logs_schema.py, ru_worker/telegram_router.py (/export stub)
  - CI green: CONFIRMED (PR #2 @ 1605aa1, PR #3 @ 8bc7eb2 — 2026-03-18)
C_BLOCKED:
  - Revenue gate not open
  - R2 feature activation forbidden until revenue gate opens
D_BLOCKERS:
  - Tier-1 Hash Lock: FIXED (LF normalized, hash lock PASS)
  - governance pytest: approve_case_with_correction RESOLVED (environment-only, 2026-03-17)
  - CI green: CONFIRMED (2026-03-18)

## Override Log (append-only)
overrides:
  - seq: 17
    ts: "2026-03-03T00:01:00Z"
    from_phase: SCOUT
    from_status: WAITING_APPROVAL
    to_phase: POST_AUDIT_LOGGER
    to_status: PENDING
    operator: "Agent/Codex"
    reason: "Resolve OWNER_MISMATCH after deferred gap sync"
  - seq: 19
    ts: "2026-03-03T09:02:38Z"
    from: "SCOUT/PENDING"
    to: "POST_AUDIT_LOGGER/PENDING"
    actor: "Agent/Codex"
    reason: "Sync deferred gap after consecutive Ask-phase deadlock: Task 4.4 no-code closeout confirmed by ARCHITECT; route to POST_AUDIT_LOGGER."
  - seq: 22
    ts: "2026-03-03T09:33:22Z"
    from: "SCOUT/PENDING"
    to: "POST_AUDIT_LOGGER/ACTIVE"
    actor: "Agent/Codex"
    reason: "Apply deferred AUDITOR PASS for Task 5.1 and execute mandatory POST_AUDIT_LOGGER transition."
  - seq: 24
    ts: "2026-03-18T00:00:00Z"
    from: "POST_AUDIT_LOGGER/ACTIVE"
    to: "BUILDER/ACTIVE"
    actor: "migration-reset"
    reason: "PC migration gap: state reset to reflect resume point; CAPSULE.md was empty, evidence fields null. Closed out properly at seq 25 (2026-03-20)."

## Task 8.1 Closeout (via auditor_system)
task_8_1_status: CLOSED
task_8_1_closed_at: "2026-04-02T22:12:08Z"
task_8_1_run_id: "run_9b2fc417617f"
