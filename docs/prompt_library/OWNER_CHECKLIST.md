# Owner Checklist — After Receiving AUDITOR REPORT

Quick checklist. Go top-to-bottom. If any answer is NO — task goes back.

## 1. can_ship

- [ ] AUDITOR verdict is `can_ship: YES`?
- [ ] If NO — blockers list makes sense? Return to BUILDER.

## 2. CI

- [ ] CI field shows `GREEN`?
- [ ] If `RED` or `NOT_RUN` — do not accept.

## 3. Deviations

- [ ] "Отклонения от плана" — acceptable or need discussion?

## 4. Defects

- [ ] "Косяки которые найдёт владелец" — empty or acknowledged?

## 5. Manual Actions

- [ ] Any manual actions listed? If yes — are they clear enough to execute?
- [ ] Full paths provided (Windows backslash format)?

## 6. Know-How

- [ ] `know_how_captured: YES` if any anomaly was found?
- [ ] New KNOW_HOW.md entry makes sense and is factual?

## 7. Diff

- [ ] `git diff --stat` shows only expected files?
- [ ] No unrelated files leaked into the commit?

## 8. Decision

- **ACCEPT** → approve PR (or paste PR number to JUDGE for CORE tasks)
- **RETURN** → state what's wrong, task goes back to BUILDER
- **REJECT** → close PR, document reason
