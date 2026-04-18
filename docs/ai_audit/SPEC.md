# AI-AUDIT (ad-hoc multi-LLM second opinion) — v0.5.1

> Full specification of the AI-Audit feature. Extracted from `CLAUDE.md` on 2026-04-18 to reduce per-session input-token load. `CLAUDE.md` retains only triggers, escalation summary, and link back to this file.

**Spec evolution:** v0.5 adds 10 improvements on top of earlier v0.4 — 4-tier escalation ladder (External 3-chat, Deep Research), mandatory `Read` / `Grep` for Claude agents, LINEAGE_TRACER role for data-pipeline topics, meta-check 5th-concern phase, root-cause synthesis in R2, concrete-example requirement, unknowns-that-flip section, D1-D5 risk-class in bundle, external-by-default for durability claims. Full change-list: `docs/_governance/AI_AUDIT_V05_PROPOSAL.md`.

Триггеры в реплике владельца: **любое упоминание** слов `"AI-аудит"`, `"API-аудит"`, `"ИИ-аудит"`, `"AI audit"` в любом падеже/контексте, либо фразы `"второе мнение"`, `"прогони через ИИ"`, `"проверь решение через ИИ"`, `"что скажут другие ИИ"`.

Не требуется императивная форма — достаточно, что слово "AI-аудит" прозвучало в реплике. Пример: "думаю мигрировать на X, AI-аудит бы" — это триггер, запускать.

**Исключение:** если владелец говорит про AI-аудит **в теоретическом ключе** (обсуждаем саму фичу, её настройки, цену, как она работает) — не запускать. Запускать только когда есть конкретное решение/предложение в контексте, которое можно аудировать.

Без триггера — не запускать.

## Процедура

1. **Собрать bundle через `python ai_audit/bundle_builder.py`** (v0.5): суть предложения, альтернативы, в чём сомнение. Builder авто-инжектит `relevant_docs_excerpts` (DNA / MASTER_PLAN §§ по keywords из bundle), `decision_class` (D1-D5 из MASTER_PLAN DECISION_CLASSES), `topic_type` (для routing LINEAGE_TRACER vs SECOND_OPINION). Если обязательных полей не хватает — спросить одним сообщением, не анкетой.
2. **Переспросить экономию:** если задача обратимая/мелкая ("поменять строчку", "попробовать промпт"), переспросить один раз: "это точно тянет на аудит? решение обратимое". Если подтвердил — запустить.
2.5. **Pre-R1 phases (v0.5.1 / Patches 1 + 11) — обязательно для D3/D4/D5:**
   - **PRECEDENT_SCANNER** (Haiku, ~$0.01-0.03) — инжектит 2-3 исторических near-miss cases из `_scratchpad/ai_audits/_index.jsonl` + KNOW_HOW.md (#bug/#data_quirk) + COMPLETED_LOG.md rollbacks. Прописан в `docs/prompt_library/roles/ai_audit/PRECEDENT_SCANNER.md`. Output → injection-directive, каждый R1 агент MUST address каждый prior.
   - **PREMORTEM** (Haiku, ~$0.01) — "back to the future": assume deployed, 6mo later caused failure. 5 past-tense mechanisms + most-missed-by-standard-review. Прописан в `docs/prompt_library/roles/ai_audit/PREMORTEM.md`. Top-ranked missed mechanism → инжектится в R1 bundle.
   - Для D1/D2 — эти фазы опциональны (cheap, low-risk decisions).

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

## Artifact schema (MANDATORY)

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

## Forensic replay schema (v0.5.1 / Patch 8)

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

## Outcome labeling — horizon-stratified + blinded (v0.5.1 / Patch 7)

Deep Research §6 (Chang 2022 disparate-censorship label bias + Bouwmeester 2012 PLoS Med blinded ascertainment + PROBAST Wolff 2019 DOI:10.7326/M18-1377): `outcome: confirmed | wrong | partial` заполненный через 7 дней **mis-scores REJECT/REVISE** из-за right-censoring. Label at T+7 / T+30 / T+90 stratified.

Расширенная схема (additive к 0.6):

```yaml
outcomes:
  t_plus_7:
    label: "confirmed" | "wrong" | "partial" | "pending"
    labeled_by: <principal_id>
    labeled_at: <ISO timestamp>
    blind_to_verdict: true    # labeler did NOT see verdict/confidence during labeling
    blind_rationale_if_false: "<why blind was broken — explicit required>"
    evidence: "<1-2 sentence factual justification>"
  t_plus_30:
    # same shape
  t_plus_90:
    # same shape
```

**Blinding discipline:** labeler UI (или CLI prompt) **прячет** verdict/confidence unless `blind_to_verdict=false` с rationale. Default — blind. Non-blind labeling разрешён только при explicit acknowledgment confirmation-bias risk.

**Inter-labeler check:** раз в 20 аудитов — второй labeler relabels blind. Gwet's AC1 между labelers пишется в `labeler_consistency_report.md`. Target: AC1 ≥ 0.6 пороговый; если падает — blinding дисциплина нарушена, SOP нуждается в fix.

## Tier-4 abort rules (v0.5.1 / Patch 10)

См. `docs/_governance/AI_AUDIT_TIER4_ABORT_RULES.md` — пять условий пропуска Tier 4 несмотря на trigger (single-source, binary-no-candidates, long-tail-no-RAG, legally-admissible, undefined-criteria), плюс post-hoc citation-verification sweep для D4/D5 outputs с >3 cites/1000 words.

## Snapshot-deprecation monitor (v0.5.1 / Patch 9)

`python ai_audit/snapshot_monitor.py` — weekly check против curated deprecation table. Alert когда pinned snapshot ≤90 days от retirement. Действие по alert:
1. Freeze all D4/D5 audits until golden-set regression passes on replacement.
2. Golden set = 20 past audits (10 APPROVE, 10 REJECT, stratified by decision_class) хранятся в `_scratchpad/ai_audits/_golden_set/`.
3. Semantic equivalence: ROUGE-L ≥ 0.85 на rationale + verdict match на ≥17/20 → greenlight migration.
- **`owner_decision` и `outcome`** оставлять `null` — владелец заполнит позже. Владелец раз в неделю открывает артефакты и проставляет:
  - `owner_decision`: `ACCEPT` (действовал по вердикту), `OVERRIDE` (сделал иначе), `DROP` (отказался от идеи)
  - `outcome` через ≥7 дней: `confirmed`, `wrong`, `partial`
- **Агрегация:** `python ai_audit/build_index.py` читает все `_scratchpad/ai_audits/*.md`, собирает YAML → `_scratchpad/ai_audits/_index.jsonl` для калибровки.

## Эскалация CHALLENGER: Gemini Flash → Gemini 2.5 Pro + extended thinking

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

## Эскалация — 4-уровневая лестница (v0.5)

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

## External-by-default для durability claims (v0.5)

Если bundle затрагивает `§3 FROZEN` / `§4 PINNED` / `§5 prohibitions` ИЛИ использует слова "forever / irreversible / architectural invariant" — после Tier 1 **обязательно** предложить владельцу Tier 2 (external 3-chat) **до арбитража**. Не ждать inconclusive Tier 1. Cost ~$0, value — другая модель-семья + свежий контекст + большее окно на DNA-цитаты.

## Стоимость (v0.5 tiers)

| Tier | Кейс | Cost | Время |
|---|---|---|---|
| Tier 1 | LOW-risk (Flash, R1 unanimous, R2 skipped) | ~$0.05-0.08 | ~15-20s |
| Tier 1 | Дефолт (Flash R1+R2+meta) | ~$0.12-0.20 | ~30-60s |
| Tier 1 | CORE/SEMI (Pro+thinking R1+R2+meta) | ~$0.25-0.40 | ~60-120s |
| Tier 2 | External 3-chat (manual copy-paste) | ~$0 | +~2 min owner time |
| Tier 3 | + Opus arbiter pass | +~$1.50 | +~30s |
| Tier 4 | + Claude Deep Research (claude.ai) | $0 marginal (subscription) | +minutes–hours |

## Что AI-Audit НЕ делает

- Не аудирует готовый код (это делает стройка через review_runner).
- Не заменяет внешний JUDGE для CORE governance-batch (governance роли отдельно).
- Не запускается автоматически на каждом предложении — только по явному триггеру владельца.
