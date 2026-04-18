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
tier_used: 4
tier4_completed_at: 2026-04-18T16:53:00
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

---

## Tier 4 Addendum — Deep Research findings (2026-04-18, 16:53)

Deep Research (claude.ai) ответил на все 7 open questions из brief. Полный отчёт: [_scratchpad/deep_research/2026-04-18_claude-code-setup-deep-research-findings.md](../deep_research/2026-04-18_claude-code-setup-deep-research-findings.md). Ключевые находки, **меняющие план**:

### ⚠️ 5 фактов, которые инвалидируют предположения Tier 1

1. **Хуки выполняются ПАРАЛЛЕЛЬНО, не последовательно.** Anthropic docs: *"All matching hooks run in parallel... Design for independence."* Это **инвалидирует** всю дискуссию R2 о hook-ordering с claude-mem. Координация только через precedence `deny > defer > ask > allow`.

2. **`exit 1` НЕ блокирует** — это "non-blocking error", tool call проходит. Блокирует только `exit 2`. Мой `frozen_guard.py` использует exit 2 — **корректно**.

3. **Default timeout 600s — fail-OPEN.** При таймауте action проходит. Нет встроенного fail-closed timeout. Мой fail-closed на missing DNA работает через explicit exit 2 — **корректно**.

4. **`$CLAUDE_TOOL_ARGS` не существует** (issue #9567). Только stdin JSON. Мой hook использует stdin JSON — **корректно**.

5. **claude-mem v12.0.0+ расширил File Read Gate на PreToolUse(Edit).** При конфликте `deny > allow` — **claude-mem выиграет, мой Edit заблокируется injection timeline**. Митигация: (a) `CLAUDE_MEM_EXCLUDED_PROJECTS=<biretos-path>` env var, ИЛИ (b) drop Edit из matcher, оставить только Write|MultiEdit.

### 🚨 Новый P0 (не был в Tier 1)

**P0 UPGRADE claude-mem → ≥ v12.1.4** (5 минут). v12.1.3 имеет **100% observation-failure bug** при Claude Code ≥ 2.1.109 (commit 3d92684 — empty-string `--setting-sources` corruption). Сейчас Claude Code 2.1.90 — баг ещё не активен, но любой upgrade Claude Code сработает. Blocking для любой дальнейшей работы с memory.

### ✅ Что подтверждено Deep Research

- **P0.2 frozen_guard** (мой Python, 240 строк) — логика correct (stdin JSON, fail-closed via exit 2, bypass env). НО рекомендовано переписать на Bash (~90 строк awk + `flock` cache): Python cold-start 200-400ms vs Bash 6-11ms. Для частых Write/Edit — значимый overhead.
- **Dynamic DNA sync** — моя SHA-256 cache стратегия совпадает с рекомендацией. Awk parser из finding §Q5 более robust чем мой regex (обрабатывает CRLF, nested lists, `## 10.` после `## 9.`).
- **Git pre-commit companion** — новое предложение: при коммите `docs/PROJECT_DNA.md` — автоматически regenerate cache + commit. Сохраняет canonical cache в git для fresh clones и CI.
- **P3.13 CLAUDE.md shrink** — никаких блокеров, proceed.

### 🔄 Revised ladder (Tier 1 → Tier 4)

| Item | Tier 1 verdict | Tier 4 revision | Reason |
|------|---------------|-----------------|--------|
| **NEW** claude-mem upgrade to ≥v12.1.4 | — | **P0 blocking** | 100% observation-failure on CC ≥2.1.109 |
| P0.2 frozen_guard (Python) | APPROVE | **APPROVE с pending rewrite** to Bash (latency) | 200-400ms vs 6-11ms |
| P0.2 matcher `Write|Edit|MultiEdit` | APPROVE | **REVISE → `Write|MultiEdit` only** (drop Edit) | claude-mem Edit Gate conflict |
| P0.2 pre-commit companion | not in plan | **ADD** as part of P0.2 PR | Canonical cache for CI/fresh clones |
| P3.13 spec extraction | APPROVE | APPROVE | unchanged |
| P0.1 bash_guard | DEFER | **PROMOTE to P1 with audit-mode FIRST** | Q2 даёт 21-pattern table + Q3 даёт ~150 строк reference `_log_only.sh`. Можно ship audit-only сегодня (exit 0 always, collect metrics). Through 1000 events → FP<1% → promote to `ask`, потом `deny`. |
| P0.3 /audit skill | DEFER | DEFER (unchanged) | Нужен subagent loop testing |
| P1.4 subagents | PROCEED отдельным batch | **PROCEED + model tier-routing** (Sonnet для hard, Haiku для repetitive) | wshobson/agents паттерн — cut cost 3-5× |
| P1.5 status line | PROCEED | PROCEED | unchanged |
| P1.6 memory cleanup | PROCEED | PROCEED | unchanged |
| P1.7 liveness hook | REJECT | **REJECT reaffirmed** | Parallel execution = can't gate anything |
| P2.8 biretos-mcp | DEFER | **DEFER but stack frozen: FastMCP (Python), library-import, stdio+env, `mask_error_details=True`** | Q4 resolves stack question |
| P2.9-10 MySQL/GitHub MCP | DEFER | DEFER | unchanged |
| P3.11 SessionStart hook | DEFER | **REJECT** — antipattern (ruflo #1530: SessionStart daemons = zombies) | Q7 evidence |
| P3.12 Stop hook | DEFER | **REVISE: use `{"continue":false}` JSON**, not exit 2 | Q7: exit-2 on Stop = infinite loop |
| P3.13 AI-Audit spec externalization | APPROVE | APPROVE | unchanged |
| P3.14 global defaultMode | REJECT | **REJECT reaffirmed** | Enterprise `allowManagedHooksOnly` conflict |

### 🆕 Новые риски, surface'нутые Deep Research

1. **`permissions.deny` silent-bypass bugs** (issues #6699/#8961/#27040). `"deny": ["Read(./.env)"]` может быть silently ignored. **Defense-in-depth PreToolUse hook обязателен, не optional**.
2. **stdio MCP CVE April 2026** (Ox Security / The Register). До ship biretos-mcp — dedicated venv + `.env` outside repo + `gitleaks detect --no-git` в pre-commit.
3. **Hook cascade latency real** — ruflo #1530: 11 hooks × 9 events = 18-21s regression. **Hard budget <100ms на каждом PreToolUse**; benchmark через `hyperfine` перед merge.
4. **claude-mem roadmap на Gate расширения** — v12.0.0 добавил Edit; может расширить на Write. **Pin claude-mem version** в settings.json + мониторить CHANGELOG.
5. **Broad matchers pairing heavy tools с high-frequency events** (Q7 antipattern) — не запускать тяжёлые проверки на каждый Write/Edit; narrow matcher + scope на `Bash(git commit*)`.

### 🎯 Финальный revised plan (Tier 1 + Tier 4 merged)

**Stage 0 (сейчас — 5 минут):**
- [x] PR #52 merged (CLAUDE.md shrink + frozen_guard.py inactive + audit artifacts) — owner ACCEPT pending
- [ ] `claude-mem` upgrade to ≥v12.1.4 (manual, owner action)

**Stage 1 (после PR #52 ACCEPT, 1 день):**
- [ ] Drop `Edit` из frozen_guard matcher (keep `Write|MultiEdit`)
- [ ] Set `CLAUDE_MEM_EXCLUDED_PROJECTS=$PWD` в `.claude/settings.json` ИЛИ переписать на Bash для consistency
- [ ] Добавить git pre-commit companion для frozen cache refresh
- [ ] Активировать frozen_guard в `.claude/settings.json` (matcher на Write только)
- [ ] Benchmark latency через `hyperfine` (<100ms cap)

**Stage 2 (1-2 недели, параллельно с Stage 1 работой):**
- [ ] bash_guard **audit-mode only** (exit 0 always, JSONL logging через Q3 reference). 21-pattern table из Q2.
- [ ] После 1000+ events → analyze FP rate → promote rules в `ask` или `deny` индивидуально.

**Stage 3 (после Stage 2 stabilization):**
- [ ] subagents с model tier-routing (Sonnet/Haiku split)
- [ ] status line
- [ ] memory cleanup
- [ ] biretos-mcp (FastMCP, если нужен по value)

**REJECTED permanently:**
- P1.7 liveness hook (parallel execution breaks gating)
- P3.11 SessionStart daemon hook (antipattern)
- P3.14 global defaultMode (enterprise conflict)

### Revised final_verdict

**REVISE → PROCEED** (по merge-plan выше). Deep Research подтвердил направление Tier 1, но конкретизировал stack и добавил 1 критичный P0 (claude-mem upgrade) + несколько технических исправлений.
