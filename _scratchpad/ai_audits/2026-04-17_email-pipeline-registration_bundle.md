# AI-Audit Bundle: email_archive_pipeline registration

## Контекст

За предыдущие часы я (Claude Code) построил email-archive pipeline (скрипты на VPS: `email_bulk_fetcher.py`, `email_pn_indexer.py`, `auto_annotate_goldset.py`, `learn_from_sonnet.py`, `apply_learned.py`, `build_clients_table.py`, `rebuild_pn_demand_v4.py`, `make_xlsx_v2.py`). Я НЕ регистрировал их в существующих knowledge registries проекта, изобретая план DR с нуля вместо использования готового `scripts/dr_prompt_generator.py`.

Владелец указал на это как **системную проблему**: "кто-то уже это делал, а ты заново всё изобретаешь". Попросил сделать аудит knowledge-системы и встроить email-pipeline в неё **не ломая** существующее.

## Что я сделал (решение на аудит)

### 1. `scripts/MANIFEST.json` — добавлен блок `email_archive_pipeline`
- 8 скриптов с triggers / usage / purpose
- Секция `shared_resources` (pn_brand_patterns.json shared с enrichment)
- Секция `postgres_tables` (email_archive, email_pn_index, clients, pn_demand_v4)
- Секция `known_gaps`

### 2. `KNOW_HOW_email.md` — новый sub-file
Создан зеркально `KNOW_HOW_enrichment.md`. 20+ правил с тегами `#rule` / `#bug` / `#data_quirk`:
- Data source rules (IMAP folders, body cleaning)
- 15 classification flags (is_rfq vs is_sell_offer etc)
- Demand counting: capped 2/client/year anti-spam
- Shared pn_brand_patterns.json — additions работают в enrichment тоже
- Sonnet = ground truth
- Russian industrial brands discovered (Ц/ПЖ/МЕТРАН/ЭМИС etc)
- Known pitfalls (t.kosova тендеры, 1734-IB8 sell_offer)

### 3. `KNOW_HOW.md` master — добавлена строчка ссылки на KNOW_HOW_email.md

### 4. `SESSION_PRIMER.md` — добавлена строка в таблицу pipelines:
| email archive | email_bulk_fetcher, ... | KNOW_HOW_email.md | ACTIVE |

### 5. `CLAUDE.md` — расширена секция `SCRIPT AWARENESS`
- Было: "enrichment tasks only" — 8 строк
- Стало: "ALL pipelines" — 30+ строк, 3-step discovery checklist, указание на reference_cross_pipeline_index.md, обязанность регистрации новых pipelines в 5 местах

### 6. `memory/reference_cross_pipeline_index.md` — создан новый memory file
- Registry layer описан
- Таблица всех 7 pipelines со ссылками на MANIFEST блок + KNOW_HOW sub-file + shared resources
- Cross-pipeline reusable components (normalize_pn, DR prompt generators, AI orchestration rules)
- 5-step protocol для регистрации новых pipelines

### 7. `memory/MEMORY.md` — ссылка на новый reference добавлена в секцию 🔴 MUST-READ FIRST

## Claims требующие аудита

1. **"Ничего не сломано"**: я добавил/расширил, не удалял и не замещал
2. **"Встраивание в существующую архитектуру"**: использовал существующие паттерны (sub-file в KNOW_HOW зеркально, блок в MANIFEST аналогично, строка в SESSION_PRIMER)
3. **"Следующая сессия Claude автоматически найдёт email-pipeline"**: если будущий ИИ прочитает SESSION_PRIMER (как требует CLAUDE.md) + MANIFEST при первом упоминании скрипта — он автоматически выйдет на email pipeline
4. **"5-step registration protocol"**: для будущих pipelines обеспечит ту же дисциплину

## Возможные возражения (на которые прошу критиков посмотреть)

1. Достаточно ли только `CLAUDE.md::SCRIPT AWARENESS` + `MEMORY.md::MUST-READ`? Или нужны hard gates (скрипт-валидатор что MANIFEST.json synced с реальным кодом)?
2. Не размыл ли я scope `SCRIPT AWARENESS`? Изначально enrichment-only — возможно это было сознательно для изоляции governance.
3. Дублирование: добавил cross-pipeline index И в CLAUDE.md И в memory-файле — не конфликтует?
4. KNOW_HOW_email.md содержит ссылку на файлы в `_scratchpad/` (deployed to VPS) — это нарушение convention? Обычно скрипты переезжают в `scripts/`.
5. Формально ли правильно email_archive_pipeline добавлять в MANIFEST если его скрипты живут на VPS (`/root/`), а не в локальном `scripts/` дереве?

## Стоимость отмены

Если аудит скажет REJECT — откат простой:
- Убрать email_archive_pipeline блок из MANIFEST.json
- Удалить KNOW_HOW_email.md
- Убрать строку из SESSION_PRIMER + KNOW_HOW.md master
- Вернуть CLAUDE.md SCRIPT AWARENESS к "enrichment only"
- Удалить reference_cross_pipeline_index.md

~15 минут работы. Никакого кода/данных не изменено, только docs + registry.
