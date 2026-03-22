# MIGRATION POLICY v1.0
## Claude Code Transition for Biretos Automation

**Согласовано:** Claude Opus 4.6 (JUDGE) + GPT High Thinking (CRITIC/AUDITOR)
**Дата:** 2026-03-15
**Статус:** APPROVED

---

## 1. Purpose

Цель миграции — сократить личное время владельца у экрана и уменьшить
manual_interventions, не нарушая архитектурные инварианты проекта,
Safety-first логику и governance для 🔴 CORE.

## 2. Source of Truth

Источником истины остаются:

- MASTER_PLAN_v1_9_0.md
- EXECUTION_ROADMAP_v2_3.md
- PROJECT_DNA_v2_0.md (включая §12 Workflow Compression)

Эта policy не заменяет эти документы.
Она задаёт режим использования Claude Code внутри существующей конституции.

## 3. Fixed Tool Stack

| Роль | Инструмент |
|------|------------|
| Primary Builder / Executor | Claude Code |
| Parallel LOW Builder | Codex app |
| External CRITIC | GPT high thinking |
| External AUDITOR | GPT high thinking |
| JUDGE | Отдельный Claude-чат (внешний контекст) |
| CI | GitHub Actions |
| Orchestrator | Windmill |
| Fallback | Cursor + Autopilot |

## 4. Honest Limitation

Claude Code выполняет роли SCOUT/ARCHITECT/PLANNER/BUILDER в одной среде.
Это owner-approved temporary workflow compression, а не буквальное
сохранение исходного INV-GOV. Для 🔴 CORE задач компрессия ограничена
Strict Mode (два отдельных прохода с паузой между ними).

## 5. Risk Routing

| Risk | Режим |
|------|-------|
| 🟢 LOW | Claude Code, review по необходимости |
| 🟡 SEMI | Claude Code + внешний GPT review |
| 🔴 CORE | Claude Code только через Strict Mode |

## 6. CORE Strict Mode

Для каждой 🔴 CORE задачи обязателен следующий порядок:

```
Pass 1 — Claude Code: SCOUT + ARCHITECT
  Завершается WAITING_FOR_OK. Кодогенерация запрещена.

Pass 1.5 — Owner Quick Check:
  git diff --stat. Если Tier-1 файл в списке → STOP. 30 сек.

Pass 2 — Claude Code: PLANNER + BUILDER
  Только после approved Pass 1.

Pass 2.5 — Owner Quick Check:
  git diff --stat. Если Tier-1 файл в списке → STOP. 30 сек.

Pass 3 — GPT: CRITIC (отдельный промпт)

Pass 4 — GPT: AUDITOR (отдельный промпт)

Pass 5 — JUDGE: отдельный Claude-чат
```

Для 🔴 CORE запрещены:
- Relaxed Mode
- Один-pass execution
- Объединение CRITIC и AUDITOR
- Merge без JUDGE
- Пропуск WAITING_FOR_OK между Pass 1 и Pass 2

## 7. Mandatory Hardening Before First CORE

До первого запуска Claude Code на 🔴 CORE обязательно:

- CLAUDE.md в корне repo
- .claude/settings.json с permissions deny на frozen files
- PreToolUse hooks для блокировки protected writes
- git pre-commit guard
- CI guards (Hash Lock, Boundary Grep, DDL Guard)
- branch protection на master

## 8. Mandatory Hard Guards

- deny write в frozen / Tier-1 / invariant files
- deny read для secrets / .env
- deny dangerous bash/network actions
- PreToolUse(Edit|Write|Bash) блокирует protected paths до выполнения
- direct merge в master запрещён
- CI обязателен: Hash Lock / Boundary Grep / DDL Guard / tests green
- Claude Code не имеет права обходить Guardian / Governance constraints
- Claude Code не имеет права менять risk classification задачи

## 9. Mandatory Automated Pre-Run Snapshot

Перед каждым запуском на 🟡 SEMI и 🔴 CORE автоматически:

- копировать docs/autopilot/STATE.md
- копировать CAPSULE.md
- складывать в timestamped папку backups/claude-pre-run/
- писать manifest (timestamp, task_id, risk_level, branch, commit_hash)

Для 🔴 CORE snapshot обязателен и неотключаем.

## 10. Gates

### READY

- hooks / sandbox / permissions реально работают
- CI стабильно зелёный
- 3 LOW/SEMI задачи прошли без architectural violations
- 1 контролируемо-проваленная задача для failback drill
- Zero-Memory Reset отработан
- fallback в Cursor + Autopilot сработал clean

### CORE-APPROVED

- 2–3 CORE strict-runs прошли успешно
- CRITIC и AUDITOR были раздельными
- JUDGE не нашёл architectural violation
- diff quality не хуже fallback-контура
- экранное время владельца реально снизилось

После CORE-APPROVED: Claude Code = primary builder для CORE,
но только через Strict Mode.

## 11. What Is Forbidden

- Называть CLAUDE.md hard enforcement
- Включать Relaxed Mode для 🔴 CORE
- Убирать раздельные CRITIC и AUDITOR
- Убирать JUDGE
- Отключать sandbox / hooks
- Менять Windmill в рамках этой миграции
- Удалять Cursor fallback до CORE-APPROVED
- Считать один проход Claude достаточным для CORE

## 12. Failback Policy

Если Claude Code:
- трогает protected path
- даёт unsafe diff
- проваливает внешний review
- дважды подряд срывает CORE strict-run
- нарушает boundaries / invariants / frozen rules

тогда:
1. Задача уходит в Cursor + Autopilot
2. Claude Code снимается с CORE
3. Claude Code остаётся только для LOW/SEMI
4. Zero-Memory Reset
5. Повторный допуск только после нового hardening + shadow-run

## 13. Zero-Memory Reset

- Завершить текущую Claude Code session
- Не переносить reasoning/context в fallback
- Начать fallback как новый чистый цикл
- Опираться только на STATE.md, CAPSULE.md, PROJECT_DNA, diff, CI evidence

## 14. GPT Review Templates

### CRITIC prompt:

```
Ты — внешний CRITIC проекта Biretos Automation.

PROJECT_DNA: [вставить DNA]

PLAN/ARCHITECTURE от Claude Code: [вставить результат Pass 1]

Проверь:
1. Архитектурный drift
2. Нарушение DNA — frozen files, pinned API, prohibitions
3. Missing invariants
4. Hidden coupling
5. Overengineering
6. (зарезервировано)
7. (зарезервировано)
8. NLU wrapper check — AI слои остаются обёрткой над TaskIntent, без собственной mutation path или second FSM
9. Degradation safety — Level 1/2 не повышает права и не обходит INV-MBC

VERDICT: OK / FIX / STOP
WHY: 1-3 причины
IMPROVEMENTS: 1-3 улучшения
```

### AUDITOR prompt:

```
Ты — внешний AUDITOR проекта Biretos Automation.

PROJECT_DNA: [вставить DNA]

DIFF от Claude Code: [вставить git diff]

Проверь:
1. Не затронуты ли Tier-1 frozen файлы (§3)
2. Не изменены ли pinned API сигнатуры (§4)
3. Нет ли запрещённых импортов/DML (§5)
4. Revenue таблицы с prefix rev_*/stg_*/lot_* (§5b)
5. trace_id + idempotency_key присутствуют (§6)
6. Нет ли silent error swallowing (§7)
7. Diff соответствует заявленному плану
8. INV-MBC proof — без button confirmation mutation path недостижим
9. Shadow isolation — shadow_mode не пишет в production decision path
10. Нет nested FSM / decision engine в нарушение DNA §5b

VERDICT: OK / FIX / STOP
WHY: 1-3 причины
IMPROVEMENTS: 1-3 улучшения
```

## 15. Final Rule

Для 🔴 CORE скорость не может быть основанием для ослабления governance.

Claude Code = новый основной builder.
GPT = внешний CRITIC + AUDITOR.
Этот чат = JUDGE.
Windmill = единственный orchestrator.
Strict Mode for CORE = обязательно.
Relaxed Mode = только для LOW/SEMI.

---

END OF POLICY
