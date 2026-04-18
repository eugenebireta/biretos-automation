# CLAUDE.md — Biretos Automation

## CHAT LIVENESS OVERRIDE (highest priority)

If the user message is a short liveness check or tiny conversational prompt
(examples: "ты тут?", "ok", "ping", "проверь связь"), Claude MUST:

1. Reply in one short sentence immediately.
2. Not start any workflow/pipeline/phase protocol.
3. Not run tools, not scan files, not propose plan, not require approvals.
4. Ignore task-completion automation rules for that turn.

This override applies only to that single liveness/conversational turn.

## AI-AUDIT (ad-hoc multi-LLM second opinion) — v0.5

**Spec evolution:** v0.5 adds 10 improvements on top of earlier v0.4 — 4-tier escalation ladder (External 3-chat, Deep Research), mandatory `Read` / `Grep` for Claude agents, LINEAGE_TRACER role for data-pipeline topics, meta-check 5th-concern phase, root-cause synthesis in R2, concrete-example requirement, unknowns-that-flip section, D1-D5 risk-class in bundle, external-by-default for durability claims. Full change-list: `docs/_governance/AI_AUDIT_V05_PROPOSAL.md`.

Триггеры в реплике владельца: **любое упоминание** слов `"AI-аудит"`, `"API-аудит"`, `"ИИ-аудит"`, `"AI audit"` в любом падеже/контексте, либо фразы `"второе мнение"`, `"прогони через ИИ"`, `"проверь решение через ИИ"`, `"что скажут другие ИИ"`.

Не требуется императивная форма — достаточно, что слово "AI-аудит" прозвучало в реплике. Пример: "думаю мигрировать на X, AI-аудит бы" — это триггер, запускать.

**Исключение:** если владелец говорит про AI-аудит **в теоретическом ключе** (обсуждаем саму фичу, её настройки, цену, как она работает) — не запускать. Запускать только когда есть конкретное решение/предложение в контексте, которое можно аудировать.

Без триггера — не запускать.

### Процедура

1. **Собрать bundle через `python ai_audit/bundle_builder.py`** (v0.5): суть предложения, альтернативы, в чём сомнение. Builder авто-инжектит `relevant_docs_excerpts` (DNA / MASTER_PLAN §§ по keywords из bundle), `decision_class` (D1-D5 из MASTER_PLAN DECISION_CLASSES), `topic_type` (для routing LINEAGE_TRACER vs SECOND_OPINION). Если обязательных полей не хватает — спросить одним сообщением, не анкетой.
2. **Переспросить экономию:** если задача обратимая/мелкая ("поменять строчку", "попробовать промпт"), переспросить один раз: "это точно тянет на аудит? решение обратимое". Если подтвердил — запустить.
3. **Round 1 — параллельно 3 агента через Agent-тул, изолированно:**
   - ADVOCATE (Claude Sonnet 4.6 через Agent-тул) — сильнейший аргумент ЗА
   - CHALLENGER (**Gemini 2.5 Flash** по умолчанию, **Gemini 2.5 Pro + extended thinking при эскалации** — см. раздел "Эскалация CHALLENGER" ниже) через `python ai_audit/gemini_call.py --prompt "..." --system "..." [--escalate]` — сильнейший аргумент ПРОТИВ. ОБЯЗАТЕЛЬНО через этот скрипт — иначе будет Claude вместо Gemini.
   - SECOND OPINION (Haiku 4.5 через Agent-тул) — независимая оценка по чек-листу, **ИЛИ LINEAGE_TRACER если `bundle.topic_type ∈ {data_pipeline, etl, ingest, data_drift, data_loss, coverage_regression}`** (v0.5).
   Роль-промпты (v0.5) — выделенные файлы в `docs/prompt_library/roles/ai_audit/`:
   - ADVOCATE → `ai_audit/ADVOCATE.md`
   - CHALLENGER → `ai_audit/CHALLENGER.md` (передать как `--system` в `gemini_call.py`)
   - SECOND_OPINION → `ai_audit/SECOND_OPINION.md`
   - LINEAGE_TRACER → `ai_audit/LINEAGE_TRACER.md` (conditional)
   Claude-агенты (ADVOCATE / SECOND_OPINION / LINEAGE_TRACER) в промпте **обязаны `Read docs/PROJECT_DNA.md` + `docs/MASTER_PLAN_v1_9_2.md` + `Grep` по affected scope** и цитировать §N / file:line (v0.5 fix для "vibes-only violations").
   Ни один из них не видит других в Round 1 — чтобы избежать конформизма.

   **Code verification — ответственность АРБИТРА (меня), ПЕРЕД R1, не аудиторов.** R1 аудиторы работают слепыми (правило выше). Значит факты в bundle (счёт нарушений, file:line, table names, size estimates) НЕ МОГУТ проверять они — они получают bundle как есть. Значит проверяю Я, ДО запуска R1.

   **Правило pre-audit sanity (я, Opus):**
   > Если bundle содержит числовые утверждения о коде (N violations, M lines, K файлов, Y скриптов) — я ОБЯЗАН до R1 подтвердить каждое число независимым grep/read/ls. Владелец мог ошибиться в счёте (бывало). Если моя проверка расходится с bundle — я поправляю bundle ПЕРЕД запуском R1 и явно сообщаю владельцу "audit updated: claimed X, actual Y".

   **Pre-audit sanity checklist:**
   1. Файлы из bundle существуют? (ls)
   2. Commits/refs реальны? (git show)
   3. Числовые счёта (violations, lines, SKUs и т.п.) — grep/wc подтверждают?
   4. Ссылки на CI-правила, rules файлы — актуальны? (grep в .github/ / docs/)
   5. Если расхождение — обновить bundle и сообщить владельцу.

   **Правило вытащено из аудита 2026-04-18 `pr-blocker-iron-fence-m3b`:** bundle заявлял "8 violations (2 ru_worker + 6 side_effects)", реально 12 (4+6+2). Все 3 аудитора честно работали на ложных цифрах. Pre-audit sanity-check выполнил я, но поверхностно — не прошёл по полному TIER3_DIRS scope. Владелец нашёл пропущенное сам. Outcome: `partial` — главная рекомендация (Variant A) верна, но factual base занижена.

   **Discovery — пост-R1 гейт арбитра, НЕ пре-R1 инпут.** Аудиторы в R1 работают СЛЕПЫМИ к текущей системе — видят только предложение владельца и контекст разговора. Это преднамеренно: без анкеринга на "а у нас уже так" аудитор способен предложить архитектурный прыжок (замену всего pipeline, смену парадигмы), когда владелец застрял в локальных фиксах.

   **Только я (арбитр, Opus) знаю проект.** После R1 я читаю:
   > 1. `scripts/MANIFEST.json` — есть ли похожий pipeline/скрипт?
   > 2. Релевантный `KNOW_HOW_*.md` — пробовался ли этот паттерн раньше?
   > 3. `_scratchpad/ai_audits/_index.jsonl` — аудировалось ли похожее решение?
   > 4. `git log --oneline -- <релевантная папка>` — есть ли прошлые попытки?

   Далее для каждого R1-вердикта, предлагающего НОВЫЙ скрипт/инфраструктуру:
   - **Если существующее найдено** → в R2 добавить этому аудитору `discovery_note` со строгим форматом: сухие факты + инструкция "существующее не = правильное; переоцени — extend / replace / keep". Аудитор в R2 может удержать свою позицию ("Y сломано, нужно заменить"), смягчить ("твик параметров Y"), или отозваться ("Y достаточно").
   - **Если существующего нет** → R2 идёт без discovery-вмешательства.

   **discovery_note — только сухие факты, без интерпретации:**
   - ✅ `"scripts/ozon_direct_match_haiku.py: BATCH_SIZE=5, embeddings=multilingual-e5-large"`
   - ❌ `"Batching уже сделан, не надо изобретать"` (это моё мнение, не факт)

   **Hard gates — НЕ auto-REJECT, а `HARD_GATE_CONFLICT` флаг.** Если предложение нарушает hard policy (ниже), я НЕ отклоняю молча, а явно поднимаю конфликт владельцу:

   ```
   HARD_GATE_CONFLICT
     Proposal: <summary>
     Auditor strength: HIGH/MEDIUM/LOW (консенсус? code evidence?)
     Conflicts with: PROJECT_DNA §N — <rule>
     DNA rationale (кратко): <почему правило было введено>

   Decision paths for owner:
     (A) REJECT proposal — DNA стоит, возвращаемся к исходной задаче
     (B) REVISE DNA §N — изменить правило, затем применить proposal
     (C) ESCALATE — отдельная governance-задача (CRITIC/AUDITOR/JUDGE трек)
   ```

   **Зачем:** PROJECT_DNA/Iron Fence — это документы, которые владелец написал в конкретный момент времени. Они кодифицируют прошлое решение, не абсолютную истину. Если 3 независимых аудитора с code evidence предлагают принципиально лучшую архитектуру, конфликтующую с DNA — это сигнал, что DNA может быть устаревшей, а не что аудиторы неправы. Моя задача — не защищать старую схему рефлекторно, а вывести конфликт явно для владельца.

   **Hard policy список** (триггеры для `HARD_GATE_CONFLICT`):
   - `docs/PROJECT_DNA.md` §3 — frozen files (19 штук)
   - §4 — pinned API signatures
   - §5 — Tier-3 prohibitions (DML на Core, imports из `domain.reconciliation_*`, ALTER/DROP reconciliation tables)
   - Iron Fence / protected governance surface

   **Исход схемы расширяется:** теперь 5 значений — `APPROVE`, `REVISE`, `REJECT`, `NEEDS_INFO`, `HARD_GATE_CONFLICT`. Последний требует явного решения владельца A/B/C.

   Правило вытащено из двух реальных аудитов 2026-04-17:
   - `email-pipeline-registration`: CHALLENGER через `grep MANIFEST` опроверг ложный прецедент ADVOCATE.
   - `api-cost-optimization`: ни один из трёх не прочитал `ozon_direct_match_haiku.py` — выдали consensus про "local hash" и "batching", которые УЖЕ реализованы. 2 из 3 recommendation оказались невалидны (outcome: partial, см. Addendum 2026-04-18). Решение: R1 остаётся слепым (чтобы не блокировать архитектурные пивоты), discovery = мой пост-R1 гейт.

   **Сбой Gemini → абортить аудит, НЕ silent fallback.** Если `gemini_call.py` падает с 429/500-ошибкой или таймаутом — остановить процедуру, вывести владельцу: "CHALLENGER Gemini недоступен (причина), AI-Audit требует provider diversity, прерываю". Не подменять Gemini на Sonnet тихо — это уничтожает кросс-провайдерное разнообразие без ведома владельца и выдаёт false signal о консенсусе.
4. **Round 2 — дебат (параллельно, 3 новых агента):**
   Каждому агенту показываю вердикты двух других (анонимизированно: "Auditor A" / "Auditor B") и даю 1 ход:
   - ADVOCATE отвечает на возражения CHALLENGER/SECOND OPINION.
   - CHALLENGER отвечает на защиту ADVOCATE + комментарии SECOND OPINION.
   - SECOND OPINION уточняет/пересматривает свою оценку после встречных аргументов.
   Анти-конформити в промпте: **"меняй вердикт только если встретил аргумент, которого не рассматривал в R1; несогласие большинства само по себе не аргумент"**.
   **Root-cause synthesis (v0.5 обязательно):** каждый R2 агент добавляет секцию `"Do these concerns share a single root cause? If yes, name it in ≤20 words and list which concerns are symptoms."`
   Если R1 единогласный + confidence высокий → Round 2 пропустить.
4.5. **Мета-фаза 5th-concern check (v0.5):** после R2, перед арбитром — один Haiku-агент читает R1+R2 output и отвечает: "Is there one concern that subsumes two or more raised, OR one none of the auditors raised but is obvious in aggregate?" Если non-null — арбитр включает в финальное решение.
5. **Я — арбитр после дебата.** Сравниваю R1+R2+meta, собираю `unknowns_that_would_flip_verdict` ото всех (v0.5), подсвечиваю где произошёл сдвиг и почему, выдаю финальную рекомендацию: `APPROVE` / `REVISE` / `REJECT` / `NEEDS_INFO` / `HARD_GATE_CONFLICT`.
6. **Сохранить артефакт** в `_scratchpad/ai_audits/{YYYY-MM-DD}_{slug}.md` — **ОБЯЗАТЕЛЬНО с YAML front-matter** (см. "Artifact schema" ниже): bundle + R1 (3 вердикта) + R2 (3 ответа) + мой арбитраж.
7. **Не** выдавать "разрешение на действие" — всегда recommendation, решение за владельцем.

### Artifact schema (MANDATORY)

Каждый `_scratchpad/ai_audits/*.md` ДОЛЖЕН начинаться с YAML front-matter:

```yaml
---
audit_id: 2026-04-18_slug-name
date: 2026-04-18T23:23:00
duration_min: 8
models:
  advocate: claude-sonnet-4-6
  challenger: gemini-2.5-flash   # или gemini-2.5-pro при эскалации
  second_opinion: claude-haiku-4-5
gemini_real: true        # false если Gemini упал и заместился (по новой политике этого не должно быть — см. abort rule)
r2_ran: true
r2_skip_reason: null     # "unanimous_high_confidence" | null
r1:
  advocate: APPROVE/9
  challenger: REJECT/9
  second_opinion: REVISE/6
r2:
  advocate: REVISE/7
  challenger: REJECT/9
  second_opinion: REVISE/7
advocate_flipped: true
final_verdict: REVISE    # ТОЛЬКО APPROVE | REVISE | REJECT | NEEDS_INFO
cost_usd_estimate: 0.16
owner_decision: null     # заполняется владельцем постфактум: ACCEPT | OVERRIDE | DROP
outcome: null            # через N дней: confirmed | wrong | partial
---
```

**Правила схемы (не нарушать):**

- **Вердикты — 5 значений:** `APPROVE`, `REVISE`, `REJECT`, `NEEDS_INFO`, `HARD_GATE_CONFLICT`. Никаких `APPROVE_WITH_CHANGES`, `APPROVE_WITH_CAVEATS` — сплющивать в `REVISE`. `HARD_GATE_CONFLICT` использует только арбитр (я), аудиторы — нет.
- **Confidence — только integer 1-10.** Никаких `HIGH/MEDIUM/LOW`.
- **Формат вердикта в таблицах: `VERDICT/N`** (пример: `APPROVE/9`). Легко парсится.
- **`gemini_real: true` обязательно** если CHALLENGER реально ходил в Gemini API. Если был подмен — нарушение политики "abort on Gemini failure" (см. шаг 3).
- **`discovery_facts_shown: [audit_ids or file refs]`** — список моих discovery-вбросов в R2 (какому аудитору какой факт показал). Если не показывал никому — `[]`.
- **`hard_gate_triggered: null | "frozen_file" | "pinned_api" | "tier3_prohibition" | "iron_fence"`** — если я выдал REJECT из-за hard policy, не из-за вердиктов аудиторов.
- **`code_verified: true/false`** по каждому аудитору — если предложение касается существующего кода (не discovery, а проверка поведения).
- **`decision_class: D1|D2|D3|D4|D5|mixed`** (v0.5) — из bundle, авто-тегится `bundle_builder.py`. Для `mixed` bundle включает per-item breakdown.
- **`topic_type: string`** (v0.5) — авто-тегится builder'ом. Значения: `general | data_pipeline | etl | ingest | data_drift | data_loss | coverage_regression`. Используется для routing SECOND_OPINION → LINEAGE_TRACER.
- **`tier_used: 1 | 2 | 3 | 4`** (v0.5) — как глубоко эскалировали. Default 1.
- **`meta_5th_concern: string | null`** (v0.5) — результат 5th-concern мета-фазы. Null если "field covered".
- **`unknowns_that_flip_verdict: [list[str]]`** (v0.5) — объединённые unknowns ото всех аудиторов. Если пусто — арбитр не имеет права выдавать `NEEDS_INFO`.

### Forensic replay schema (v0.5.1 / Patch 8)

Deep Research выявил: "verdict recorded" ≠ "verdict replayable". Atil 2024 (arXiv:2408.04667) — даже при temperature=0 hosted API даёт swings до десятков процентов точности. Bitwise replay на hosted API infeasible; цель — **semantic replay** через golden-set anchor + полный prompt/response capture.

Дополнительные поля YAML frontmatter (additive к существующей схеме):

```yaml
schema_version: "0.6"           # bumped from 0.5 (implicit)
content_hash: sha256:...        # hash of everything below

per_agent:                      # одна запись на каждый R1/R2/meta/arbiter call
  - role: ADVOCATE | CHALLENGER | SECOND_OPINION | LINEAGE_TRACER
         | PRECEDENT_SCANNER | PREMORTEM | R2_<role> | META | ARBITER
    model:
      provider: anthropic | google
      model_id: claude-sonnet-4-5-20250929
      api_version: <provider api-version string>
      deprecation_date_known: <date | null>
    sampling: {temperature, top_p, top_k, max_tokens, seed, stop_sequences}
    prompt:
      system_hash: sha256:...
      user_hash: sha256:...
      attachments: [{sha256, mime, bytes_len, source_path}]
    context:
      retrieved_docs: [{source_url_or_path, retrieved_at, content_hash}]
      tools_available: <JSONSchema>
    invocation_log: [{step, tool, args_hash, result_hash, at, latency_ms}]
    runtime:
      region: <...>
      request_id: <provider id>
      response_id: <provider id>
      system_fingerprint: <if provider exposes>
      token_usage: {prompt, completion, cache_hit}
    output:
      raw_hash: sha256:...
      parsed: <...>

replay:
  strategy: semantic
  golden_set_id: <ref>
  tolerance: {metric: rouge_l, threshold: 0.85}
  fallback_model: claude-sonnet-5-...   # filled when snapshot deprecated

chain_of_custody:
  - {actor, action, at, signature}   # git commit signatures satisfy this
```

**Правила схемы 0.6:**
- `per_agent` обязателен, content_hash обязателен. При отсутствии — артефакт **не валиден** для post-hoc forensics и не может цитироваться при обжаловании вердикта.
- `replay.strategy: semantic` — bitwise replay на hosted API infeasible. Golden-set anchor хранится в `_scratchpad/ai_audits/_golden_set/`.
- `model.deprecation_date_known` — заполнять при каждом запуске из provider deprecation API (Anthropic `docs.claude.com/en/docs/about-claude/model-deprecations`, Google `ai.google.dev/gemini-api/docs/deprecations`).
- Raw prompts/responses хранятся в артефакте verbatim (или в отдельном `_scratchpad/ai_audits/_raw/{artifact_id}/` если >100KB).
- chain_of_custody удовлетворяется через git commits подписанные ключом owner — не требует WORM storage.

**Migration:** существующие v0.5 артефакты **не требуют перегенерации**. Новая schema 0.6 применяется к новым аудитам. Legacy артефакты остаются на schema 0.5.
- **`owner_decision` и `outcome`** оставлять `null` — владелец заполнит позже. Владелец раз в неделю открывает артефакты и проставляет:
  - `owner_decision`: `ACCEPT` (действовал по вердикту), `OVERRIDE` (сделал иначе), `DROP` (отказался от идеи)
  - `outcome` через ≥7 дней: `confirmed`, `wrong`, `partial`
- **Агрегация:** `python ai_audit/build_index.py` читает все `_scratchpad/ai_audits/*.md`, собирает YAML → `_scratchpad/ai_audits/_index.jsonl` для калибровки.

### Эскалация CHALLENGER: Gemini Flash → Gemini 2.5 Pro + extended thinking

Дефолт CHALLENGER — **gemini-2.5-flash** без thinking (быстро, копейки, free tier).

**Триггеры автоматической эскалации на Pro + thinking** (`gemini_call.py --escalate`):
- Task risk = **CORE** или **SEMI** с необратимыми последствиями (schema change, миграция данных, удаление production-данных)
- R1 показал **противоречие** (один APPROVE высокой confidence vs один REJECT высокой confidence) — Pro нужен для R2 глубже
- Владелец в bundle явно написал "решение необратимое" / "production impact" / "деньги клиентов"
- Governance-проход (batch relates to `docs/PROJECT_DNA.md` §3-5, Tier-1 files, protected governance surface)

**Когда НЕ эскалировать:**
- LOW-риск / обратимое / локальное изменение
- Мелкие промпт-правки / конфиг
- R1 единогласный high-confidence (тогда R2 вообще пропускается)

**Стоимость эскалации:** Flash → Pro+thinking добавляет ~$0.03-0.10 на CHALLENGER-вердикт (в 30-100× дороже Flash, но абсолютно — копейки). Не просить разрешение, автоматически применять по триггеру.

### Эскалация — 4-уровневая лестница (v0.5)

- **Tier 1 — Internal AI-Audit.** R1 + R2 + meta-check по процедуре выше. Default, ~$0.12-0.40, автоматически.
- **Tier 2 — External 3-chat.** Manual. Cost ~$0 (время ~2 мин). Владелец копирует bundle + R1 + R2 в Gemini-chat, ChatGPT, Claude-chat, собирает 3 вердикта, вставляет назад. Арбитр синтезирует. Триггер: auto после Tier 1 для durability claims (см. ниже) ИЛИ по просьбе владельца.
- **Tier 3 — Opus arbiter pass.** Cost ~$1.50. Перед вызовом спросить "этот случай тянет на Opus-арбитраж? +$1". Авто-триггеры:
  - После Pro-эскалации CHALLENGER R1+R2 всё равно противоречивы/поверхностны, ИЛИ
  - R2 unanimous REJECT, ИЛИ
  - ADVOCATE flipped APPROVE → REVISE/REJECT между R1 и R2, ИЛИ
  - R2 verdicts спанят APPROVE + REJECT (no middle), ИЛИ
  - `decision_class ∈ {D4, D5}` + R2 non-unanimous, ИЛИ
  - Решение особо тяжёлое (необратимая миграция + финансовое воздействие + CORE-риск).
- **Tier 4 — Claude Deep Research (claude.ai).** Highest. Cost = subscription time (минуты–часы). Триггеры:
  - Tier 3 Opus returned contradictory / still-inconclusive, ИЛИ
  - Bundle затрагивает `docs/PROJECT_DNA.md §3 (FROZEN)` / `§4 (PINNED)` / `§5 (prohibitions)`, ИЛИ
  - Явная фраза от владельца: "deep research" / "глубокое исследование".
  - Процедура: AI-Audit STOP'ается, я готовлю **Deep Research brief** (bundle + Tier 1-3 findings + specific questions to investigate) и отдаю владельцу. Владелец запускает brief в claude.ai Deep Research, паст'ит результат обратно. Я финализирую арбитраж с учётом Deep Research findings.

### External-by-default для durability claims (v0.5)

Если bundle затрагивает `§3 FROZEN` / `§4 PINNED` / `§5 prohibitions` ИЛИ использует слова "forever / irreversible / architectural invariant" — после Tier 1 **обязательно** предложить владельцу Tier 2 (external 3-chat) **до арбитража**. Не ждать inconclusive Tier 1. Cost ~$0, value — другая модель-семья + свежий контекст + большее окно на DNA-цитаты.

### Стоимость (v0.5 tiers)

| Tier | Кейс | Cost | Время |
|---|---|---|---|
| Tier 1 | LOW-risk (Flash, R1 unanimous, R2 skipped) | ~$0.05-0.08 | ~15-20s |
| Tier 1 | Дефолт (Flash R1+R2+meta) | ~$0.12-0.20 | ~30-60s |
| Tier 1 | CORE/SEMI (Pro+thinking R1+R2+meta) | ~$0.25-0.40 | ~60-120s |
| Tier 2 | External 3-chat (manual copy-paste) | ~$0 | +~2 min owner time |
| Tier 3 | + Opus arbiter pass | +~$1.50 | +~30s |
| Tier 4 | + Claude Deep Research (claude.ai) | $0 marginal (subscription) | +minutes–hours |

### Что AI-Audit НЕ делает

- Не аудирует готовый код (это делает стройка через review_runner).
- Не заменяет внешний JUDGE для CORE governance-batch (governance роли отдельно).
- Не запускается автоматически на каждом предложении — только по явному триггеру владельца.

## SESSION START (for substantive tasks)

For any non-liveness task, read `SESSION_PRIMER.md` FIRST — it contains:
- Current project status (sync with `docs/autopilot/STATE.md`)
- Active pipelines table (enrichment / export / identity / price / telegram)
- Top-5 critical KNOW_HOW rules
- Links to domain-specific `KNOW_HOW_*.md` files

Read it once per session. Skip for liveness messages per CHAT LIVENESS OVERRIDE above.

## ENRICHMENT DATA RULES (mandatory, never forget)

### Rule 1 — Read from normalized{}, not raw fields
Evidence data is in `normalized{}` block. NEVER check raw `dr_price`/`dr_image_url` to assess coverage.
- Price → `normalized.best_price`
- Photo → `normalized.best_photo_url`
- Description → `normalized.best_description`
- To assess gaps: run `python scripts/evidence_coverage_report.py` FIRST.

### Rule 2 — Phased pipeline, NEVER one mega-prompt
DR enrichment uses a phased architecture (see `scripts/MANIFEST.json` → `full_enrichment_pipeline`):
1. Phase 1: Identity Recon (Haiku) — product_type, series, designation only
2. Phase 2: Market Recon (Haiku) — unit vs pack, dangerous distributors
3. Gate A: identity must be resolved before proceeding
4. Phase 3A: Price (GPT Think) + Phase 3B: Content (Opus ext) — parallel
5. NEVER combine all into one "find everything" prompt

### Rule 3 — Filename ≠ brand
Source Excel "honeywell new.xlsx" contains mixed brands: Dell, NVIDIA, Phoenix Contact, SAIA, Weidmüller, Moxa, Xerox, Sony, etc. NEVER assume brand from filename. Brand comes from `structured_identity.confirmed_manufacturer` (set by Phase 1 recon), not from the Excel filename.

### Rule 4 — Model assignments
- Haiku: cheap recon (phases 1-2)
- GPT Think: price scouting (phase 3A)
- Opus ext: content/specs/photos (phase 3B)
- Gemini: NEVER (fabricates prices and product identities)

## SCRIPT AWARENESS (ALL pipelines, not just enrichment)

When working on ANY new pipeline task (DR, batch AI, scraping, classifier, data extraction) — **MANDATORY cross-pipeline discovery checklist**:

### Step 1: Read the registry
- `scripts/MANIFEST.json` — ALL pipelines with their scripts, triggers, I/O
- `SESSION_PRIMER.md` table — high-level pipeline status + KNOW_HOW links

### Step 2: Read relevant KNOW_HOW sub-files
Filter by pipeline:
- enrichment/catalog/DR tasks → `KNOW_HOW_enrichment.md` + `KNOW_HOW_identity.md` + `KNOW_HOW_price.md`
- email/RFQ/CRM tasks → `KNOW_HOW_email.md`
- export/InSales/Ozon → `KNOW_HOW_export.md`
- Telegram bot → `KNOW_HOW_telegram.md`

### Step 3: Check shared resources
- `downloads/knowledge/pn_brand_patterns.json` — 192 brand regexes (shared by enrichment AND email)
- `scripts/pipeline_v2/identity.py` — normalize_pn() reusable
- `scripts/dr_prompt_generator.py` — Claude/Gemini/ChatGPT prompt generators
- Existing memory: `memory/reference_cross_pipeline_index.md` (auto-loaded)

### Key cross-pipeline scripts
- DR prompts → `scripts/dr_prompt_generator.py` (Claude rich / Gemini short / ChatGPT role)
- DR results → `scripts/dr_results_import.py`
- Merge to evidence → `scripts/merge_research_to_evidence.py`
- Documents → `scripts/download_documents.py`
- Export → `scripts/export_pipeline.py`
- Photos → `scripts/deploy_photos_vps.py`
- Email IMAP fetch → `/root/email_bulk_fetcher.py` (VPS)
- Email PN index → `/root/email_pn_indexer.py` (VPS, shares pn_brand_patterns.json)

**NEVER write ad-hoc Python for tasks that existing scripts already handle.**
**NEVER invent product data — always pull from evidence files.**
**NEVER design DR prompts from scratch — reuse `scripts/dr_prompt_generator.py` templates.**
**WHEN new pipeline is created — register it in MANIFEST.json + SESSION_PRIMER.md + create KNOW_HOW_<name>.md.**
All scripts support `--dry-run` — use it first.

### Runtime semantics в MANIFEST (важно)

Скрипт в MANIFEST имеет `runtime: "local"` ИЛИ `runtime: "vps"`.
- `runtime: "local"` — запускать `python path.py` в локальном репо (поле `local_source` = полный путь)
- `runtime: "vps"` — НЕ запускать локально. Использовать `ssh {ssh_host} 'python3 {remote_path}'`. Поле `local_source` — только для деплоя (`scp local_source → remote_path`)

Не путать. Если видишь `runtime: "vps"` и `local_source: "_scratchpad/..."` — это НЕ локальный скрипт, это исходник для деплоя. Локально он не запустится (нет DB/IMAP creds).

DR batch log: `downloads/DR_BATCH_LOG.json` — read before creating/importing DR batches.

## Управление неявными знаниями (KNOW_HOW.md)

Код документирует себя сам через `git log`. Файл `KNOW_HOW.md` предназначен СТРОГО
для фиксации внешних и неявных знаний, которые невозможно вывести из исходного кода.

ТВОЯ ОБЯЗАННОСТЬ:
Если в процессе диалога, анализа данных или дебага ты обнаруживаешь новую критическую
информацию, ты должен САМОСТОЯТЕЛЬНО предложить записать её в `KNOW_HOW.md`.

ЧТО ПИШЕМ:
- `#platform` — неочевидное поведение внешних платформ (API, лимиты, переключения режимов LLM)
- `#rule` — доменные правила и специфика данных (форматы PN, суффиксы, мусор в лотах)
- `#bug` — плавающие ошибки, связанные с окружением или грязными данными
- `#data_quirk` — аномалии в данных, coverage gaps, quality patterns. Примеры:
  "evidence: expected_category wrong in 92% (344/374)",
  "evidence: weak identity 30% SKUs — worse DR results",
  "brand X: N SKUs, coverage Y%, description gap Z%"

ПРАВИЛО МАСШТАБА: числовые факты в KNOW_HOW требуют команду-источник.
Не "33+ PEHA", а `grep -c` / `wc -l` / скрипт подсчёта → точное число и процент.
Никогда не экстраполировать масштаб из одного примера.

ПОСЛЕ BATCH PROCESSING: обязательно записать хотя бы один `#data_quirk` —
coverage, quality, аномалии. Даже если "всё нормально" — зафиксировать метрики.

СТРОГО ЗАПРЕЩЕНО писать:
- Изменения в коде (добавление функций, рефакторинг, фиксы)
- Изменение конфигураций (включение флагов, настройки)
- Структуру директорий и архитектуру (это README или архитектурные доки)
- Инструкции по установке инструментов (это README)

Формат: `YYYY-MM-DD | #тег | scope: Суть и почему это важно`

KNOW_HOW ownership:
- SCOUT и BUILDER могут записать открытие с тегом `#draft`
- AUDITOR — финальный валидатор: подтверждает, дополняет или удаляет `#draft` записи
- Финальная запись (без `#draft`) появляется до закрытия задачи

## VERIFICATION REMINDER

Before changing code, define the verification path first.
Prefer baseline -> change -> re-check.
If no automated checks exist, state the validation gap explicitly.

## IDENTITY

Post-Core Freeze. Corrective execution track active:
Phase 0 loss prevention -> Phase 1 governance codification.

Read these files ONLY before CORE/SEMI code changes (NOT for enrichment/DR/export tasks):
1. `docs/PROJECT_DNA.md`
2. `docs/MASTER_PLAN_v1_9_2.md`
3. `docs/EXECUTION_ROADMAP_v2_3.md`
4. `docs/claude/MIGRATION_POLICY_v1_0.md`
5. `docs/autopilot/STATE.md`

Skip these for enrichment pipeline tasks (evidence, DR, prompts, export, photos).

Source of truth priority:
`docs/PROJECT_DNA.md` → `docs/MASTER_PLAN_v1_9_2.md` → `docs/EXECUTION_ROADMAP_v2_3.md` → `docs/claude/MIGRATION_POLICY_v1_0.md` → `docs/autopilot/STATE.md`

## DESTRUCTIVE OPS ON VPSES — mandatory wrapper

Rule (soft enforcement, owner-approved 2026-04-18):
Any SSH command touching production that matches destructive patterns MUST be wrapped via `safe_exec.sh` (deployed on both biretos.ae + dev.bireta.ru as `/root/safe_exec.sh` and symlinked `/usr/local/bin/safe`).

**Destructive patterns (non-exhaustive):**
- `rm -rf`, `rm -r /`
- `docker compose down`, `docker rm`, `docker volume rm`
- `DROP TABLE`, `DROP DATABASE`, `TRUNCATE`
- `systemctl stop mysql/mariadb`
- `mkfs`, `dd of=`, `parted`, `fdisk`
- `shutdown`, `reboot`

**Correct usage:**
```bash
ssh root@vps "/usr/local/bin/safe --confirm 'docker compose down'"
```

**What safe_exec does:**
1. Classifies by pattern — refuses without `--confirm` flag
2. Pre-change MySQL snapshot → `/root/backups/pre_change_snapshots/`
3. Telegram audit trail on every call
4. Executes command
5. Post-execute health check: curls Shopware admin, alerts on HTTP≠200

**Why soft, not hard (ForceCommand):**
- Backup is primary defense (3-2-1-1-0 with immutable B2 + GPG)
- Hard enforcement risks SSH lockout
- 90% of Claude ops are read-only — wrapping them = friction
- Discipline rule + logged audit trail is 80% of the value at 10% of the cost

**Exception:** read-only operations (`ls`, `cat`, `docker ps`, `stat`, `curl`, `grep`, `tail`) bypass the wrapper freely. When in doubt — use the wrapper.

See Phase 2 Post-Audit Report (`downloads/insales_audit/2026-04-16/PHASE_2_POST_AUDIT_REPORT.md`) for full architecture.

## CURRENT TRACK

Default execution order until the owner explicitly reopens a later track:
1. `Phase 0` — loss prevention / safety / repo integrity
2. `Phase 1` — governance codification in authoritative files
3. Only after that may `Stage 8.1` / local review fabric / runtime shadow gate continue

Presence of Stage 8.1 code in the repo does NOT authorize expanding that track.

Do not modify these files as part of corrective governance batches unless the owner
explicitly opens a separate Stage 8.1 batch:
- `auditor_system/review_runner.py`
- `auditor_system/hard_shell/approval_router.py`
- `auditor_system/hard_shell/contracts.py`

## PROTECTED GOVERNANCE SURFACE

These modules enforce execution constraints. They CANNOT be modified by
LOW or SEMI executor paths. Changes require explicit owner approval as
a separate governance batch:

- `orchestrator/acceptance_checker.py` — acceptance gates (A1-A5+)
- `orchestrator/synthesizer.py` — risk floor, gate semantics
- `orchestrator/guardian.py` — task intent / action validation
- `auditor_system/hard_shell/` — post-audit bridge, approval routing
- `orchestrator/collect_packet.py` — pytest parser, evidence collection

Reason: executor must never modify its own constraints. If executor needs
a gate change to pass — that is an escalation to owner, not a fix.

## FROZEN FILES (19) — NEVER TOUCH

See `docs/PROJECT_DNA.md` §3 for full list.
Any change = architectural violation.
If you are unsure whether a file is frozen — check §3 first.

## PINNED API — NEVER CHANGE SIGNATURES

See `docs/PROJECT_DNA.md` §4. These function signatures are immutable:

- `_derive_payment_status()`
- `_extract_order_total_minor()`
- `recompute_order_cdek_cache_atomic()`
- `update_shipment_status_atomic()`
- `_ensure_snapshot_row()`
- `InvoiceStatusRequest`
- `ShipmentTrackingStatusRequest`

You may change function bodies.
You may NOT change names, arguments, or return types.

## ABSOLUTE PROHIBITIONS

See `docs/PROJECT_DNA.md` §5 + §5b. Summary:

Tier-3 code CANNOT:
- `INSERT/UPDATE/DELETE` on `reconciliation_audit_log`, `reconciliation_alerts`, `reconciliation_suppressions`
- Raw DML on `order_ledger`, `shipments`, `payment_transactions`, `reservations`, `stock_ledger_entries`, `availability_snapshot`, `documents`
- Import from `domain.reconciliation_service`, `domain.reconciliation_alerts`, `domain.reconciliation_verify`, `domain.structural_checks`, `domain.observability_service`
- `ALTER/DROP` `reconciliation_*` tables in `migrations/020+`

## REVENUE TABLES (§5b)

- Always prefix: `rev_*` / `stg_*` / `lot_*`
- No direct `JOIN` with Core tables
- Read Core only through read-only views
- Linear FSM only, max 5 states
- No nested FSM, no branching states, no custom retry orchestrators

## NLU TABLES (Phase 7)

`nlu_pending_confirmations` and `nlu_sla_log` do NOT use `rev_*` prefix.
These are Core Backoffice infrastructure tables (AI Assistant layer),
not Revenue Tier-3 tables. They are owned by the Governance/Backoffice
domain, not by Revenue workers.

## EVERY NEW TIER-3 MODULE MUST HAVE

1. `trace_id` from payload
2. `idempotency_key` for side-effects
3. No commit inside domain operations — commit only at worker boundary
4. No logging of secrets or raw payload
5. Structured error logging: `error_class` (`TRANSIENT` / `PERMANENT` / `POLICY_VIOLATION`), `severity` (`WARNING` / `ERROR`), `retriable` (`true/false`)
6. No silent exception swallowing
7. Runnable in isolation (entry point or test with stub dependencies)
8. At least one deterministic test (no live API, no unmocked time/randomness)
9. Structured log at decision boundary: `trace_id`, key inputs, outcome
10. Webhook workers must validate signature (HMAC) BEFORE processing
11. Inbound event dedup: external `event_id` as `idempotency_key` via `INSERT ON CONFLICT DO NOTHING`

## RISK CLASSIFICATION

Before any commit, classify the change:

- 🟢 **LOW**: Tier-3 only, no Core touch → commit to feature branch
- 🟡 **SEMI**: Tier-2 body changes, new Tier-3 with financial side-effects → flag for review
- 🔴 **CORE**: Tier-1 adjacent, schema, FSM, Guardian, invariants → STOP and use Strict Mode

Do NOT change risk classification without owner approval.

## CORE STRICT MODE

For 🔴 CORE tasks, you MUST follow this exact sequence:

### Pass 1 — SCOUT + ARCHITECT only
- Analyze code
- Design architecture
- Produce plan
- Do NOT write implementation code
- End with `WAITING_FOR_OK`

### Pass 2 — PLANNER + BUILDER
- Start only after owner approves Pass 1 result
- Implement the approved plan
- Run tests
- Commit to feature branch

### After Pass 2
- Show `git diff --stat`
- Do NOT merge
- Wait for external `CRITIC`, `AUDITOR`, `JUDGE`

## MIGRATION POLICY

See `docs/claude/MIGRATION_POLICY_v1_0.md`.

Key rule:
- `LOW/SEMI` may use relaxed execution
- `CORE` must always use Strict Mode
- Workflow compression is allowed only as defined in `docs/PROJECT_DNA.md` §12 and `MIGRATION_POLICY_v1_0.md`
- `CRITIC`, `AUDITOR`, `JUDGE` remain external and separate

## R1 / PHASE A BATCH EXECUTION

For `R1` / `Phase A` / Revenue Tier-3 / `SEMI` work, default execution mode is
bounded batch execution under
`docs/policies/R1_PHASE_A_BATCH_EXECUTION_STANDARD_v1_0.md`.

- One logical change-set per batch
- One risk class per batch
- One narrow outcome per batch
- One policy surface maximum per batch
- No out-of-scope files
- No multi-agent runtime
- No substantial return without evidence pack
- If scope breaks or evidence pack is incomplete, self-reject and reopen the batch

## AUTOPILOT PROTOCOL

After completing any task:

1. Update `docs/autopilot/STATE.md` with new phase/status
2. Write `CAPSULE.md` summary
3. Append to `docs/_governance/COMPLETED_LOG.md`
4. Classify next task risk: `LOW` / `SEMI` / `CORE`
5. Do NOT merge to `master`
6. Wait for external review
7. Show final diff summary and risk classification

## OPERATIONAL PARAMETERS

### Global task timeout
Formula: `executor_timeout × (max_retries + 1) × 2`.
Default: 600 × 4 × 2 = 4800s (~80 min) for all risk levels.
After timeout → forced STOP + park in `STATE.md` with `#TIMEOUT`. Not crash, not retry.

### Budget limits
- Per-run: $0.50 soft warning (log, don't block)
- Daily: $5.00 hard stop — all tasks parked until next day
- Owner override: explicit only

### Orphan cleanup
At start of each new trace:
- Check for uncommitted files from prior cycles
- If found → log in experience, clean working directory
- If orphan doesn't belong to current trace → log + escalate, don't delete silently

### API fallback
If external API returns error or timeout:
1. One retry after 60s
2. If still failing → park task in `STATE.md` with `parked_api_outage`
3. Owner notification
4. No model substitution (Gemini CRITIC ≠ Claude CRITIC — changes governance)

### Acceptance gate A6 (test modification warning)
If executor modified test files that existed before task started → WARNING flag.
Not a block — a flag for AUDITOR to verify "test was fixed, not weakened".

## PARALLELIZATION

- Only ONE major branch active at a time
- Safety (`infra/*`) and Revenue (`feat/rev-*`) alternate in 3–5 day sprints
- `feat/rev-*` branches must NOT touch `core/`, `domain/reconciliation/`, `infra/`

## Claude Code Operational Guardrails

1. **Executor, not judge.** Claude Code may act as combined SCOUT / ARCHITECT / PLANNER / BUILDER when workflow compression is allowed. It must never act as final CRITIC, AUDITOR, or JUDGE for its own work.

2. **Owner of truth stays outside.** Core / repo governance remain source of truth. Claude Code must not present itself as owner of truth.

3. **No irreversible repo authority without explicit owner approval.** No push, no merge, no branch protection changes, no deleting branches, no rewriting history, no edits to source-of-truth governance docs unless explicitly requested.

4. **CORE work requires external review.** Strict Mode for CORE. External CRITIC / AUDITOR / JUDGE required before final approval.

5. **Evidence-first approval.** No "safe / done / approved" claim without: git diff / touched files, test evidence, CI status if applicable, relevant DNA checklist facts.

6. **One major branch at a time.** Do not open or advance parallel major tracks unless explicitly requested.

7. **Max autonomy cap for CORE.** At most 2 autonomous passes on one CORE package before stopping for external review or owner decision.

8. **Cursor role.** Cursor is treated as read-only dashboard / diff review surface during CORE sessions, not as a parallel writer.

9. **Guardrail conflicts.** If any guardrail conflicts with a direct owner instruction — stop and ask for explicit confirmation instead of assuming.

## WORKFLOW RULE

Workflow differs by risk level:

### 🟢 LOW
1. Commit → push → PR → auto-merge (`gh pr merge --auto --merge`)
2. Show PR number, diff --stat, pytest result
3. STOP. PR merges when CI passes.

### 🟡 SEMI
1. Commit → push → PR
2. Show PR number, diff --stat, pytest result
3. **WAIT for owner ACCEPT** — no auto-merge
4. After owner says "ACCEPT" → run `gh pr merge --auto --merge`

### 🔴 CORE
1. Commit → push → PR
2. Show owner the PR number: "Send this PR number to JUDGE chat for review"
3. After owner pastes "OK" → run `gh pr merge --auto --merge`
4. Owner's "OK" means external reviewers approved. Owner does not review code.

Do all steps automatically without asking (except waiting for approval on SEMI/CORE).

## MANDATORY PIPELINE FOR EVERY TASK

Every task goes through roles according to risk level.
Role templates: `docs/prompt_library/roles/`

### Pipeline by risk level

**🟢 LOW:**
`SCOUT/ARCHITECT/PLANNER/BUILDER (compressed) → AUDITOR → auto ship`
Compression allowed, but: deterministic gates mandatory, AUDITOR must be
a separate pass (not same breath as BUILDER). `can_ship` only after acceptance.

**🟡 SEMI:**
`SCOUT → ARCHITECT → external CRITIC → PLANNER → BUILDER → external AUDITOR → OWNER ACCEPT`
CRITIC and AUDITOR must be external (separate context, not self-review).
JUDGE is not required for SEMI but may be invoked by owner.

**🔴 CORE:**
`Pass 1: SCOUT + ARCHITECT → WAITING_FOR_OK → Pass 2: PLANNER + BUILDER → external CRITIC → external AUDITOR → external JUDGE → owner decision`

### Relay rule

Every role produces an artifact (Report/Verdict).
Without artifact the role is NOT considered complete.
Next role starts only after receiving the previous role's artifact.

### Task completion rule

- **LOW**: closed when AUDITOR wrote `can_ship: YES`.
- **SEMI**: closed when AUDITOR `can_ship: YES` AND owner `ACCEPT`.
- **CORE**: closed when AUDITOR `can_ship: YES` AND JUDGE `APPROVE` AND owner `ACCEPT`.

"I did everything" without AUDITOR REPORT = task is NOT closed.
Agent CANNOT report "done" before receiving `can_ship: YES`.

### Defect discovery rule

If agent finds a defect AFTER saying "done" —
that is an AUDITOR failure, not a coincidence.
Agent MUST fix the defect and re-run AUDITOR.

### Self-check before reporting

Agent CANNOT write "done" or "completed" until:
1. Tests ran (if any exist)
2. Result checked against task requirements
3. Explicitly answered: "can this be used right now — yes/no"

If there are defects — fix first, report second.

## NEVER

- Merge to `master` directly
- Modify Tier-1 files (see `docs/PROJECT_DNA.md` §3)
- `ALTER/DROP` `reconciliation_*` tables
- Import from `domain.reconciliation_*`
- DML on Core business tables from Tier-3
- Bypass Guardian for Core mutations
- Create plans, audits, or meta-documents instead of code when implementation is requested
- Skip `WAITING_FOR_OK` between Pass 1 and Pass 2 for CORE tasks
- Change risk classification of a task without owner approval
- Ignore `docs/claude/MIGRATION_POLICY_v1_0.md`
- Ignore `docs/autopilot/STATE.md`
- Give owner manual git commands (`git add`, `git commit`, `git push`) — Claude Code does this autonomously
- Use `git add -A` — only add specific files that were changed by the task
- Revert format or rules of `KNOW_HOW.md` — current format is architectural decision (PROJECT_DNA.md §9)
- Add code changes, config changes, or install instructions to `KNOW_HOW.md` — only external know-how (#platform, #rule, #bug, #data_quirk)
- Restore deleted `KNOW_HOW.md` entries or `scripts/hooks/pre-commit` — removals were deliberate
