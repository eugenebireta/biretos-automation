# PRECEDENT_SCANNER — Adversarial priors from past audits
<!-- version: 0.5.1 | scope: AI-Audit feature only | phase: pre-R1 | model: Haiku -->

## Когда инвокается

Обязательна для **всех D3/D4/D5** аудитов. Factor factor: per Deep Research V1 (Kim 2025 arXiv:2506.07962 — 60% co-error between models), корреляция shared training data может дать false consensus на patterns которые "звучат каноничнo". Противодействие — **принудительная engagement с disconfirming priors** перед R1.

Pipeline-position: после `bundle_builder.py` enrichment, до R1. Output инжектируется в каждый R1 prompt как "historical near-misses".

## Задача

Найти 2-3 исторических near-miss / failure cases похожих на текущий proposal. Источники:
1. `_scratchpad/ai_audits/_index.jsonl` (агрегированные past audits с outcome=wrong|partial)
2. `KNOW_HOW.md` записи с #bug / #data_quirk
3. `docs/_governance/COMPLETED_LOG.md` tasks с park_reason или rollback
4. seeded failure-mode library (built over time)

## Матрица поиска (Haiku prompt template)

```
Bundle topic: <proposal summary>
Keywords: <extracted from bundle by builder>

For each of 2-3 historical artifacts/entries similar to this topic:
1. Artifact ID / KNOW_HOW line
2. What was proposed
3. What went wrong (factual, one sentence)
4. Why it looked reasonable at the time (the "sounds canonical" trap)
5. Distance-from-current: "structurally same" / "partial overlap" / "adjacent domain"

If no priors found with distance-from-current ≠ "adjacent domain": output
  {priors: [], confidence: "low-precedent-match", note: "<why>"}

Never invent artifact IDs. Cite real `_scratchpad/ai_audits/` filenames or
KNOW_HOW.md line numbers. Vibes-precedent is worse than no precedent.
```

## Output format

```yaml
precedent_scanner_report:
  priors_found: 0..3
  priors:
    - artifact_id_or_cite: "<file:line | artifact_filename>"
      summary: "<what was proposed>"
      failure_mode: "<what went wrong factually>"
      why_looked_reasonable: "<the canonical-sounding trap>"
      distance: "structurally_same" | "partial_overlap" | "adjacent_domain"
  overall_note: "<1-2 sentence synthesis for R1 agents>"
  injection_directive: |
    For each prior above, each R1 agent MUST state in their R1 output either:
    (a) "current proposal structurally different because <file:line>", OR
    (b) "current proposal inherits this risk, mitigated by <mechanism>".
    A verdict that does not address each listed prior is INVALID.
```

## Cost

Single Haiku call ~$0.01-0.03 (bundle + priors summary context). Amortized across R1 for D3+ audits.

## Запреты

- Не генерировать priors "в стиле" без реальных артефактов.
- Не растягивать adjacent-domain случаи до structurally_same.
- Если priors не найдены — честно `priors: []`, не изобретать filler.

## Литература

- Kim Garg Peng Garg 2025, *Correlated Errors in LLMs*, ICLR, arXiv:2506.07962 — 60% co-error rate empirical.
- NRC PRA initiating-event enumeration discipline (NUREG-2122) — institutional precedent.
- ARP4761 Functional Hazard Assessment — aerospace analogue.
