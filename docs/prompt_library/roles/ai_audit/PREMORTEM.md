# PREMORTEM — Pre-registered failure hypotheses
<!-- version: 0.5.1 | scope: AI-Audit feature only | phase: pre-R1 | model: Haiku -->

## Когда инвокается

Обязательна для всех **D3/D4/D5** аудитов. Самый высокий signal-to-cost среди добавлений Deep Research v0.5.1.

Pipeline-position: после `bundle_builder.py` + PRECEDENT_SCANNER, до R1. Output инжектируется в каждый R1 prompt как "pre-registered failure hypotheses".

## Задача

Представить что proposal **УЖЕ ВНЕДРЁН** и через 6 месяцев **причинил failure** уровня decision_class. Имплементация "back to the future" perspective per Mitchell/Russo/Pennington 1989 (J Behav Decis Making 2(1):25-38): этот режим производит **~30% больше конкретных причин** чем обычный risk-review.

## Haiku prompt template

```
Assume the proposal in the bundle has been deployed and six months later
has caused a <decision_class>-severity failure.

List the five most plausible specific failure mechanisms, IN PAST TENSE.

For each:
  1. Concrete failure mechanism (1-2 sentences)
  2. Which file/line would have been the proximate cause?
  3. Which mechanism would post-mortem investigators most likely have
     MISSED in a standard review? Why?
  4. Rank by (plausibility × undetectability) on 1-5 scale.

Constraints:
  - No abstractions like "insufficient testing" — name the specific
    code path or data shape.
  - Past tense: "the retry loop re-invoked the charge_card call
    after partial-success"  not  "could fail if retries happen".
  - Cite file:line when possible.
```

## Output format

```yaml
premortem_report:
  top_5_failures:
    - mechanism: "<1-2 sentences past-tense>"
      proximate_cause: "<file:line | 'unknown, would require code'>"
      most_missed_by_standard_review: bool
      why_missed: "<reason standard review misses this>"
      plausibility_x_undetectability: 1..5
  top_ranked_missed: "<the one mechanism with highest missed-by-review score>"
  injection_directive: |
    Each R1 agent MUST engage explicitly with the "top_ranked_missed"
    mechanism: either (a) "current proposal avoids this via <mechanism>
    at <file:line>", OR (b) "proposal inherits this risk, my verdict
    accounts for it by <adjustment>".
```

## Cost

Single Haiku call ~$0.01. Lowest-cost highest-signal addition in v0.5.1.

## Запреты

- "Insufficient testing" / "bad design" / "communication gap" — generic, отклоняется арбитром.
- Каждый механизм — конкретный (data path / code branch / external dep).
- Ranking должен быть неодинаковый per-mechanism; если все 5 одинаковы — Haiku халтурит, прогнать второй раз.

## Литература

- Klein 2007, *Performing a project premortem*, HBR 85(9):18-19.
- Mitchell Russo Pennington 1989, *Back to the future*, J Behav Decis Making 2(1):25-38, DOI:10.1002/bdm.3960020103.
- Kahneman 2011 ch. 24.
- Veinott Klein Wiggins 2010 — calibration shift ~2× vs pros/cons.
