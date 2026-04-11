# Identity Guard Hardening v1 — Implementation Report

**Date**: 2026-04-10
**Risk**: SEMI
**Batch**: Identity Guard Hardening v1 (7 blocks)
**Branch**: feat/rev-r1-catalog

---

## A. P0 Holes Closed

### P0-1: Brand Guard Dead Code

**Before**: `brand_mismatch` in `confidence.py` was always `False`. No caller ever computed or passed a real brand mismatch signal. The 0.20 multiplier penalty existed but was unreachable — a dead code path masking a hard architectural hole.

**After**: `identity_gate.evaluate_brand_match()` performs deterministic brand evaluation:
- Exact string match → `confirmed`
- Same canonical ecosystem (e.g. PEHA under Honeywell) → `ecosystem_match`
- Different brands → `mismatch` → hard BLOCK

Ecosystem detection uses both `_KNOWN_ECOSYSTEMS` dict and `brand_knowledge.py` YAML configs (sub_brands + aliases). Symmetric: PEHA→Honeywell = Honeywell→PEHA.

### P0-2: Specs Before Identity

**Before**: `parse_product_page()` extracted specs from fetched pages before any identity resolution. Wrong-brand pages had their specs blindly accepted.

**After**: `merge_research_to_evidence.py` gates specs acceptance through `id_gate.allows_specs`:
- `pass` → specs accepted normally
- `review` → specs accepted with `specs_status: "unvalidated"` flag
- `block` → specs stored as `specs_raw_unvalidated` with `specs_status: "blocked_identity_unresolved"`

---

## B. New Module: `scripts/identity_gate.py`

Pure-function module (~330 lines). No I/O, no API calls, no side effects.

### Components

| Function | Input | Output | Purpose |
|---|---|---|---|
| `evaluate_brand_match()` | expected_brand, found_brand, expected_subbrand | (status, reason_codes) | Brand identity: confirmed/ecosystem_match/mismatch/unknown |
| `evaluate_pn_match()` | identity_confirmed, pn_match_location, pn_confidence | (status, reason_codes) | PN strength: exact/ambiguous/unknown |
| `evaluate_category_match()` | expected_category, found_category, product_category | (status, reason_codes) | Category consistency: consistent/inconsistent/unknown |
| `evaluate_identity_gate()` | all above combined | `IdentityGateResult` | Composite gate: pass/review/block |
| `_brands_in_same_ecosystem()` | brand_a, brand_b | bool | Ecosystem membership check |

### `IdentityGateResult` Dataclass

```python
gate_result: str       # "pass" | "review" | "block"
brand_match_status: str  # "confirmed" | "ecosystem_match" | "mismatch" | "unknown"
pn_match_status: str     # "exact" | "ambiguous" | "unknown"
category_match_status: str  # "consistent" | "inconsistent" | "unknown"
identity_resolved: bool
reason_codes: list[str]

# Properties
allows_price: bool   # True only on "pass"
allows_specs: bool   # True on "pass" or "review"
is_blocked: bool     # True only on "block"
```

### Gate Decision Matrix

| Brand Status | PN Status | → Gate Result |
|---|---|---|
| confirmed/ecosystem | exact | **pass** |
| confirmed/ecosystem | ambiguous | **review** |
| unknown | exact | **review** |
| mismatch | any | **block** |
| unknown | unknown/ambiguous | **block** |

Category inconsistency adds `category_advisory_conflict` reason code but does NOT block (expected_category is 92% wrong in catalog).

---

## C. Integration: `merge_research_to_evidence.py`

5 changes to `merge_one()`:

1. **Import** (line 53): Graceful `try/except` with `_HAS_IDENTITY_GATE` flag — backward compatible if module missing.

2. **Gate evaluation** (after `identity_confirmed` check): Calls `evaluate_identity_gate()` with expected_brand, found_brand, expected_subbrand, category signals, and identity_confirmed. Result stored in `evidence["identity_gate"]` dict.

3. **Hard block on mismatch**: If `id_gate.is_blocked`, returns `"identity_blocked"` action with negative evidence audit trail. No price, no specs, no data accepted.

4. **Specs gating**: `id_gate.allows_specs` controls spec acceptance. Blocked specs stored as `dr["specs_raw_unvalidated"]` with status flag.

5. **Price brand guard**: `id_gate.allows_price` controls price acceptance. Blocked price stored in `evidence["dr_price_blocked"]` with `IDENTITY_GATE_PRICE_BLOCK` flag.

6. **Expected category advisory**: Detects conflict between expected_category and resolved category, stores `expected_category_status: "advisory_conflict"` with explanatory note.

---

## D. Expected Category Hardening

**Design decision**: expected_category is treated as **advisory hint**, not truth.

- 92% of expected_category values in the xlsx catalog are wrong (344/374 — see KNOW_HOW.md)
- Category conflicts between expected and resolved are logged but do NOT block
- `product_category` (normalized from DR/page data) takes priority over `found_category`
- Only `found_category` or `product_category` absence results in `"unknown"` status

---

## E. Ecosystem Logic

Honeywell ecosystem includes: PEHA, Esser, Notifier, Saia, Elster, Honeywell Analytics, Honeywell Home, Honeywell Process Solutions.

Two-layer lookup:
1. `_KNOWN_ECOSYSTEMS` hardcoded dict (fast path)
2. `brand_knowledge.load_brand_config()` YAML lookup (sub_brands + aliases)

This prevents false-positive brand mismatch blocks on legitimate sub-brand products (e.g., PEHA 00020211 found on PEHA.de for a Honeywell-expected SKU).

---

## F. Backward Compatibility

- `_HAS_IDENTITY_GATE` flag: if `identity_gate.py` import fails, merge proceeds with existing logic (no gate enforcement)
- No existing function signatures changed
- No existing fields removed from evidence
- New fields added: `identity_gate`, `specs_raw_unvalidated`, `specs_status`, `dr_price_blocked`, `expected_category_status`, `expected_category_conflict`

---

## G. Test Coverage

**File**: `tests/enrichment/test_identity_gate_deterministic.py`
**Tests**: 42 (all passing)

| Test Class | Count | Covers |
|---|---|---|
| `TestBrandMatch` | 10 | Exact, case-insensitive, subbrand, ecosystem (PEHA/Esser/Notifier), mismatch, unknown |
| `TestPnMatch` | 9 | identity_confirmed True/False, structured locations, body, confidence thresholds |
| `TestCategoryMatch` | 7 | Exact, substring, conflict, no-data, unreliable-only, product_category priority |
| `TestFullGate` | 8 | All pass/review/block combinations from decision matrix |
| `TestGateProperties` | 3 | allows_price/allows_specs/is_blocked for each gate state |
| `TestRegressionP0` | 5 | P0-1 brand mismatch no longer dead, P0-2 specs blocked, ecosystem symmetry |

---

## H. Files Changed

| File | Change |
|---|---|
| `scripts/identity_gate.py` | **NEW** — deterministic identity gate module |
| `scripts/merge_research_to_evidence.py` | 5 integration points for gate enforcement |
| `tests/enrichment/test_identity_gate_deterministic.py` | **NEW** — 42 unit tests |

---

## I. Remaining Work / Known Gaps

1. **Live pipeline `run()` path**: `photo_pipeline.py`'s `parse_product_page()` still extracts specs before identity. The gate in `merge_research_to_evidence.py` catches DR-path specs, but live-pipeline specs extraction is ungated. Fix requires refactoring `parse_product_page()` flow (CORE-level change).

2. **`confidence.py` brand_mismatch**: The dead `brand_mismatch` parameter still exists in `confidence.py`. It is now superseded by `identity_gate.py` but not removed. Safe to leave — callers still pass `False`, and `identity_gate` handles the real logic upstream.

3. **`deterministic_false_positive_controls.py`**: Still receives `brand_mismatch=False` from callers. Now redundant for brand checking since identity gate blocks upstream, but the dead parameter remains.

4. **Category resolver integration**: `category_resolver.py` has its own conflict detection logic. Currently identity_gate does a simpler check. Future: wire `CategoryResult` from resolver into gate for richer evaluation.
