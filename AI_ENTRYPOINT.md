# AI Entrypoint

Read first:

1. `docs/PROJECT_DNA.md`
2. canonical boundary / governance documents referenced by DNA
3. `docs/MASTER_PLAN_v1_9_2.md`
4. `docs/autopilot/STATE.md`
5. GitHub current state
6. `docs/EXECUTION_ROADMAP_v2_3.md`
7. `docs/_governance/AI_EXECUTION_CONTRACT_v1.md`
8. `docs/autopilot/HANDOFF_STATE.json`
9. `docs/handoffs/SWITCH_RUNBOOK_v1.md`

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

Before continuing work, read:
- `docs/_governance/AI_EXECUTION_CONTRACT_v1.md`
- `docs/handoffs/SWITCH_RUNBOOK_v1.md`
