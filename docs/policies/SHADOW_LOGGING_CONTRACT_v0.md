# Shadow Logging Contract v0

Status: DRAFT-MVP  
Date: 2026-03-27

## 1. Executive verdict

This should start now because high-value cloud trajectories are already being
produced in the repo, but they are fragmented across raw shadow logs, evidence
packs, verdict artifacts, and continuity outputs.

If linkage starts only at Local AI runtime time, the future corpus will be:

- noisy
- weakly labeled
- hard to deduplicate
- detached from final outcomes

This does not launch Local AI runtime.

v0 is only a redacted linkage contract for future training and evaluation
corpus assembly. It does not introduce:

- local model execution
- orchestration
- fine-tuning pipeline
- vector DB / retrieval engine
- governance authority transfer

## 2. What already exists

Useful raw artifacts already exist:

- `shadow_log/*.jsonl` in the photo/catalog path
- `artifacts/judge/<timestamp>_<sha>/evidence_pack.md`
- `artifacts/judge/<timestamp>_<sha>/judge_verdict.json`
- `artifacts/judge/<timestamp>_<sha>/human_verdict.md`
- `docs/autopilot/CONTINUITY_INDEX.md`
- verifier shadow records in evidence bundles
- `shadow_adjudication_queue.json`
- reviewer packets and development memory snapshots

These artifacts are useful, but they are not yet one corpus.

## 3. What is missing

The current repo still lacks:

- one stable `trajectory_id` across task -> execution -> evidence -> judge -> outcome
- one normalized record format for cross-role trajectories
- one authoritative final outcome label rule
- one quality label rule separated from runtime noise
- one redaction contract for future corpus extraction
- one explicit rule that training corpus is not Memory Vault and not source of truth

## 4. Hard separation

Three layers must stay separate.

### 4.1 Continuity / memory

Purpose:

- fast re-entry
- durable operator context
- structured recall of proven and not-proven conclusions

Examples:

- `docs/autopilot/CONTINUITY_INDEX.md`
- `docs/memory/PHASE_A_DEVELOPMENT_MEMORY_v1.json`

Rules:

- not training corpus
- not source of truth
- not allowed to set final outcome labels by itself

### 4.2 Evidence / judge flow

Purpose:

- govern one concrete execution batch
- support review, merge gates, and owner decisions

Examples:

- evidence packs
- judge verdicts
- human verdicts
- bounded execution status artifacts

Rules:

- review artifacts can recommend
- they do not automatically become training labels
- they remain tied to one explicit run or batch

### 4.3 Future training / eval corpus

Purpose:

- accumulate redacted teacher-student trajectories
- compare cloud vs local quality later
- support future distillation and regression evaluation

Rules:

- not Memory Vault
- not governance authority
- not source of truth
- labels must come from explicit authoritative outcome rules

## 5. Shadow Logging Contract v0

### 5.1 Scope

v0 covers linkage for these roles:

- `executor`
- `judge`
- `reviewer`
- `auditor`
- `recon`

v0 covers these entities:

- task / request
- executor run
- evidence pack
- continuity artifact
- judge verdict
- human verdict
- final accepted or rejected outcome
- timeout / retry / stall / failure status
- corrections / overrides / rework

### 5.2 Storage

Raw source artifacts stay where they already live.

The normalized corpus layer lives separately:

- `shadow_log/corpus_v0/trajectory_records_YYYY-MM.jsonl`

v0 stores normalized, redacted linkage records only.

Large or sensitive payloads must remain by reference to an existing artifact.

No new daemon, queue, or background worker is required.

### 5.3 Format

Format: JSONL, one normalized record per line.

Each record is one event or artifact snapshot in one trajectory.

Allowed `record_kind` values:

- `task`
- `executor_run`
- `evidence_pack`
- `continuity_artifact`
- `judge_verdict`
- `human_verdict`
- `final_outcome`
- `status_event`
- `correction`

### 5.4 Linkage model

Each trajectory must have one stable `trajectory_id`.

Minimum linkage rule:

- one task/request starts one `trajectory_id`
- retries and rework stay inside the same `trajectory_id`
- each new artifact gets its own `record_id`
- `parent_id` points to the immediate causal parent

Each normalized record also carries `linkage_ids`:

- `task_id`
- `request_id`
- `run_id`
- `attempt_id`
- `evidence_pack_id`
- `continuity_id`
- `judge_verdict_id`
- `human_verdict_id`
- `outcome_id`
- `correction_id`

If an id does not exist yet, it stays `null`.

### 5.5 Reference format

The contract should prefer references over inline payloads.

Allowed reference forms:

- repo-relative path with optional line anchor  
  Example: `shadow_log/price_extraction_2026-03.jsonl#L245`
- repo-relative path to artifact file  
  Example: `artifacts/judge/20260327T101500_df21f3d/judge_verdict.json`
- future blob reference  
  Example: `sha256:<digest>`

Inline excerpts are allowed only when they are already redacted and short.

### 5.6 Required fields

Every normalized record must contain at least:

- `schema_version`
- `record_kind`
- `record_id`
- `trajectory_id`
- `parent_id`
- `timestamp`
- `role`
- `task_type`
- `risk`
- `provider`
- `model`
- `input_ref`
- `output_ref`
- `evidence_ref`
- `verdict_ref`
- `final_outcome_label`
- `trajectory_quality_label`
- `redaction_status`
- `linkage_ids`

### 5.7 Optional fields

Optional but recommended:

- `run_status`
- `attempt_index`
- `retry_count`
- `correction_type`
- `authoritative_label_source`
- `auxiliary_trace`
- `notes`

### 5.8 Mandatory labels

Trajectory quality labels:

- `good_trajectory`
- `bad_trajectory`
- `blocked_trajectory`
- `inconclusive_trajectory`

Outcome labels:

- `accepted_outcome`
- `rejected_outcome`
- `superseded_outcome`
- `needs_human_review`

### 5.9 Authoritative label rule

`final_outcome_label` is authoritative only when both are true:

- `record_kind` is `final_outcome`
- `authoritative_label_source` is `human_owner` or `authoritative_system_record`

All other labels are auxiliary or provisional.

Default safety rule:

- unresolved cases stay `needs_human_review`
- unlabeled quality defaults to `inconclusive_trajectory`

### 5.10 Example normalized record

```json
{
  "schema_version": "shadow_logging_record_schema_v0",
  "record_kind": "judge_verdict",
  "record_id": "judge_verdict:task7:attempt1",
  "trajectory_id": "trajectory:task7",
  "parent_id": "evidence_pack:task7:attempt1",
  "timestamp": "2026-03-27T10:15:00Z",
  "role": "judge",
  "task_type": "coding_review",
  "risk": "SEMI",
  "provider": "openai",
  "model": "gpt-5.4",
  "input_ref": "artifacts/judge/20260327T101500_df21f3d/evidence_pack.md",
  "output_ref": "artifacts/judge/20260327T101500_df21f3d/judge_raw_response.json",
  "evidence_ref": "artifacts/judge/20260327T101500_df21f3d/evidence_pack.md",
  "verdict_ref": "artifacts/judge/20260327T101500_df21f3d/judge_verdict.json",
  "final_outcome_label": "needs_human_review",
  "trajectory_quality_label": "inconclusive_trajectory",
  "redaction_status": "ref_only",
  "linkage_ids": {
    "task_id": "7",
    "request_id": "task7.review",
    "run_id": "judge_runner:20260327T101500Z",
    "attempt_id": "attempt1",
    "evidence_pack_id": "evidence_pack:task7:attempt1",
    "continuity_id": "continuity:20260327",
    "judge_verdict_id": "judge_verdict:task7:attempt1",
    "human_verdict_id": null,
    "outcome_id": null,
    "correction_id": null
  },
  "run_status": "COMPLETED",
  "attempt_index": 1,
  "retry_count": 0,
  "correction_type": null,
  "authoritative_label_source": "none",
  "auxiliary_trace": false,
  "notes": "Judge verdict exists, but final owner decision is still pending."
}
```

## 6. Ownership and labels

### 6.1 Who writes raw records

Raw source artifacts are written by the producing component:

- `photo_pipeline.py` writes raw shadow task logs
- `judge_runner.py` writes evidence and verdict artifacts
- bounded execution wrapper writes status artifact
- continuity generator writes continuity artifact
- shadow adjudication scripts write reviewer and blocker artifacts

The normalized corpus record should be written by a thin adapter located next to
the producing component, not by a new central orchestrator.

### 6.2 Who can set final outcome

Only these may set authoritative final outcome:

- human owner
- explicit authoritative system-of-record artifact for that domain

Not allowed to set authoritative final outcome:

- executor model
- judge model
- reviewer model
- continuity artifact
- development memory snapshot

### 6.3 Who can set quality label

`trajectory_quality_label` may be set by:

- human owner
- designated reviewer or auditor acting after final outcome is known
- deterministic labeling rule explicitly approved in policy

It must not be set by the executor itself.

### 6.4 What is authoritative

Authoritative:

- the latest non-superseded `final_outcome` record
- signed by `human_owner` or backed by one explicit authoritative system record

Noisy auxiliary trace:

- raw LLM responses
- reviewer packets
- disagreement logs
- continuity artifacts
- development memory
- completed log and decisions log entries
- intermediate retries, timeouts, and stall traces without final resolution

## 7. Redaction rules

### 7.1 Never store

Do not store at all:

- API keys
- access tokens
- cookies
- passwords
- authorization headers
- `.env` values
- private credentials from logs
- raw personal chats unrelated to the task
- Memory Vault records copied into corpus payload

### 7.2 Must redact

Redact before storing or store by reference only:

- customer names
- phone numbers
- email addresses
- delivery addresses
- payment details
- internal account identifiers not needed for evaluation
- raw prompts or logs that include secrets or personal data

### 7.3 Reference-only payloads

Store by reference, not inline:

- full evidence packs
- raw test logs
- long scraped page bodies
- uploaded documents
- large diffs
- large raw model responses

### 7.4 Redaction status values

Use:

- `not_required`
- `redacted_inline`
- `ref_only`
- `contains_secret_blocked`
- `contains_sensitive_blocked`

If a payload cannot be made safe, the normalized record may still exist, but the
payload must stay blocked and referenced only by a blocked status.

## 8. Integration points

### 8.1 `photo_pipeline.py` and existing `shadow_log`

Keep existing raw task logging as the source layer.

v0 integration:

- do not replace current files
- append normalized corpus records separately
- treat existing task JSONL lines as source artifacts referenced by `input_ref`
  and `output_ref`

### 8.2 `judge_runner.py`

First-class v0 integration point.

Reason:

- it already links task scope, evidence pack, continuity preview, judge verdict,
  human verdict, and raw judge response
- it already sits on the governed execution path

v0 addition should be tiny:

- append one normalized `judge_verdict` record
- append one normalized `human_verdict` record
- append one provisional `final_outcome` record with `needs_human_review`
  unless the owner already finalized the outcome
- always write `shadow_corpus_status.json` next to judge artifacts with
  `written | failed` so corpus holes are visible and machine-readable

### 8.3 `generate_continuity_index.py`

Continuity should be referenced only as:

- `record_kind = continuity_artifact`
- `auxiliary_trace = true`
- `authoritative_label_source = none`

Continuity must never become a final label source.

### 8.4 Bounded execution artifacts

Bounded execution status should be linked into the same trajectory through:

- `record_kind = status_event`
- `run_status`
- stdout and stderr refs
- retry and timeout classification

### 8.5 `COMPLETED_LOG.md` and `DECISIONS_LOG.md`

These are context references only.

They may support auditability, but they must not auto-label trajectories.

### 8.6 Verifier and reviewer packets

Treat these as auxiliary reviewer traces:

- useful for future evaluation
- not authoritative for final outcomes
- quality labels only after outcome linkage exists

## 9. Scope now vs later

### 9.1 Do now

- approve one storage path for normalized corpus records
- approve one normalized schema
- start with docs-first policy and schema
- add tiny write integration to `judge_runner.py` first
- keep unresolved cases at `needs_human_review` and
  `inconclusive_trajectory`

### 9.2 Defer to 8.1

- local vs cloud quality comparison at scale
- disagreement dashboards
- shadow gate based on local reviewer
- dedupe and backfill tooling across old trajectories
- retention policy automation for the corpus layer

### 9.3 Not allowed now

- local AI runtime for coding or governance
- autonomous routing based on local model verdicts
- fine-tuning pipeline
- vector DB or retrieval engine
- Memory Vault coupling
- source-of-truth replacement by corpus labels

## 10. Minimal output artifacts

Minimal v0 launch set:

- `docs/policies/SHADOW_LOGGING_CONTRACT_v0.md`
- `config/shadow_logging_record_schema_v0.json`
- corpus write target: `shadow_log/corpus_v0/trajectory_records_YYYY-MM.jsonl`
- per-run visibility artifact: `artifacts/judge/<timestamp>_<sha>/shadow_corpus_status.json`

No framework, daemon, or orchestrator is required for v0.

## 11. Risks

Main risks:

- noisy labels from non-final artifacts
- duplicated trajectories across retries and rework
- drift between outcome and trajectory label
- overcollection of logs that are not useful for evaluation
- privacy or secret leakage through raw prompts and logs
- confusion between corpus data and authoritative truth

The main defense is strict separation:

- truth stays in authoritative artifacts
- governance stays with owner and system-of-record rules
- corpus records stay redacted, linked, and explicitly labeled

## 12. Single recommended next step

Add one tiny post-write adapter to `judge_runner.py` first.

This is the smallest high-value starting point because `judge_runner.py`
already produces the cleanest linkage chain in the repo:

- task scope
- evidence pack
- continuity artifact
- judge verdict
- human verdict
- governed closeout path

That yields the first low-noise corpus slice without premature Local AI runtime.
