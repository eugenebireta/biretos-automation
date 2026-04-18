# AI Entrypoint

## Layer 0 — Always read (every cycle):

0. `SESSION_PRIMER.md` — quick context: project status, pipelines, key KNOW_HOW
1. `docs/PROJECT_DNA.md` — invariants, frozen files, absolute rules
2. `docs/autopilot/STATE.md` — current execution state
3. Task Brief текущей задачи — сейчас: `config/TASK_BRIEF_R1_ENRICHMENT.md`
4. `docs/_governance/AI_EXECUTION_CONTRACT_v1.md` — execution role boundaries

## Read if relevant to current task:

5. `docs/policies/R1_PHASE_A_BATCH_EXECUTION_STANDARD_v1_0.md` — при R1 / Phase A работе
6. `CLAUDE.md` — при первом запуске в новом repo checkout

## Read when planning (not every cycle):

7. `docs/MASTER_PLAN_v1_9_2.md` — стратегия, принципы
8. `docs/EXECUTION_ROADMAP_v2_3.md` — порядок этапов, текущая позиция

## Read only at tool switch:

9. `docs/autopilot/HANDOFF_STATE.json`
10. `docs/handoffs/SWITCH_RUNBOOK_v1.md`

## Layer 2 — Experience Memory (read when task requires deep domain knowledge)

- `docs/memory/EXPERIENCE_BOOTSTRAP_v1.jsonl` — 24 operating principles (PEHA naming, source trust, family rules)
- `docs/memory/engineering/ENGINEERING_EXPERIENCE_v1.jsonl` — 17 engineering lessons
- `docs/memory/enrichment/ENRICHMENT_EXPERIENCE_v1.jsonl` — 41 enrichment rules
- `docs/memory/PHASE_A_DEVELOPMENT_MEMORY_v1.json` — Phase A proof artifacts

Execution-state rules:

- This file does not change the project's canonical document hierarchy.
- Canonical rules remain in the project's canonical governance documents.
- Use `git` for local workspace state resolution.
- Use `STATE.md` and GitHub for operational execution-state resolution.
- Use the roadmap as the target map unless fresher execution state contradicts it.
- `git`, `STATE.md`, and GitHub do not override DNA, canonical boundaries, or Master Plan rules.

Execution role rules:

- AI tools act only as governed execution assistants.
- Dual-tool mode is an owner-approved provisional extension, not historical repo canon.
- Claude Code and Codex may swap only the BUILDER role.
- Tool swap never downgrades governance.
- For CORE work, Codex is read-only / proposal-only until the full external pipeline is complete.
- Switch only at a valid clean stop-point.
- If `git` and `HANDOFF_STATE.json` disagree, trust `git`, discard the handoff summary as authority, and reconstruct it.
- For `R1` / `Phase A` / Revenue Tier-3 / `SEMI` work, execute in batch-only mode.
- Do not widen scope between gates without reopening the batch.
- `R1` batch execution does not authorize multi-agent runtime.

Verification reminder:

- Before changing code, define how correctness will be verified.
- Prefer baseline -> change -> re-check.
- Do not return from a substantial `R1` batch without an evidence pack.
- If scope boundary breaks or evidence is incomplete, self-reject and reopen as a new batch.

Before continuing work, read:
- `docs/_governance/AI_EXECUTION_CONTRACT_v1.md`
- `docs/handoffs/SWITCH_RUNBOOK_v1.md`
