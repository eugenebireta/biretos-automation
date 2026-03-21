# PromptOps Commands (Fallback Templates)

Purpose: если в проекте не настроен нативный формат Cursor custom commands, используйте эти короткие однострочные триггеры прямо в чате Cursor.

Global rule for all commands: no action phase starts without explicit `approve`.

## `/risk`

- What it does: фиксирует уровень риска и маршрут pipeline.
- Output format:
  - `RISK: <LOW|SEMI|CORE>`
  - `PIPELINE: <phase->phase>`
  - `WAITING_FOR_APPROVE`

## `/scout`

- What it does: read-only разведка scope и фактов.
- Output format:
  - `Scope Confirmed`
  - `Files Observed`
  - `Facts`
  - `Risks`
  - `WAITING_FOR_APPROVE`

## `/arch`

- What it does: архитектурный дизайн в рамках риска.
- Output format:
  - `Risk Classification`
  - `Proposed Scope`
  - `Design Decision`
  - `Safety Constraints`
  - `WAITING_FOR_APPROVE`

## `/critic`

- What it does: независимая критика и проверка DNA/INV-GOV.
- Output format:
  - `Verdict: PASS|PASS_WITH_FIXES|BLOCK`
  - `Findings by Severity`
  - `Required Fixes`
  - `WAITING_FOR_APPROVE`

## `/plan`

- What it does: детальный план реализации без правок.
- Output format:
  - `Scope`
  - `Step Plan`
  - `Validation Plan`
  - `WAITING_FOR_APPROVE`

## `/build`

- What it does: реализация approved-плана.
- Output format:
  - `Files Changed`
  - `What Implemented`
  - `Safety Checks`
  - `Validation Result`
  - `WAITING_FOR_REVIEW`

## `/audit`

- What it does: пост-аудит результата по чек-листу DNA.
- Output format:
  - `Audit Verdict`
  - `Checklist Results`
  - `Deviations`
  - `Recommendation`

## `/validate`

- What it does: быстрая compliance-проверка перед build/audit.
- Output format:
  - `Boundary Check`
  - `Risk Check`
  - `Governance Check`
  - `Result: READY|BLOCKED`

## `/cleanup`

- What it does: сокращает ответ до actionable next-step и артефактов handoff.
- Output format:
  - `Keep`
  - `Drop`
  - `Next Prompt`

## `/pack`

- What it does: собирает краткий handoff пакет для внешнего JUDGE (CORE only).
- Output format:
  - `Task`
  - `Risk`
  - `Architect Summary`
  - `Critic Findings`
  - `Open Questions`
