# CONTINUITY_INDEX

Purpose: short continuity summary for fast re-entry and handoff.
Non-authoritative. Mirrors canonical and operational sources. If conflict exists, owner source wins.

## Usage Rules

- Read after `STATE.md`, not instead of it.
- Preview with `python scripts/generate_continuity_index.py`.
- Write with `python scripts/generate_continuity_index.py --write`.
- Update only after milestone-like events or substantial handoff.
- Every entry must have `source_ref`.
- Do not duplicate decision ledger, audit dumps, or long closeout summaries.
- `Current thread` and `Next approved item` are mirror-from-STATE only.
- Prefer exact `STATE` section or line references, not free retelling.
- Keep this file under 200 lines.
- If this file does not improve re-entry after 2-3 cycles, creates bureaucracy, or becomes a drift source, freeze or remove it.

## Conflict Rules

- For live execution conflicts: `STATE` wins over `ROADMAP`.
- For plan and scope conflicts: `PROJECT_DNA`, policy docs, and `MASTER_PLAN` win; `ROADMAP` is only a planning snapshot.
- `CONTINUITY_INDEX` never resolves conflicts by itself; it only mirrors or flags them.

## Current Thread

Status: `open`
Claim: `8 — Stability Gate (эксплуатация)` is the active execution thread in `MONITOR` / `ACTIVE`.
Source_ref: `docs/autopilot/STATE.md#L8-L18`
Last_validated: `2026-03-27`

## Verified Findings

- ID: `VF-001`
  Status: `verified`
  Claim: `Task 7` merged, and execution advanced to `8 — Stability Gate (эксплуатация)`.
  Source_ref: `docs/autopilot/STATE.md#L21-L27; docs/autopilot/STATE.md#L97`
  Last_validated: `2026-03-27`
- ID: `VF-002`
  Status: `verified`
  Claim: Implemented CDM v2 runtime contracts: added Pydantic models under `domain/cdm`, moved FSM conversion into Tier-3 `ru_worker/cdm_adapters.py`, integrated mapper/worker validation boundaries, and added deterministic `tests/test_cdm_models.py` coverage
  Source_ref: `docs/COMPLETED_LOG.md#L25`
  Last_validated: `2026-03-27`

## Active Blockers

- ID: `BL-001`
  Status: `blocked`
  Claim: `8 — Stability Gate (эксплуатация)` cannot advance until the `STATE` exit conditions are met: ≥30 closed cycles, 0 corruption, Shadow Mode exit (≥50 req, ≥90% match)
  Source_ref: `docs/autopilot/STATE.md#L18`
  Last_validated: `2026-03-27`
- ID: `BL-002`
  Status: `blocked`
  Claim: `ROADMAP` contains a live drift for `8 — Stability Gate (эксплуатация)`: one snapshot marks it active, another still marks it not started.
  Source_ref: `docs/EXECUTION_ROADMAP_v2_3.md#L101; docs/EXECUTION_ROADMAP_v2_3.md#L702`
  Last_validated: `2026-03-27`
- ID: `BL-003`
  Status: `blocked`
  Claim: `ROADMAP` still shows `R1` as not started in one snapshot while other roadmap text says the track is active in practice.
  Source_ref: `docs/EXECUTION_ROADMAP_v2_3.md#L95; docs/EXECUTION_ROADMAP_v2_3.md#L708`
  Last_validated: `2026-03-27`

## Open Hypotheses

- ID: `HY-001`
  Status: `open`
  Claim: doc audit / SOP cleanup after current R1 milestone
  Source_ref: `docs/autopilot/STATE.md#L17`
  Last_validated: `2026-03-27`

## Next Approved Item

Status: `open`
Claim: Continue `8 — Stability Gate (эксплуатация)` until the `STATE` exit criteria are satisfied.
Source_ref: `docs/autopilot/STATE.md#L8-L18`
Last_validated: `2026-03-27`

## Manual Addendum

- None.
