# LLM Correction Pipeline v1 — Critique Log

Collecting critiques before synthesis. Per `feedback_three_critiques_then_decide`.

---

## Critique #1 (received 2026-04-17)

Overall: "textbook example of turning painful incident into robust system design."

### Answers to open questions (Q1-Q8)

- **Q1 URL Oracle:** Weighted, not authoritative. Split by domain type:
  - T0.98 for literal manufacturer domain (`honeywell.com`)
  - T0.85 for distributor/third-party (`walde.ee/esser/...`)
  - Rationale: distributors sell multiple brands; `walde.ee/esser/accessories/generic-cable` could mislead.

- **Q2 Sibling threshold:** **80%** (not 60%, not unanimity). 60% = coin flip in small families (3/5 split). Unanimity freezes on dirty legacy data. 80% = strong consensus, tolerates 1 outlier.

- **Q3 Trust Hierarchy T2 rigidity:** Context-dependent. Split T2:
  - T2a Official Datasheet (manufacturer site) = 0.90
  - T2b Third-party PDF (distributor catalog) = 0.75
  - Sonnet web search can outrank T2b but not T2a.

- **Q4 Review Bucket lifecycle:** Do not auto-expire. Triage by:
  1. Cluster size (15 SKUs, same proposed brand, same sibling series → batch)
  2. High-value SKUs (price / expected sales)
  Long tail waits for local validator (Phase E) to sweep.

- **Q5 Language awareness:** YES, explicit. Pass `context_language` field in EvidencePack. "Esser" is German brand AND German word for "eater" — anchoring prevents semantic drift.

- **Q6 Alternative-Hypothesis CoT:** YES, absolutely. Require LLM to output `rejected_brands[{brand, reason}]`. Forces CoT routing, reduces hallucination (model must evaluate sub-brand stripping etc. before answering).

- **Q7 Photo selection generalization:** Text-to-image alignment, not visual.
  - OCR on image + URL slug + metadata
  - If OCR finds "OBO" but pipeline thinks "Esser" → reject
  - Visual consistency via CLIP embeddings is a separate service (future).

- **Q8 Cost envelope Stage-2:** **Stage 2 is PYTHON-ONLY. No LLM.**
  - All rules are deterministic (JSON paths, trust tiers, URL regex, sibling math)
  - Only escalate to LLM tie-breaker for rare conflicts
  - Near-zero cost overhead vs. 2x I originally feared.

### New architectural pitfalls raised

1. **Regex Rot** — `url_brand_oracle.json` will grow fragile. `*obo*` → matches `robotics.com`.
   - Mitigation: strict unit-test suite with golden dataset of 1000 known URLs before deploy.

2. **Data Decay** — T1 `confirmed_manufacturer` may have been set incorrectly 2 years ago.
   - Mitigation: freshness decay. T1 older than 24mo → lower trust weight, allow fresh T2+T3 consensus to flag for review.

3. **Sub-brand Erasure** — LLM bias toward parent brand (Honeywell > Sperian/Notifier).
   - Mitigation: explicit "Sub-brand vs Parent" rule. If evidence contains known sub-brand, proposal MUST include it or auto-fails Stage 2.

### Open question raised back to me

> Given Phase E fine-tune goal: how do you handle human-in-the-loop annotations for review bucket so bad proposals don't accidentally become part of "ground truth" fine-tuning dataset?

(Answer in synthesis after all 3 critiques received.)

---

## Critique #2 (received 2026-04-17)

Overall: "на правильном направлении, с правильной диагностикой, но с неправильным масштабом." Не отклонять, но **сжать**. 2-3 недели работы там, где 80% ценности за 2-3 дня.

### Что сделано хорошо (consensus with #1)
- Root-cause §1.2 образцовый, трогать не надо.
- P1 + P2 + P6 правильное архитектурное направление.
- Walkthrough в Appendix показывает дизайн ловит конкретный кейс.

### Критические замечания (новые, не дублирующие #1)

1. **80% риска закрывается одним guard.** Все 19 неправильных правок были на SKU с `structured_identity.confirmed_manufacturer` заполненным + `identity_confirmed=true`. Минимум: «не запускать auto-fix для таких SKU». ~20 строк, один guard. **Сначала замок на входной двери, потом вторая периметровая ограда. План размывает этот порядок.**
   - **Action:** verify numerically — сколько из 19 имели T1 populated? (нужна проверка перед синтезом).

2. **Q3 — не открытый вопрос, а дыра в фундаменте.** T2 `from_datasheet.*` извлекается Gemini из PDF. Объявлять LLM-парсер авторитетнее другого LLM-парсера по декрету — неверно. Gemini плохо парсит сканы, многостраничные таблицы, нестандартные шаблоны → отравленный якорь, который **запрещает корректировку**.
   - **Fix:** правильная иерархия:
     - T1-H — подтверждено человеком
     - T1-URL — совпадение манук. домена
     - T2 — distilled из official PDF, но с `extraction_method` флагом
     - T3 — LLM без grounding
   - Сейчас всё «датасеточное» склеено в один T2 — слишком грубо.

3. **Критерий успеха §5.1 циркулярный.** 55 SKU — выборка, на которой дизайн разрабатывался. Тест на обучающей выборке ничего не доказывает. **Нужен hold-out ≥50 SKU**, которых никто не смотрел при проектировании rules. Иначе shadow-прогон даст ложное чувство готовности.

4. **Sibling Gate bootstrap problem.** «Бренд братьев» берётся из того же поля, которое могло быть массово неверно помечено. Если серия FX\d+ вся когда-то помечена Honeywell — новое корректное «Esser» режется как выброс.
   - **Fix:** sibling-проверка смотрит **только на T0-T2 бренды братьев, игнорируя T4** (top-level `brand`). Явно записать в P4.
   - Минимум братьев — **3**, иначе на маленьких сериях правило вырождается.

5. **Confidence gate — LLM self-assessment, плохо калибровано.** Sonnet вероятно выдал "high" на "OBO Bettermann" для FX808313. Полагаться на этот сигнал = воспроизводить инцидент.
   - **Fix:** confidence должен быть **вычисленный** — функция от (число цитированных полей, их tier, совпадение с URL Oracle, совпадение с братьями). Тогда confidence — производная остальных гейтов, отдельный гейт можно убрать.

6. **Сроки занижены в 2-3 раза.**
   - Phase B «2 дня» → реально 5-7 дней (URL Oracle это **сотни** доменов ручной курации, не десятки)
   - Phase C «2 дня» → реально 4-5 дней
   - Phase D «3 дня» на 4 независимых гейта → реально **2 недели** if gladko
   - Итог: 8 дней в плане → **3-4 недели** реально.

7. **§3.8 Generalization переоценено.** Паттерн НЕ одинаково ложится:
   - **EAN** — строка, либо совпадает с datasheet либо нет. Trust Hierarchy вырождается. Нужно простое правило consistency, не гейт.
   - **Description** — свободный текст, нет majority agreement, нет URL oracle. Нужен embeddings-based подход против DR key_findings.
   - **Specs** — работает, datasheet каноничен ✓
   - **Category** — работает if есть классификатор.
   - **Photo** — паттерн не работает вообще.
   - **Fix:** явно написать в плане: **«универсальная рамка только для brand + category; для остальных полей — отдельные дизайны»**.

8. **Rollback не first-class.** `_validate_brand_changes.py` — ad-hoc. Должно быть:
   - Каждое применение → immutable append-only journal
   - `revert_correction(pn, correction_id)` API
   - Batch rollback по времени/критерию
   - 0.5 дня работы, но критически нужно — следующий инцидент будет.

9. **Система может блокировать правильные правки (36/55).** Инцидент: 19 неверных, но 36 **правильных**. Если T1 устаревшее но не мусорное, а LLM предлагает корректировку на свежее правильное — Trust Hierarchy **заблокирует** её.
   - **Fix:** механизм override T1: «если 3 независимых источника T0/T2 противоречат T1 — T1 идёт в review, не блокирует».

### Ответы на Q1-Q8 (дополняют #1, где не совпали)

- **Q1:** Hybrid. Authoritative для curated-whitelist с `last_verified`; weighted для auto-discovered. Staleness >180 дней → downgrade.
- **Q2:** 60% (НЕ 80% как в #1) + **минимум 3 брата** + считать по T0-T2, не T4.
- **Q3:** РАЗБИТЬ T2 по `extraction_method`. Добавить T-human выше всего. (Это главное противоречие с #1 который предложил T2a/T2b split.)
- **Q4:** Авто-expiry **30 дней** с daily-digest за 7 и 1 день до. Expired → в `review_bucket/archive/` для training data. (Противоречит #1 "никогда не expire".)
- **Q5:** Language как **модификатор confidence**, не gate. Отдельный гейт = перебор. (Противоречит #1 "explicit field".)
- **Q6:** Да, counterfactual reasoning (`rejected_alternatives`). **Согласие с #1.**
- **Q7:** Не натягивать рамку. Правило: «фото валидно если URL совпадает с DR-source с наибольшим весом». Остальное — в review.
- **Q8:** Stage-2 rule-only для 80% кейсов. LLM-validator **только** когда rules дают противоречие или borderline. **Согласие с #1.**

### Рекомендации: MVP 3 дня
1. **Guard:** не запускать auto-fix если T1 filled + identity_confirmed. Прогнать исторически — сколько из 19 поймало бы?
2. **`evidence_pack.py`** как единственный источник для LLM — ценно само по себе.
3. **URL Oracle минимум:** 20-30 частых доменов (`esser-by-honeywell`, `peha.de`, `obo.de`, `dkc.ru`, `phoenixcontact.com`, `weidmueller.com`).

После этого большая часть риска закрыта, дальше спокойно Trust Hierarchy/Sibling/review bucket.

### Отложить
- Generalization на description/photos — отдельный проект.
- Training Data Phase E — преждевременно.
- LLM-валидатор в Stage-2 — rule-only первая итерация.

### До подписания плана
1. Hold-out sample ≥50 SKU в §5.
2. Phase-длительности ×2.
3. Компонент `correction_journal.py` в §3.
4. Явно ограничить §3.8 до brand+category.
5. Закрыть Q3 конкретным решением.

### Противоречия между #1 и #2 (требуют решения в синтезе)
- Sibling threshold: 80% (#1) vs 60%+min3 (#2)
- Review bucket expiry: never (#1) vs 30-day with archive (#2)
- Language: explicit field (#1) vs confidence modifier (#2)
- T2 split: T2a/T2b by PDF origin (#1) vs by extraction_method (#2)
- URL Oracle authority: weighted (#1) vs hybrid whitelist+weighted (#2)

---

## Critique #3 (pending)

---

## Synthesis (after #3)

TBD.
