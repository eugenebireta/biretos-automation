---
audit_id: 2026-04-18_claude-code-setup-optimization
date: 2026-04-18T15:35:00
duration_min: 12
models:
  advocate: claude-sonnet-4-6
  challenger: gemini-2.5-flash
  second_opinion: claude-haiku-4-5
gemini_real: true
r2_ran: true
r2_skip_reason: null
r1:
  advocate: APPROVE/6
  challenger: REVISE/8
  second_opinion: REVISE/6
r2:
  advocate: REVISE/7
  challenger: REVISE/8
  second_opinion: REVISE/7
advocate_flipped: true
final_verdict: REVISE
cost_usd_estimate: 0.25
owner_decision: null
outcome: null
decision_class: D3
topic_type: general
tier_used: 1
meta_5th_concern: "Отсутствует pre-deployment testing regime как отдельный deliverable — все три аудитора рекомендовали audit-mode, но никто не включил его как P0.0 в план. Это subsumes false-positive, measurement gap и 3-way orchestration concerns."
unknowns_that_flip_verdict:
  - "Baseline количества destructive attempts в логах текущих сессий — измерение не проводилось"
  - "Реализация dynamic DNA §3 sync в frozen_guard (hardcoded list vs grep-at-runtime)"
  - "Scope bash_guard regex — file-target vs command-global (sed -i frozen vs sed -i /tmp)"
  - "3-way hook orchestration: safe_exec(VPS) + bash_guard(local) + claude-mem"
  - "Claude Code public docs об hook execution order при нескольких PreToolUse на одном matcher"
code_verified:
  advocate: true
  challenger: false
  second_opinion: true
discovery_facts_shown: []
hard_gate_triggered: null
decision_class_note: "Bundle builder auto-tagged D5/data_pipeline = FALSE POSITIVE (из-за упоминания FROZEN/pipeline в защитном контексте). True class: D3 infra/reversible, topic_type=general. Все 3 аудитора отметили это в отчётах."
---

# AI-Audit: Claude Code Setup Optimization (P0-P3)

## Bundle summary

Предложение: 14 элементов в 4 уровнях (P0=hooks+audit-skill, P1=subagents+memory+statusline, P2=MCP servers, P3=SessionStart hook+CLAUDE.md refactor+global defaultMode change).

Текущее состояние (verified): 12 global / 27 project allow / 15 deny правил. 1 plugin (claude-mem v12.1.3). CLAUDE.md 761 строк. Memory 179 файлов, MEMORY.md 166 строк. Нет .claude/agents/, .claude/skills/, .claude/hooks/, .mcp.json.

## R1 verdicts

### ADVOCATE (Sonnet): APPROVE/6
Steelman points:
1. 9/19 FROZEN FILES защищены только промптом — реальный gap (verified: grep settings.json)
2. Нет Bash(ssh*)/Bash(docker*) в deny — destructive SSH не перехватываются
3. Proposal не трогает FROZEN/PINNED surface (disjoint scopes)
4. Pattern hooks проверен claude-mem (workable)
5. Полная обратимость через git revert

Caveat: regex false positives — использовать `exit 2` (ask) вместо `exit 1` (hard block).

unknowns_that_flip: claude-mem hook ordering, полнота bash_guard паттернов, global defaultMode impact.

### CHALLENGER (Gemini Flash): REVISE/8
Concerns (по severity):
1. CRITICAL: PreToolUse(Bash) regex false positives блокируют легитимные операции
2. HIGH: frozen_guard drift vs DNA §3 (hardcoded list desync)
3. HIGH: /audit skill + subagents зависают в циклах
4. HIGH: claude-mem hook-ordering conflict
5. HIGH: global defaultMode broad impact
6. MEDIUM: MCP latency
7. LOW: bundle misclassification D5/data_pipeline

Альтернатива: gradual rollout через audit-mode (log-only) перед блокировкой.

### SECOND_OPINION (Haiku): REVISE/6
Checklist FAIL/FLAG:
- FAIL: trade-off скрыт, benefit не измерен (нет baseline)
- FAIL: scope недоопределён — PreToolUse(Bash) затронет DR/enrichment/Phase 3A
- FAIL: risk регрессий (regex false-positives ломают grep/awk)
- FAIL: bundle miscategorization D5/data_pipeline ложный
- FLAG: hook-ordering, measurement strategy

Top-1 предложение: **Deploy ONLY P0.2 (frozen_guard) immediately, skip P0.1+P0.3 until regex audit-mode complete (1-2 weeks).**
REJECT: P1.6 (claude-mem dedup), P3.14 (global defaultMode).

## R2 debate

### ADVOCATE R2: APPROVE → REVISE/7 (flipped)
`reason_class: new_argument` (аудитор A2: drift frozen_guard vs DNA §3 — не рассматривал в R1).

**КРИТИЧЕСКИЙ FACT-CHECK**: прочитал claude-mem `hooks.json` v12.1.3 — PreToolUse зарегистрирован **ТОЛЬКО на matcher="Read"**. На Write/Bash claude-mem хуков нет.
→ **hook-ordering conflict для Write/Bash опровергнут фактами.** Снимает один HIGH concern.

Root cause (≤20 слов): "Proposal spec неполная — отсутствуют scope boundaries, regex audit-mode, и dynamic DNA sync."

### SECOND_OPINION R2: REVISE/7 (поднял confidence)
`reason_class: new_argument` (`safe_exec.sh` уже на VPS — локальный bash_guard дублирует enforcement).

Root cause: "Regex false positives defeat legitimate introspection; safe_exec already guards VPS; local bash_guard must NOT overlap."

### CHALLENGER R2: REVISE/8 (no change)
`reason_class: no_change`. Ответ на exit 2 vs exit 1: "Ask-pause по-прежнему прерывает рабочий процесс."

Root cause: "Недостаточная спецификация proposal'а и неопределённость взаимодействий компонентов."

## Meta 5th-concern check

**Обнаружено:** все три аудитора рекомендовали audit-mode / testing как mitigation, но никто не включил **pre-deployment testing framework как отдельный deliverable P0.0**. Это meta-gap subsumes concerns #1 (false positives), #3 (claude-mem conflict), #6 (measurement missing).

## Arbiter decision (Opus)

**Final verdict: REVISE (highly likely consensus)**

Направление единогласное: не деплоить P0-P3 целиком, идти гранулярно.

### Приоритизированный план (замена original P0-P3)

| # | Элемент | Вердикт | Комментарий |
|---|---------|---------|-------------|
| 0 | **P0.0 Testing framework** (NEW) | APPROVE — сделать первым | `.claude/hooks/_test/` + mode=log-only по умолчанию. Без этого остальное небезопасно. |
| 1 | **P0.2 frozen_guard** | APPROVE с условием | Hook читает DNA §3 **динамически** (grep), не hardcoded. Fail-closed если DNA отсутствует. |
| 2 | **P0.1 bash_guard** | DEFER до P0.0 | 1-2 недели audit-mode (exit 0, log-only) → tune patterns → `exit 2` (ask). Never `exit 1`. |
| 3 | **P0.3 /audit skill** | DEFER | После stabilization P0.2. Требует subagent loop testing. |
| 4 | P1.4 subagents | PROCEED отдельным batch | Low risk. После P0.2. |
| 5 | P1.5 status line | PROCEED | Ergonomic, no risk. |
| 6 | P1.6 memory cleanup | PROCEED | Low risk. |
| 7 | P1.7 UserPromptSubmit liveness | REJECT | CLAUDE.md уже имеет LIVENESS OVERRIDE. Дублирование + false-negative risk. |
| 8 | P2.8 biretos-mcp | DEFER | После P0+P1. Бонус, не защита. |
| 9 | P2.9 MySQL MCP | DEFER | Тот же аргумент. |
| 10 | P2.10 GitHub MCP | DEFER | Тот же аргумент. |
| 11 | P3.11 SessionStart hook | DEFER | После P0 stabilization. |
| 12 | P3.12 Stop hook | DEFER | То же. |
| 13 | P3.13 Вынос AI-Audit spec из CLAUDE.md | APPROVE | Docs organization, обратимо, экономит input-токены. |
| 14 | P3.14 Global defaultMode change | REJECT | Слишком broad scope. Только project-level если нужно. |

### Последовательность работы (минимальный blast-radius)

1. **Неделя 1**: P0.0 (testing framework) + P3.13 (docs refactor) — обратимо, не затрагивает runtime.
2. **Неделя 2**: P0.2 frozen_guard с dynamic DNA §3 sync + P0.1 bash_guard в **audit-mode** (log-only). Сбор baseline.
3. **Неделя 3-4**: анализ audit-mode log → tune patterns → P0.1 перевести в ask-mode (`exit 2`).
4. После стабилизации: P1.4/P1.5/P1.6 одним batch.
5. Остальное — отдельный track.

### owner_decision_required

Три пути для владельца:
- **A) ACCEPT** — следовать пересмотренному плану (P0.0 → P0.2 → audit-mode P0.1).
- **B) MINIMAL** — только P3.13 (docs refactor) + P0.2 (frozen_guard). Остальное не трогать.
- **C) ESCALATE Tier 4 Deep Research** — глубокое исследование (1) Claude Code hook execution model, (2) community-vetted regex patterns для destructive-command filtering, (3) biretos-mcp дизайн. Оправдано если владелец хочет production-grade решение, а не пилот.
