# Deep Research Brief — Claude Code Setup Optimization для biretos-automation

**Дата:** 2026-04-18
**Инициатор:** Owner (eugene.bireta@gmail.com)
**Происхождение:** Tier 1 AI-Audit вердикт REVISE ([_scratchpad/ai_audits/2026-04-18_claude-code-setup-optimization.md](../ai_audits/2026-04-18_claude-code-setup-optimization.md)) → Tier 4 эскалация по запросу владельца.
**Контекст:** "Я беспокоюсь, как бы ты мне что-нибудь не сломал." Требуется production-grade дизайн, не пилот.

---

## Инструкция для Claude Deep Research

Это brief для запуска в **claude.ai → Deep Research**. Вставь содержимое целиком в Deep Research prompt. Результат верни в этот файл (добавь новую секцию `## Deep Research Findings`) или в отдельный `2026-04-18_claude-code-setup-deep-research-findings.md`. После — арбитр (Claude Code Opus в локальном репо) финализирует арбитраж AI-Audit.

---

## Контекст проекта (1 абзац)

`biretos-automation` — Autonomous B2B Decision & Execution Engine для продуктового каталога (~374 SKU: Honeywell, PEHA, Phoenix Contact). Claude Code используется как координатор/executor. Проект имеет строгий governance (PROJECT_DNA §3 — 19 frozen files, §4 — pinned API, §5 — Tier-3 prohibitions). Есть уже работающая AI-Audit инфраструктура (ADVOCATE/CHALLENGER/SECOND_OPINION через bundle_builder.py + Gemini). Установлен `claude-mem@thedotmack v12.1.3` plugin с активными hooks. VPS имеет `safe_exec.sh` для destructive SSH.

---

## Что Tier 1 AI-Audit уже подтвердил (не повторять в Deep Research)

**Final verdict: REVISE.** Гранулярный подход:
- ✅ APPROVE: P0.2 frozen_guard (с dynamic DNA §3 sync), P3.13 вынос AI-Audit spec
- ⏸️ DEFER: P0.1 bash_guard, /audit skill, MCP серверы, subagents
- ❌ REJECT: P3.14 global defaultMode, P1.7 liveness hook

Факты из R1/R2:
- `claude-mem` регистрирует PreToolUse **только на matcher="Read"** (verified hooks.json lines 61-71). Конфликт с PreToolUse(Write) не существует.
- `safe_exec.sh` уже защищает VPS destructive SSH (CLAUDE.md §DESTRUCTIVE OPS lines 465-494).
- 9/19 FROZEN FILES защищены только промптом, 10/19 — через `.claude/settings.json` Write-deny.
- Bundle builder ложно tagged D5/data_pipeline — настоящий класс D3/general.

**Не тратьте Deep Research токены на подтверждение этих findings. Фокус — на 7 Open Questions ниже.**

---

## Open Questions для Deep Research

### Q1. Claude Code hooks — execution semantics

**Вопрос:** Документация Anthropic на hooks тонкая. Нужны точные ответы:
1. Если две разных конфигурации регистрируют `PreToolUse` на один matcher (например, оба на `"*"` или оба на `"Write"`) — в каком порядке они выполняются? Global first? Plugin first? Project first? Алфавитный?
2. Если один hook вернёт `exit 1` (block) — вызывается ли следующий в цепочке? Или цепочка прерывается?
3. Какая разница между `exit 1` (block) и `exit 2` (ask-pause) фактически в UI Claude Code?
4. Timeout behaviour: что происходит при exceed timeout — block (fail-closed) или allow (fail-open)?
5. Stderr output — отображается владельцу в UI? Или только в logs?
6. Поддерживается ли priority/order field в `hooks.json` / `settings.json`?
7. Могут ли hooks читать `$CLAUDE_TOOL_ARGS` с полными аргументами (для Write/Edit — какой путь)? Какова схема environment variables, доступных hook-script'у?
8. Есть ли разница между `settings.json hooks` и `plugin hooks.json`? Порядок какой?

**Источники:** docs.anthropic.com, code.claude.com, github.com/anthropics/claude-code, публичные issue-trackers, community blog posts.

### Q2. Best-practice regex patterns для destructive Bash detection

**Вопрос:** Какие community-vetted regex-patterns существуют для детекции destructive shell commands? Нужен сравнительный обзор:
1. `gitleaks`, `pre-commit.com`, `trufflehog` — какие regex используют для detection сенситивных команд (не credentials, а destructive)?
2. OWASP Shell Injection Cheat Sheet — есть ли рекомендации?
3. Google Shell Style Guide / Bash strict mode — есть ли паттерны defense?
4. Open-source policy-as-code (OPA, Falco) — rules для detection `rm -rf`, `DROP TABLE`, `docker compose down`, `systemctl stop`, `mkfs`, `dd`?
5. Какие известные false-positive cases для таких regex? (`sed -i`, `find -delete`, `grep -r`, `ls -r`...)
6. Паттерн "scope-aware": как различить `sed -i safe_file` vs `sed -i frozen_file` на уровне regex? Возможно ли без parse?
7. Есть ли published false-positive / false-negative rates для конкретных pattern наборов?

**Deliverable:** таблица паттернов с severity + known FP cases + recommended action (block/ask/log).

### Q3. Audit-mode (log-only) hook implementation

**Вопрос:** Как правильно реализовать "log-only mode" для PreToolUse hook в shell-скрипте?
1. Pattern для structured logging — JSON lines? syslog? OpenTelemetry?
2. Как лучше хранить: local file (rotation?), stdout-to-CLI, Telegram bot, Postgres?
3. Какие metrics собирать для false-positive rate calculation? (command_hash, matched_pattern, timestamp, session_id, allowed/blocked, follow-up action)
4. Какой минимум данных для later A/B decision "turn on blocking"?
5. Существующие tools: `auditbeat`, `auditd`, `falco` — применимы ли к Claude Code hooks?
6. Privacy: могут ли hook logs содержать PII / secrets? Как санитизировать?

**Deliverable:** референс-имплементация `.claude/hooks/_log_only.sh` с rotation и sanitization.

### Q4. MCP server architecture для biretos-mcp

**Вопрос:** Дизайн собственного MCP-сервера для wrap AI-Audit / DR / evidence tools. Требования:
1. Performance: MCP session должен стартовать <2s, response на tool call <500ms p95.
2. Error handling: graceful degradation при недоступности underlying script.
3. Auth: нужна ли auth между MCP и Claude Code? (стандарты MCP — stdio? HTTP+auth?)
4. Observability: structured logging, metrics, traces.
5. Как integrate с существующим AI-Audit (`ai_audit/bundle_builder.py`, `gemini_call.py`, `build_index.py`)? Wrapper vs rewrite?
6. Python vs TypeScript — что быстрее запускается в MCP context?
7. Hot-reload: можно ли обновлять MCP без restart Claude Code session?
8. Security: если MCP выполняет Python scripts с secrets — как изолировать?
9. Есть ли примеры mature MCP servers от Anthropic / community, которые обёртывают workflow scripts?

**Deliverable:** архитектурный diagram + выбор stack + skeleton for `.claude/mcp/biretos-mcp/`.

### Q5. Dynamic DNA §3 sync для frozen_guard hook

**Вопрос:** P0.2 frozen_guard должен читать список FROZEN FILES из `docs/PROJECT_DNA.md §3` динамически, не hardcoded (critical finding из R2 AI-Audit). Подходы:
1. Parse markdown §3 at runtime на каждом PreToolUse(Write) — latency concern?
2. Cache: generate `.claude/hooks/_cache/frozen_list.txt` по hash DNA.md + refresh если hash изменился?
3. Daemon: long-running process который watches DNA.md и обновляет список?
4. Git pre-commit hook: regenerate cache при commit'е DNA.md?
5. Fail-safe behaviour: что делать если DNA.md отсутствует / parse failed? **Fail-closed (block все writes) или fail-open (allow)?**
6. Пример markdown-section parsing в shell (grep/awk/sed): robust pattern для `## 3. ... (19 файлов...)` → `## 4. ...`?
7. Безопасность: как защититься от инъекции в DNA.md (если атакующий добавит маркер "## 4." выше §3)? Hash verification?

**Deliverable:** референс-имплементация с benchmark latency (<10ms hot-cache, <100ms cold-parse).

### Q6. claude-mem plugin integration — не конфликты

**Вопрос:** У нас установлен `claude-mem@thedotmack v12.1.3`. Он использует hooks: Setup, SessionStart, UserPromptSubmit, PreToolUse(Read), PostToolUse, Stop, SessionEnd + локальный MCP worker на `:37777`.
1. Задокументировано ли поведение claude-mem при наличии project-level hooks на те же matchers?
2. Если я добавлю project-level `UserPromptSubmit` hook — перекроет он claude-mem UserPromptSubmit или будут выполнены оба?
3. Timeout claude-mem PreToolUse(Read) = 2000ms. Как это взаимодействует с моим PreToolUse(Write)?
4. Порт `:37777` — конфликтует ли если я добавлю свой MCP на другой порт / stdio?
5. Есть ли public stance от @thedotmack на integration с project-level configs?
6. Альтернативы: migrate away from claude-mem, или полная интеграция через его API?

**Deliverable:** integration manifest + known conflict list + mitigation.

### Q7. Production examples of mature `.claude/` configurations

**Вопрос:** Нужны реальные примеры open-source repos с production-grade `.claude/` setup:
1. GitHub search `path:.claude/settings.json stars:>100` — какие есть?
2. Repos с `.claude/hooks/` — какие паттерны hook chaining они используют?
3. Repos с `.claude/agents/` — как структурированы subagents?
4. Repos с `.mcp.json` — какие MCP servers популярны в engineering teams?
5. Есть ли "reference" setup от Anthropic для большого Python проекта?
6. Какие antipatterns видны в неудачных setups (блокирующие hooks, broken regex)?

**Deliverable:** топ-5 reference repos + extracted patterns + antipatterns.

---

## Out of scope для Deep Research

- Enrichment pipeline internals (DR prompts, coverage) — отдельный track.
- Revenue Tier-3 governance (рассмотрено в отдельных docs).
- Shopware / MySQL / VPS infra (отдельный track).
- Ответы на вопросы, уже закрытые в Tier 1 AI-Audit (см. "Что уже подтверждено" выше).

---

## Формат ответа

```markdown
## Deep Research Findings — Claude Code Setup Optimization

### Q1. Hook execution semantics
...findings + cite sources...

### Q2. Destructive Bash regex patterns
...table of patterns + FP cases + recommendations...

... (Q3 — Q7)

### Cross-cutting recommendations
- Revised priority ordering vs Tier 1 plan
- New risks surfaced by deep research
- Open questions remaining after Deep Research
```

Время ожидается: 5-30 минут Deep Research sub-session.
Cost: $0 marginal (subscription).

---

## После получения Findings

Арбитр (Claude Code Opus в репо) интегрирует Deep Research в финальный план:
1. Обновит `_scratchpad/ai_audits/2026-04-18_claude-code-setup-optimization.md` → section `### Tier 4 Addendum`.
2. Пересмотрит приоритизацию (что из DEFER можно ускорить, что из APPROVE нужно пересмотреть).
3. Выдаст final implementation plan владельцу на approve.
