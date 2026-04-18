# Pipeline Architecture v2 — Identity-First Enrichment

> **Status:** FROZEN SPEC v1.0 (2026-04-15)
> **Owner decision:** Architecture approved after 6-round review with external critics.
> **Rule:** Any agent working on enrichment code MUST read this file first.
> **Mutation policy:** Append-only. New versions create v1.1, v1.2 etc. Never edit frozen sections.

---

## 1. Ubiquitous Language

| Term | Definition |
|---|---|
| **SKU** | One product identified by `brand + normalized_pn`. Smallest unit of catalog. |
| **Candidate** | Raw observation from any source. NOT confirmed. NOT truth. |
| **Identity Capsule** | Frozen passport of a confirmed product. Immutable after freeze. Append-only versioned. |
| **Identity Hash** | `sha256(confirmed_brand \| normalized_pn \| manufacturer_namespace)`. Does NOT include product_type, series, EAN, or version. |
| **Identity Key** | Human-readable form: `"PEHA\|109411\|PEHA"`. |
| **Bound Evidence** | Data that passed re-bind check against capsule. Carries `identity_hash`. |
| **Candidate Enrichment** | Data that FAILED re-bind check. Stored for review and learning. Never lost. |
| **Canonical Product** | Materialized projection from capsule + bound evidence. Rebuilt, never hand-edited. |
| **Platform Listing** | Platform-specific card (InSales / Ozon / WB). Generated from canonical product + platform rules. |
| **Review Bucket** | Queue for items requiring human decision. Typed by `owner_queue_type`. |
| **Trust Tier** | Source authority level: TIER 1 (manufacturer) > TIER 2 (authorized distributor) > TIER 3 (industrial distributor) > TIER 4 (organic) > TIER 5 (denylist). |
| **Re-bind Check** | Verification that evidence belongs to THIS product before recording as bound. |
| **Field Admissibility** | Per-field acceptance decision on evidence. One page may be good for photo but bad for price. |

---

## 2. Pipeline Layers

```
LAYER 0: INTAKE
    Excel -> brand + PN + seed_name + our_price
    Create trace_id per SKU

LAYER 1: CHEAP SCOUTING
    Local scripts, pn_brand_lib, trusted domains from prior runs, SERP
    Output: candidate_identity_records[] (raw observations)
    Cost: free or near-free

LAYER 2: IDENTITY RESOLUTION
    Resolver: hard rules -> negative evidence -> source independence -> score
    Input: candidate_identity_records[]
    Output: verdict (CONFIRMED / WEAK / CONFLICT / REJECTED)
    Log: identity_resolution_events (append-only)

LAYER 3: CAPSULE FREEZE
    For CONFIRMED -> create immutable identity_capsule
    For WEAK -> review_bucket (identity_review)
    For CONFLICT -> review_bucket (identity_review)
    For REJECTED -> archived

LAYER 4: GUIDED ENRICHMENT
    All research (Haiku/GPT Think/Opus ext) receives capsule, NOT raw PN
    Each result -> re_bind_check against capsule
    Bound -> bound_evidence (with identity_hash)
    Unbound -> candidate_enrichment (with rejection reason)
    Starvation check: if bound=0 and candidates>5 -> review_bucket

LAYER 5: CANONICAL BUILDER (materialized projection)
    Input: capsule + bound_evidence[]
    Output: canonical_product (rebuilt from scratch each time)
    Selection: best_* by trust_tier > confidence > freshness
    Never hand-edit. Always rebuild from evidence.

LAYER 6: LISTING TRANSFORMERS
    Input: canonical_product + platform requirements
    Output: platform_listing_drafts (insales / ozon / wb)
    Validation: platform-specific rules, readiness gate
```

### Linear Flow (no FSM branching)

```
pending -> scouting -> resolving_identity ->
  CONFIRMED -> enriching -> building_canonical -> listing_ready
  WEAK      -> review_bucket (identity_review)
  CONFLICT  -> review_bucket (identity_review)
  REJECTED  -> archived
```

---

## 3. Hard Invariants

These rules CANNOT be violated by any code in the pipeline.

1. **No evidence without identity_hash.** Bound evidence MUST carry `identity_hash` linking to a frozen capsule. Without it, data does not enter canonical product.

2. **Capsule does not mutate after freeze.** Changes create new version (v2 supersedes v1). Old evidence stays linked to its version.

3. **After CONFIRMED, pipeline does not search for product. It searches for evidence of already confirmed product.** This is the fundamental semantic boundary.

4. **AI output is not identity evidence of first class.** AI finds candidates, extracts structure, proposes aliases. But final identity proof must be source-backed (real URL on real page), not LLM text.

5. **Title/category never confirm identity alone.** They may only strengthen an existing PN+brand match. Without exact PN or equivalent strong anchor, title/category are signals only.

6. **Denylist sources contribute nothing.** No identity, no enrichment, no signals from TIER 5 sources. Hard reject.

7. **Numeric/short PNs require extra anchor.** For PNs that are purely numeric or under 6 characters: mandatory EAN, manufacturer page, or official datasheet before CONFIRMED. Max verdict without anchor: WEAK.

8. **Canonical product is a projection, not primary truth.** Truth lives in capsule + bound_evidence. Canonical is always rebuildable.

9. **Pack price must be flagged, not silently used.** If evidence contains pack signal ("10 St", "pack of 5"), store original price + pack_qty flag. Division to unit price happens in canonical builder only.

10. **Independence rule for cross-validation.** Two sources from same origin_group count as ONE confirmation, not two. Cached copies, reseller feed clones, and marketplace text duplicates are not independent.

---

## 4. Identity Resolution Rules

### Verdict Rules (hard rules first, score second)

#### CONFIRMED
ALL of:
- `pn_match` = exact or normalized_exact
- `brand_match` = exact or allowed_alias
- no `negative_evidence`
- `page_type` is product_page / datasheet / catalog_page (not category/search)
- source strength sufficient:
  - 1x TIER 1 (manufacturer) alone is enough
  - 2x TIER 2 independent sources
  - 1x TIER 2 + 1x TIER 3
  - 3x TIER 3 independent
- for numeric_strict PNs: extra anchor required (EAN / manufacturer page / datasheet)

#### WEAK
- Some conditions met but insufficient proof
- Examples: PN exact but brand not confirmed, single TIER 3 source, page ambiguity
- Candidate enrichment allowed (provisional), not truth

#### CONFLICT
- Two strong candidates with incompatible verdict roots
- Example: mouser says "PEHA switch", RS says "ABB relay" for same PN

#### REJECTED
- PN mismatch or brand mismatch
- Explicit other product on page
- Product type hard conflict
- Page is not product page
- Source extraction unreliable and unconfirmed

### Score (only for ranking within same verdict)
Score does NOT override hard rules. It ranks candidates within WEAK, selects best CONFIRMED source.

---

## 5. Re-bind Check Algorithm

```
re_bind_check(evidence, capsule):

    1. NORMALIZE
       norm_pn = normalize_pn(evidence.extracted_pn)
         - strip brand prefix if matches confirmed_brand
         - strip known suffixes (.10, -BLK, -WHT, /Dialog)
         - strip leading zeros
         - strip special chars (- / . space)
         - lowercase
       norm_brand = normalize_brand(evidence.extracted_brand)

    2. HARD VETO (instant REJECT)
       IF negative_evidence present (explicit other PN/brand)  -> REJECT
       IF page_type in capsule.forbidden_page_types            -> REJECT
       IF product_type hard conflict                           -> REJECT
       IF source_tier = denylist                               -> REJECT

    3. PN MATCH
       exact        = (norm_pn == capsule.confirmed_pn)
       alias        = (norm_pn in capsule.allowed_pn_aliases)
       normalized   = (strip_all(norm_pn) == strip_all(capsule.confirmed_pn))
       IF none match -> REJECT

    4. BRAND MATCH
       exact_brand  = (norm_brand == capsule.confirmed_brand)
       alias_brand  = (norm_brand in capsule.allowed_brand_aliases)
       IF none match AND brand present on page -> REJECT
       IF brand absent from page -> WEAK (OK if PN exact match)

    5. PACK DETECTION
       IF pack_signal in text ("pack of X", "10 St", "5er Pack")
         -> flag pack_qty, set price_admissibility = "pack_price_detected"

    6. FIELD-LEVEL ADMISSIBILITY
       price:       admit if source_tier >= capsule.min_source_tier_for_price
       photo:       admit if identity_verified (PN+brand visible or Haiku confirmed)
       description: admit if page_type = product_page or datasheet
       specs:       admit if page_type = product_page or datasheet

    7. BIND
       Record: identity_hash + capsule_version + binding_reason + field admissibility
```

---

## 6. Trust Tier Hierarchy

### Source Tiers

| Tier | Name | Examples | Can confirm identity alone? |
|---|---|---|---|
| TIER 1 | manufacturer_proof | honeywell.com, peha.de, dkc.ru | YES (one source sufficient) |
| TIER 2 | authorized_distributor | mouser.com, rs-online.com, digikey.com, conrad.de | NO (need 2 independent) |
| TIER 3 | industrial_distributor | tme.eu, automation24.com, chipdip.ru | NO (need 3 independent) |
| TIER 4 | organic_discovery | AI-found pages, random resellers | NEVER confirms identity |
| TIER 5 | denylist | aliexpress, ebay, temu, wish | REJECTED always |

### Cross-validation (identity confirmation)

| Combination | Result |
|---|---|
| 1x TIER 1 | CONFIRMED |
| 2x TIER 2 (independent) | CONFIRMED |
| 1x TIER 2 + 1x TIER 3 | CONFIRMED |
| 3x TIER 3 (independent) | CONFIRMED |
| 1x TIER 2 alone | max WEAK |
| 1x TIER 3 alone | max WEAK |
| any TIER 4 only | max WEAK |
| any TIER 5 | REJECTED |

### Domain trust matrix (per field)

Defined in `config/seed_source_trust.json`. Determines which tier is authoritative for which field type (identity, price, photo, specs, pdf).

### Independence Groups

Sources in the same origin_group count as ONE confirmation:
- manufacturer (official sites)
- distributor (each distributor = separate group)
- marketplace (all marketplace sellers = one group)
- cached_copy (mirrors, caches = same as original)
- reseller_clone (copied listings = same as original)

---

## 7. Data Schemas

### 7.1 candidate_identity_records

One per source observation. 0-20 per SKU.

```
record_id:              string (unique)
search_batch_id:        string (which search produced this)
requested_pn:           string
requested_brand_hint:   string
source_url:             string
source_domain:          string
source_tier:            enum (manufacturer_proof | authorized_distributor | industrial_distributor | organic_discovery | denylist)
page_type:              enum (product_page | datasheet | catalog_page | category_page | search_results | marketplace_offer | pdf_brochure | image_asset)
origin_group:           enum (manufacturer | distributor | marketplace | cached_copy | reseller_clone | ai_extraction)

extracted_pn:           string | null
extracted_brand:        string | null
extracted_mpn:          string | null
extracted_ean:          string | null
extracted_title:        string | null
extracted_product_type: string | null
extracted_category_path: string | null

pn_match:               enum (exact | normalized | alias | partial | mismatch | absent)
brand_match:            enum (exact | alias | ambiguous | mismatch | absent)
product_type_match:     enum (exact | compatible | unknown | conflict)
negative_evidence:      list[string] (empty if none)

identity_score:         float (0.0 - 1.0)
collected_at:           datetime
collected_by:           string (phase/script name)
```

### 7.2 identity_capsules

Frozen passport. One active per SKU. Append-only versioned.

```
identity_hash:          string (sha256 of identity_key)
identity_key:           string ("brand|pn|namespace")
version:                int (1, 2, 3...)
superseded_by:          int | null (next version number)
frozen_at:              datetime

confirmed_brand:        string
confirmed_pn:           string
normalized_pn:          string
manufacturer_namespace: string

product_type:           string | null
series:                 string | null
identity_class:         enum (normal | numeric_strict)

allowed_brand_aliases:  list[string]
allowed_pn_aliases:     list[string]
allowed_series_aliases: list[string]
ean:                    string | null

verdict:                enum (CONFIRMED)
decision_path:          list[string]

confirmed_sources:      list[object]
  - url:                string
  - domain:             string
  - tier:               string
  - page_type:          string
  - origin_group:       string
  - candidate_record_id: string

capsule_constraints:    object
  - required_anchor_for_numeric: bool
  - forbidden_page_types: list[string]
  - min_source_tier_for_price: string
  - accept_marketplace_photos: bool

packaging:              enum (single | pack)
known_pack_sizes:       list[int]
variant_key:            string | null
```

### 7.3 identity_resolution_events

Append-only log. One per resolution attempt.

```
event_id:               string
identity_key:           string
timestamp:              datetime

candidate_set:          list[string] (record_ids considered)
hard_vetoes:            list[object] (record_id + veto_reason)
independence_groups:     dict (group_name -> list[record_ids])
cross_validation_result: string
final_verdict:          enum (CONFIRMED | WEAK | CONFLICT | REJECTED)
verdict_reason:         string
capsule_version_created: int | null
reviewer_override:      object | null (manual override if any)
```

### 7.4 bound_evidence

Data that passed re-bind. Linked to capsule via identity_hash.

```
evidence_id:            string (unique)
identity_hash:          string (FK to capsule)
capsule_version:        int
field:                  enum (price | photo | description | specs | category_signal | document)

value:                  object (field-specific, see below)
value_normalized:       object (canonical units, see below)

source_url:             string
source_domain:          string
source_tier:            string
page_type:              string
origin_group:           string

binding_status:         enum (bound)
binding_reason:         string
binding_checks:         object
  - pn_match:           string
  - brand_match:        string
  - negative_evidence:  string
  - page_type_allowed:  bool

field_admissibility:    object
  - price:              enum (admitted | not_admitted | not_available)
  - photo:              enum (admitted | not_admitted | not_available)
  - description:        enum (admitted | not_admitted | not_available)
  - specs:              enum (admitted | not_admitted | not_available)

collected_at:           datetime
collected_by:           string
expires_at:             datetime | null (for prices: TTL for staleness)
```

#### value objects by field type:

```
# price
value: { amount: float, currency: string, price_type: string, pack_qty: int|null, vat_included: bool|null }
value_normalized: { unit_amount_minor: int, currency: string, vat_flag: string }

# photo
value: { url: string, local_path: string|null, identity_verified: bool, identity_verified_by: string|null }
value_normalized: { url: string, role_candidate: string, family_risk: string|null }

# description
value: { text: string, lang: string, length: int }
value_normalized: { text_cleaned: string, lang: string }

# specs
value: { raw: string, parsed: dict }
value_normalized: { weight_g: int|null, length_mm: int|null, width_mm: int|null, height_mm: int|null, color_canonical: string|null, material: string|null, ip_rating: string|null }

# category_signal
value: { source_category_path: string, source_site: string }
value_normalized: { internal_category_candidate: string|null }

# document
value: { url: string, type: string, local_path: string|null }
value_normalized: null
```

### 7.5 candidate_enrichment

Failed re-bind. Never lost. Stored for review and learning.

```
candidate_id:           string
identity_hash:          string (which capsule it was checked against)
field:                  string
value:                  object
source_url:             string
source_domain:          string
source_tier:            string

rejection_reason:       string
rejection_details:      object
  - pn_match:           string
  - brand_match:        string
  - source_tier:        string
  - page_type:          string
  - negative_evidence:  list[string]

collected_at:           datetime
```

### 7.6 canonical_products

Materialized projection. ALWAYS rebuilt from capsule + bound_evidence. Never hand-edited.

```
identity_hash:          string (FK to capsule)
capsule_version:        int
built_at:               datetime
build_trigger:          string (manual | auto_after_enrichment | schedule)

identity:               object (copy from capsule for convenience)
  - brand, pn, manufacturer, product_type, series, ean

canonical:              object
  - title_ru:           string
  - title_en:           string | null

  - best_price:         float | null
  - best_price_currency: string | null
  - best_price_source:  string
  - best_price_tier:    string
  - best_price_evidence_id: string

  - best_photo_url:     string | null
  - best_photo_tier:    string
  - best_photo_evidence_id: string
  - photo_set:          list[object] (url, source, role)

  - best_description_ru: string | null
  - best_description_tier: string

  - specs:              object (merged from all bound specs evidence)
  - canonical_category: string | null
  - category_signals:   list[object]
  - documents:          list[object]
  - trusted_sources:    list[object] (domain, tier, has[])

readiness:              object
  - insales:            enum (READY | DRAFT | BLOCKED_reason)
  - ozon:               enum (READY | BLOCKED_reason)
  - wb:                 enum (READY | BLOCKED_reason)

evidence_stats:         object
  - bound_count:        int
  - candidate_count:    int
  - rejected_count:     int
```

### 7.7 platform_listing_drafts

One per platform per SKU. Generated from canonical + platform rules.

```
platform:               enum (insales | ozon | wb)
identity_hash:          string (FK to canonical)
status:                 enum (READY | BLOCKED | DRAFT)
generated_at:           datetime

requirements_snapshot:  object
  - snapshot_version:   string (e.g. "ozon_rules_2026_04")
  - required_fields:    list[string]
  - category_mapping_version: string

listing:                object (platform-specific fields)

validation_errors:      list[string]
validation_warnings:    list[string]
```

### 7.8 review_buckets

Typed queues for human decisions.

```
bucket_id:              string
identity_key:           string (brand|pn|namespace, NOT bare pn)
identity_hash:          string | null (null for pre-capsule reviews)
owner_queue_type:       enum (identity_review | evidence_review | marketplace_mapping_review | pricing_review)
bucket_type:            string (identity_conflict | identity_weak | enrichment_starvation | price_pack_ambiguity | photo_wrong_product | category_mapping_missing | missing_required_attrs)
reason:                 string
priority:               enum (high | medium | low)
candidates:             list[string] (record_ids or evidence_ids)
created_at:             datetime
resolved:               bool
resolved_at:            datetime | null
resolved_by:            string | null
resolution:             string | null
```

---

## 8. Canonical Builder Logic

### Selection: best_* per field

```
For each field (price, photo, description, specs):
    candidates = bound_evidence WHERE field = X AND admissibility = admitted
    sort by:
        1. trust_tier (TIER 1 > TIER 2 > TIER 3)
        2. confidence
        3. freshness (collected_at DESC)
        4. for price: prefer unit over pack
    best = candidates[0]
    
    For price with pack_qty:
        canonical_price = value.amount / value.pack_qty
```

### Category resolution

```
category_signals from bound_evidence
    -> weighted vote by trust_tier
    -> map to internal canonical_category
    -> then platform-specific mapping:
        canonical_category -> insales_path (from category_mapper)
        canonical_category -> ozon_category_id
        canonical_category -> wb_subject_id
```

### Readiness gates

```
InSales:  title + price + description -> READY (photo optional, weight optional)
Ozon:     title + price + description + EAN + weight + dimensions + category_id -> READY
WB:       title + price + description + barcode + weight + category_id -> READY
Missing any required field -> BLOCKED_reason
```

---

## 9. Model Assignments (from benchmarks)

| Pipeline Phase | Model | Why (benchmark 2026-04-11) |
|---|---|---|
| Phase 1+2 (Identity Recon) | Haiku | Best product ID, type designations, honest "not found", cheapest |
| Phase 3A (Price) | GPT Think | 21/30 coverage, correct pack division |
| Phase 3B (Content/Specs) | Opus ext | 10 photos, 136 URLs, best specs |
| Training URL collection | Sonnet ext | 153 URLs, maximum training value |
| Photo quality audit | Haiku (with product info) | wrong_product detection confirmed |
| Photo identity check | CLIP ViT-L/14 | sim >= 0.80 for same-product verification |
| Photo quality classification | Fine-tuned Qwen2-VL-2B | 76% exact, 86% binary (local, no API cost) |
| Gemini | NEVER | Fabricates prices, fake URLs. Permanently banned. |

---

## 10. Existing Assets to Reuse

| Asset | Location | Use in v2 |
|---|---|---|
| pn_brand_lib | scripts/pn_brand_lib.py | PN normalization, brand detection (143 patterns, 39 brands) |
| seed_source_trust.json | config/seed_source_trust.json | Trust tier definitions, domain lists, rate limits |
| identity_checker.py | scripts/identity_checker.py | Match priority logic (jsonld > h1 > title > body) |
| price_unit_judge | scripts/price_unit_judge_full_run.py | Pack/unit detection (deterministic text triggers) |
| category_resolver | scripts/category_resolver.py | Category override logic, synonym dictionary |
| spec_extractor | scripts/spec_extractor.py | 3-tier HTML spec extraction |
| photo_clip_validate | scripts/photo_clip_validate_raw.py | CLIP pairwise similarity, training pair generation |
| photo_trusted_collector | scripts/photo_trusted_collector.py | Whitelist-first photo collection |
| audit_photos_v2 | scripts/audit_photos_v2.py | Product-aware Haiku audit |
| evidence_normalize | scripts/evidence_normalize.py | Price priority chain, safe merge |
| export_ready | scripts/export_ready.py | Readiness gates, blocker detection |
| dr_prompt_generator | scripts/dr_prompt_generator.py | Family classifier, search site hints, prompt templates |
| KNOW_HOW.md | KNOW_HOW.md | Domain rules, PN grammars, pack-price traps, platform quirks |
| Trained Qwen2-VL-2B | D:\AI_MODELS\trained\qwen2vl_2b_photo_quality | Local photo quality classifier |
| CLIP training data | downloads/photo_training/ | 563 labeled photos for model improvement |
| InSales catalog | shop_data.csv (6234 products, 253 cols) | Category tree, existing products, field format reference |

---

## 11. Target Export Platforms

### InSales (first, softest requirements)
- 253 columns, key: [1]Title, [5]Description, [11]Category, [17]Images, [31]SKU, [32]EAN, [35]Price, [41]Weight
- 594 unique category paths, 337 brands
- Parameters: cols [45]-[252] including Ozon/WB/Yandex/Google category mappings
- EAN optional, weight optional, partial cards OK

### Ozon (strict)
- EAN mandatory
- Weight + dimensions mandatory
- Category ID from Ozon tree (119 unique in current catalog)
- Required attributes per category
- Photo requirements (white background, no watermarks)

### WB (strict)
- Barcode mandatory
- Weight mandatory
- Subject ID from WB tree (only 3 unique in current catalog - poorly filled)
- Required attributes per subject
- Own photo and title format rules

---

## 12. Pipeline Priority

```
Priority 1: Identity accuracy (data belongs to THIS SKU)
Priority 2: Source authority (trusted sources > organic)
Priority 3: Accumulated knowledge (KNOW_HOW, benchmarks, trained models)
Priority 4: Enrichment completeness (max data from confirmed sources)
```

**Better an empty field than data from wrong product.**

---

## 13. Task Routing (added 2026-04-17, append-only)

Before starting a task, use this table to find which pipeline OWNS the domain.
Never invent a new data flow if an existing pipeline covers it.

| Task | Orchestrator | Primary output |
|---|---|---|
| Load Excel / new SKU intake | scripts/pipeline_v2/run_full_370.py (Layer 0) | `downloads/evidence/evidence_{pn}.json` |
| Find datasheet PDF | scripts/datasheet_pipeline.py | `downloads/datasheets_v2/{pn}.pdf` + evidence |
| Extract specs from PDF | scripts/pipeline_v2/_extract_datasheets.py | evidence.datasheet.specs |
| Find product photos | scripts/photo_pipeline.py | `downloads/datasheet_photos/` |
| Resolve price per-unit | scripts/price_unit_judge_full_run.py | evidence.normalized.best_price |
| Deep research new SKU | scripts/dr_prompt_generator.py → manual Gemini → scripts/dr_results_import.py | `research_results/result_*.json` |
| Resolve identity | scripts/pipeline_v2/resolver.py (Layer 2) | identity_capsule |
| Build canonical product | scripts/pipeline_v2/builder.py (Layer 5) | `downloads/staging/pipeline_v2_output/canonical_products.json` |
| Normalize title to Russian | scripts/pipeline_v2/_normalize_title_ru.py (Layer 5.5) | `downloads/knowledge/title_ru_normalized_cache.json` |
| Match our SKU to shop_data analogue | scripts/match_sku_to_shopdata_haiku.py | `downloads/knowledge/haiku_matched_predictions.json` |
| Categorize (InSales/Ozon/WB) | scripts/build_exports_from_haiku.py | per-SKU category in unified dataset |
| Build InSales import CSV | scripts/build_insales_from_template.py | `downloads/exports/v4_insales_import.csv` |
| Build Ozon XLSX | scripts/build_exports_from_haiku.py | `downloads/exports/v3_ozon_import.xlsx` |
| Build WB XLSX | scripts/build_exports_from_haiku.py | `downloads/exports/v3_wb_import.xlsx` |
| Email → OrderDraft | orchestrator/email_order_bot.py | OrderDraft dataclass |
| Telegram alerts | orchestrator/start_telegram.py | Telegram messages |
| Lot scoring | scripts/lot_scoring/run_full_ranking_v341.py | `downloads/lots/summary.json` |

---

## 14. Inter-Pipeline Data Flow (added 2026-04-17, append-only)

Canonical flow for catalog-card generation:

```
Excel import → evidence/{pn}.json
    ↓
Datasheet Pipeline → datasheets_v2/*.pdf + evidence.datasheet
    ↓
Photo Pipeline → datasheet_photos/ + evidence.photo
    ↓
Price Pipeline → evidence.normalized.best_price
    ↓
Pipeline v2 Layer 0-5 (run_full_370.py) → canonical_products.json
    ↓ (title_ru may still be English here — CONTRACT)
Pipeline v2 Layer 5.5 (_normalize_title_ru.py) → title_ru_normalized_cache.json
    ↓
build_unified_product_dataset.py → unified_product_dataset.json
    ↓
match_sku_to_shopdata_haiku.py → haiku_matched_predictions.json
    ↓ (each SKU now has a shop_data analogue for Ozon/WB categories + attributes)
build_insales_from_template.py  → v4_insales_import.csv
build_exports_from_haiku.py     → v3_ozon_import.xlsx, v3_wb_import.xlsx
```

Data ownership (who writes where):

| Path | Writer | Read-only for |
|---|---|---|
| `downloads/evidence/*.json` | Pipeline v2 (Layer 0-4) | everyone else |
| `downloads/datasheets_v2/*.pdf` | datasheet_pipeline.py | everyone |
| `downloads/datasheet_photos/` | photo_pipeline.py | everyone |
| `downloads/staging/from_datasheet_for_categorizer.json` | datasheet-parse stage | everyone |
| `downloads/staging/pipeline_v2_output/canonical_products.json` | builder.py + _normalize_title_ru.py | everyone |
| `downloads/knowledge/title_ru_normalized_cache.json` | _normalize_title_ru.py | everyone |
| `downloads/knowledge/unified_product_dataset.json` | build_unified_product_dataset.py | everyone |
| `downloads/knowledge/haiku_matched_predictions.json` | match_sku_to_shopdata_haiku.py | everyone |
| `downloads/knowledge/sku_category_overrides.json` | manual_overrides / resolve_sku scripts | everyone |
| `downloads/marketplace_schemas/ozon/` | download_ozon_wb_schemas.py | everyone |
| `downloads/marketplace_schemas/wb/` | download_ozon_wb_schemas.py | everyone |
| `downloads/exports/*` | build_insales_from_template.py + build_exports_from_haiku.py | — |

---

## 15. Rules for AI Agents (added 2026-04-17, append-only)

Binding rules for ANY AI agent (Claude, Gemini, local model) editing this project:

1. **Read foundation first.** Before any task, open `docs/PROJECT_DNA.md` and this file. Never patch blindly.
2. **Never duplicate another pipeline's output.** If data exists — read it, don't regenerate.
3. **Never invent field names.** Check upstream pipeline output schema first (§7 Data Schemas).
4. **Append-only for this file.** New insights go as new sections (§16+). Never edit frozen sections.
5. **New data-flow? Update §13-14.** Add the task → orchestrator → output mapping.
6. **New file in `docs/`? Ask first.** Only create if existing docs genuinely don't cover the topic.
7. **Follow Priority Order (§12).** Identity accuracy over completeness. Empty field beats wrong data.
8. **Upstream contract violations are bugs, not fixes-in-place.** If canonical_products.json has non-Russian title_ru, fix `builder.py` or add a Layer (like 5.5), don't patch downstream.

---

## 16. title_ru Contract (added 2026-04-17, append-only)

**Format (catalog convention from shop_data.csv):**
```
[Тип товара Russian] [вариант] [бренд Latin] [модель] [PN]
```

**Mandatory content:**
1. Russian product type at the start (Рамка, Датчик, Клапан, Модуль, Извещатель, Кронштейн, …)
2. Brand in original Latin script (PEHA, Honeywell, ABB, Schneider, …)
3. **PN at the END of the title** — mandatory for catalog matching

**Examples (valid):**
- `Рамка 2-местная PEHA NOVA белая глянцевая 00020211`
- `Датчик температуры Honeywell D 20.572.51.70 101411`
- `Беруши Howard Leight Bilsom 304L на шнурке одноразовые 1000106`
- `Модуль управления Honeywell ADEMCO 4209U 183791`

**Validator:** `scripts/pipeline_v2/_normalize_title_ru.py::is_russian_normalized(text, pn=...)`
- Must return True for every `canonical_products[].title_ru` before downstream consumers read it.
- Enforcement point: Layer 5.5 in `run_full_370.py` after `build_canonical()`.

**Rationale:** Owner convention — catalog names include PN so humans can search catalog by PN or by description. Previous bug (2026-04-17): Layer 5.5 generated Russian titles but dropped PN. Haiku followed examples without PN → 130/370 titles missed PN. Fix: prompt examples now show PN mandatorily, validator now accepts `pn` kwarg and rejects titles missing PN fragment ≥4 chars.

---

## 17. Single-Source-of-Truth Discipline (added 2026-04-17, append-only)

Owner requirement (2026-04-17): "Мне нужен единый источник правды. Не чтобы ты там кучу данных вибрировал и потом хрен знает, где правда, где ложь."

### Two classes of files

**WRITERS (authoritative, produce canonical data):**
| Path | What | Who writes |
|---|---|---|
| `downloads/evidence/evidence_{pn}.json` | Per-SKU raw observations + normalized block | Pipeline v2 Layer 0-4 |
| `downloads/datasheets_v2/{pn}.pdf` | Original datasheet PDFs | datasheet_pipeline.py |
| `downloads/datasheet_photos/{pn}_*.{png,jpg}` | Extracted product photos | photo_pipeline.py |
| `downloads/staging/pipeline_v2_output/canonical_products.json` | Canonical product passport | builder.py (Layer 5) |
| `downloads/staging/from_datasheet_for_categorizer.json` | Datasheet parse (EAN/specs/photos) | _extract_datasheets.py |
| `downloads/knowledge/title_ru_normalized_cache.json` | Layer 5.5 Russian titles | _normalize_title_ru.py |
| `downloads/knowledge/haiku_matched_predictions.json` | SKU→shop_data matches | match_sku_to_shopdata_haiku.py |
| `downloads/knowledge/sku_category_overrides.json` | Manual category overrides | human review / manual_overrides.py |
| `shop_data.csv` | Owner-curated catalog ground truth | owner (InSales UI) |

**CONSUMERS (aggregate or derive, never the source):**
| Path | Reads from | Purpose |
|---|---|---|
| `downloads/knowledge/unified_product_dataset.json` | all Writers above | Aggregate view for exports. Read-only for downstream. |
| `downloads/exports/*.csv/xlsx` | unified_product_dataset + schemas | Final marketplace import files |

### Rules

1. **Exactly ONE writer per field.** If two scripts want to write `title_ru` — that's a bug, not a feature.
2. **Consumers never write back to Writer paths.** If consumer finds an error, fix it in the Writer.
3. **Aggregate files are disposable.** `unified_product_dataset.json` can be rebuilt anytime from Writers. It is not a source of truth for anything.
4. **Archive, never duplicate.** If a file becomes obsolete (replaced by a new approach), move it to `downloads/knowledge/_archived/` with README, don't leave both active.

### Current archive (2026-04-17)

Moved to `downloads/knowledge/_archived/` — no longer read by any script:
- `catalog_knowledge_base.json` → replaced by `unified_product_dataset.json`
- `extracted_properties_gemini.json` (v1 + v2) → replaced by `from_datasheet_for_categorizer.json`
- `knn_v2_predictions.json`, `knn_ozon_wb_predictions.json` → replaced by `haiku_matched_predictions.json`
- `sku_category_assignment.json` → replaced by `haiku_matched_predictions.json` + `sku_category_overrides.json`

---

## 18. Training Data Collection Policy (added 2026-04-17, append-only)

Owner requirement (2026-04-17): "Каждый API-call должен быть возвратной инвестицией. Деньги за токены не должны уходить в воду."

### Contract for ALL AI-calling scripts

**Every external LLM call (Haiku / Claude / Gemini / GPT) MUST write a training record to `downloads/training_data/{task}.jsonl` in real time.**

### Record schema (JSONL)

```json
{
  "pn": "00020211",
  "query_text": "Honeywell PEHA combination frames NOVA ...",
  "candidates": [...],
  "chosen_index": 14,
  "chosen": { ...authoritative answer... },
  "source_model": "claude-haiku-4-5-20251001",
  "platform": "ozon" | "wildberries" | "insales" | "shop_data",
  "task": "ozon_tree_classification" | "shop_data_nearest_neighbor" | "title_normalization" | etc.
}
```

### Rules

1. **Real-time persistence.** Open JSONL in append mode; `flush()` after each record. If the script crashes, the data paid for is preserved.
2. **Task taxonomy.** Use consistent `task` names so the training sets can be aggregated and split later.
3. **Include candidates + chosen_index** (not just final answer) — without candidates, the training pair is useless for classifier/ranker models.
4. **Keep original query text** — the exact embedding input Haiku saw. Not the raw evidence record.
5. **Never overwrite.** Training JSONL is append-only. If the task runs again on same PN, both records are kept (the newer overrides for production, but both survive in training data).

### Writers currently conforming

- `scripts/match_sku_to_shopdata_haiku.py` → `shop_data_matcher.jsonl` (retroactive extract)
- `scripts/ozon_direct_match_haiku.py` → `ozon_category_classifier_live.jsonl`
- `scripts/wb_direct_match_haiku.py` → `wb_category_classifier.jsonl`
- `scripts/pipeline_v2/_normalize_title_ru.py` → NEEDS update (currently saves only to cache, not training)

### Training targets

When a JSONL file reaches ≥500 pairs, fine-tune a local model on RTX 3090:
- Embedding-based classifier (multilingual-e5 + MLP head) — fast, 1-2 hours
- Or LoRA on Gemma-3 / Qwen2.5 — slower, 8-12 hours
- Once local model ≥85% accuracy on held-out set → switch production traffic from Haiku to local.

**Rationale:** Haiku call = $0.003-0.005. 370 SKU × 3 tasks (Ozon/WB/shop_data) = ~$4. After local model replaces Haiku: 0 per call, same quality. Break-even at ~100 new SKUs.
