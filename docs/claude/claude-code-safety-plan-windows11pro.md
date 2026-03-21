# Claude Code — Safety Architecture for Windows 11 Pro

Кратко: локальный слой безопасности на рабочей станции Windows для работы с Claude Code в этом репозитории. Детали изоляции ОС, SSH, git push и прочих политик не меняются этим документом — здесь только Tier-1 hash и механический барьер LOW vs SEMI.

---

## 1. Tier-1 freeze / Iron Fence (scope данного релиза)

### Единственный source of truth для Tier-1 hash

**Авторитетный список путей и состав Tier-1 frozen:** только [`PROJECT_DNA_v2_0.md`](../../PROJECT_DNA_v2_0.md) §3 («Tier-1 Frozen Files»). Любой hash-lock / guardrail должен опираться на этот список дословно (без локальных копий «на глаз»).

### Проверки: локально и в CI

Один и тот же **Tier-1 hash-check** (тот же список из 19 путей, та же нормализация содержимого, например CRLF-safe для Windows ↔ Linux) обязан выполняться:

- **локально** (pre-commit / эквивалентный guard на машине разработчика);
- **в CI** (без исключений: push/PR не может обходить проверку отсутствием хука на клиенте).

### Scope: что в этом плане называется Iron Fence

В рамках **данного Windows safety plan** под «Iron Fence» понимается **узко**:

- **локальный** safety-layer на Windows + **паритет в CI** для **Tier-1 hash** по списку из `PROJECT_DNA_v2_0.md` §3.

**Не входит в scope этого документа и не считается здесь «реализованным»:** project-wide **Boundary Grep** (импортные границы Tier-3 → Tier-1), **DDL Guard**, **Ruff** и прочие проверки из общего roadmap/DNA. Они остаются **отдельными обязательными защитами проекта** и должны жить в соответствующих CI/репозиторных механизмах, а не подменяться этим планом.

### Список из 19 Tier-1 frozen files (дословно из `PROJECT_DNA_v2_0.md` §3)

- `.cursor/windmill-core-v1/maintenance_sweeper.py`
- `.cursor/windmill-core-v1/retention_policy.py`
- `.cursor/windmill-core-v1/domain/reconciliation_service.py`
- `.cursor/windmill-core-v1/domain/reconciliation_verify.py`
- `.cursor/windmill-core-v1/domain/reconciliation_alerts.py`
- `.cursor/windmill-core-v1/domain/structural_checks.py`
- `.cursor/windmill-core-v1/domain/observability_service.py`
- `.cursor/windmill-core-v1/migrations/016_create_reconciliation_audit_log.sql`
- `.cursor/windmill-core-v1/migrations/017_create_reconciliation_suppressions.sql`
- `.cursor/windmill-core-v1/migrations/018_create_reconciliation_alerts.sql`
- `.cursor/windmill-core-v1/migrations/019_add_retention_indexes.sql`
- `.cursor/windmill-core-v1/docs/RETENTION_INVARIANT.md`
- `.cursor/windmill-core-v1/tests/validation/test_phase3_alert_emission.py`
- `.cursor/windmill-core-v1/tests/validation/test_phase3_cache_read_model_contract.py`
- `.cursor/windmill-core-v1/tests/validation/test_phase3_l3_structural_checks.py`
- `.cursor/windmill-core-v1/tests/validation/test_phase3_replay_verify.py`
- `.cursor/windmill-core-v1/tests/validation/test_phase3_structural_safety_contract.py`
- `.cursor/windmill-core-v1/tests/validation/test_phase25_contract_guards.py`
- `.cursor/windmill-core-v1/tests/validation/test_phase25_replay_gate.py`

---

## 2. LOW vs SEMI — механический барьер (не декларативный)

Правило **не** опирается на «честную» самометку риска в сообщении коммита. Классификация определяется **только** по набору **staged** изменений.

### LOW (узкий whitelist)

Риск **LOW** допустим **только если все** staged-файлы попадают в **whitelist документации**:

- пути под `docs/` с суффиксами **`.md`** или **`.txt`**, **кроме** `docs/_governance/**` (governance всегда вне LOW-whitelist).

Любой файл вне этого whitelist при staged-состоянии **не может** быть отнесён к LOW.

### Автоматический перевод в SEMI (консервативный триггер)

Если среди staged changes есть **хотя бы один** путь, попадающий под любое из условий ниже, изменение **автоматически классифицируется как SEMI** и **требует явного SEMI approve** до разрешения коммита:

- расширения: **`.py`**, **`.sql`**, **`.ps1`**, **`.sh`**
- каталоги: **`tests/**`**, **`scripts/**`**
- конфиги и сериализация: **`.yml`**, **`.yaml`**, **`.json`**, **`.toml`**, **`.ini`**
- секреты/окружение: **`.env`**, **`.env.*`**
- **`docs/_governance/**`**
- **`.cursor/**`**
- любые пути **вне** узкого LOW-whitelist выше (включая markdown или текст **не** под `docs/`, корневые README и т.п. — по умолчанию **auto-SEMI**)

### Блокировка коммита

Если сработал **auto-SEMI** (staged-набор не укладывается в LOW-whitelist), **коммит без подтверждённого SEMI approve блокируется** механизмом guard (тот же контур, что и остальные локальные блокировки этого плана).

---
