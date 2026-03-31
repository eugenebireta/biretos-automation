# IDEA-SPIK - Shared Product Intelligence Kernel

> **Status:** PARKED
> **INBOX entry:** `docs/IDEA_INBOX.md` -> IDEA-20260331-020
> **Risk class:** SEMI

---

## 1. Problem / Context

R1 enrichment, marketplace categorization, pricing, quote flows, demand intelligence, and lot analysis all need overlapping product intelligence: identity, evidence, specs, price observations, images, and disposition outcomes.

Without a shared kernel, each consumer tends to re-acquire and re-normalize the same product knowledge in its own script or stage. That creates duplicated logic, inconsistent evidence handling, and repeated rework when the same product moves across different business flows.

The target principle is simple: one acquisition and normalization pass should be reusable by many downstream consumers.

## 2. Why Now

This idea is intentionally parked until two triggers are met:

- R1 enrichment is stable enough to serve as Kernel v0.
- The provider adapter seam exists, so acquisition logic is not hard-wired to one model path.

The goal is not to expand R1 scope immediately. The goal is to capture the architectural direction early, then extract reusable interfaces only after the current enrichment track is stable.

## 3. Relation to Master Plan / Roadmap / DNA

This idea aligns with already-established principles:

- The Intelligence Layer is designed as a read-only knowledge plane.
- SS-2, SS-3, and SS-4 are already separated as different intelligence types.
- Stage 10 already assumes `CanonicalProduct -> N platform-specific listings`.
- Evidence-grade enrichment is already required.
- PN-first identity is already a fixed principle.

SPIK does not replace Core and does not change channel publishing ownership. Core remains the owner of truth. SPIK is a reusable product-knowledge kernel that feeds multiple consumers while keeping channel-specific adapters separate.

## 4. Goals

- Establish the principle `one acquisition -> many consumers`.
- Reuse a single product-knowledge bundle across multiple consumer modules.
- Standardize kernel capabilities: identity, evidence, specs, category, price, image, disposition.
- Keep channel adapters outside the kernel.
- Reduce duplicated acquisition and normalization logic between R1 and later stages.

## 5. Non-Goals

- Build a giant monolith that tries to do every downstream task itself.
- Move Ozon/WB/YM/Avito/channel rules into the kernel.
- Turn Tier-3 exploration into a second Core.
- Bypass governance for price or publish decisions.
- Expand current R1 delivery scope just to "do SPIK now".

## 6. Core Entities / Concepts

### Kernel capabilities

1. **Identity normalization**: normalize brand, PN, dedupe, confidence.
2. **Evidence acquisition**: raw URLs, screenshots, snippets, image/price/datasheet candidates.
3. **Spec extraction**: structured specs, units, compatibility.
4. **Category inference**: internal category candidate with accepted/review/insufficient outcomes.
5. **Price observation**: raw price, currency, pack qty, MOQ, source role.
6. **Image intelligence**: raw image, usable/family/insufficient, cover candidate.
7. **Disposition**: unified `ACCEPTED / REVIEW_REQUIRED / INSUFFICIENT / REJECTED` pattern for all fields.

### Canonical data artifacts

#### `raw_evidence_bundle`

Raw evidence collection with fields such as `trace_id`, `product_ref`, `brand_raw`, `pn_raw`, `source_url`, `source_role`, `extracted_snippets[]`, `image_candidates[]`, `price_candidates[]`, `datasheet_candidates[]`, `captured_at`, `raw_confidence`.

#### `normalized_product_knowledge`

Canonical product knowledge with fields such as `canonical_brand`, `canonical_pn`, `normalized_title`, `family/series`, `normalized_specs[]`, `internal_category_candidate`, `image_status`, `price_observation_status`, `datasheet_status`, `evidence_refs[]`, `knowledge_version`.

#### `channel_requirements_profile`

Channel requirements with fields such as `channel_name`, `allowed_categories`, `required/optional_attributes`, `photo_rules`, `content_rules`, `compliance_rules`.

#### `channel_listing_projection`

Channel projection with fields such as `canonical_product_id`, `channel_name`, `channel_category`, `transformed_attributes`, `title/description_variant`, `selected_images`, `validation_status`, `publish_readiness`.

### Channel adapters remain separate

The kernel must not own:

- Ozon category tree and required attributes.
- WB required attributes and validation.
- YM category-specific rules.
- Avito photo constraints.
- InSales/Shopware field mapping.
- Channel-specific photo transforms.
- Channel-specific title/content limits.
- Platform-specific publish APIs.

Principle: the kernel supplies knowledge; adapters translate that knowledge for a platform.

## 7. Consumers

- **R1 Mass Catalog Pipeline**: PN normalization, evidence, image/price, review bucket.
- **Stage 10 Catalog Factory**: category mapping, attribute completion, photo adaptation, marketplace listings.
- **Stage 11 Price Intelligence**: price observations, source roles, historical store.
- **Stage 12 Quote/RFQ**: datasheet extraction, price observation, supplier evidence.
- **Stage 18 Demand Intelligence**: brand/category normalization, market observations.
- **R3 Lot Analyzer**: product normalization, valuation mapping, price/demand evidence.

## 8. Data Sources

- Supplier and manufacturer pages discovered during enrichment.
- Marketplace pages used as evidence or observation sources.
- Datasheets and product documents.
- Raw screenshots and snippets captured during evidence acquisition.
- Existing R1 enrichment traces and future provider-agnostic scout outputs.

## 9. Constraints

- Core remains the owner of truth.
- SPIK must stay read-only from the perspective of channel publication.
- Channel rules stay outside the kernel.
- Disposition and acceptance semantics must remain deterministic and governance-compatible.
- R1 should first stabilize as Kernel v0 before extraction work begins.
- Provider coupling should be reduced through the adapter seam before SPIK extraction starts.

## 10. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Kernel scope grows into a monolith | Medium | High | Keep kernel limited to reusable product knowledge and disposition primitives |
| Channel-specific rules leak into kernel contracts | Medium | High | Enforce strict boundary: kernel knowledge in, adapter transforms out |
| SPIK work disrupts current R1 delivery | Medium | High | Keep idea parked until R1 stabilization and provider seam are done |
| Consumer modules expect different evidence semantics | Medium | Medium | Standardize artifact schemas and disposition classes before broader rollout |
| Duplicate truths emerge between Core and SPIK | Low | High | Keep Core as owner of truth and SPIK as reusable intelligence layer only |

## 11. Promotion Options

- Option A: Treat stabilized R1 enrichment as Kernel v0, then extract reusable interfaces for identity, evidence, and disposition.
- Option B: Add a bounded Stage 10 integration step as the first external SPIK consumer after Kernel v0 exists.
- Option C: Create a dedicated TD for SPIK contracts, artifacts, and consumer integration sequencing.

## 12. Open Questions

- What should be the canonical ownership boundary between `CanonicalProduct` and `normalized_product_knowledge`?
- Which artifact store should hold reusable evidence bundles and knowledge versions?
- How should knowledge versioning and invalidation work for stale price/image observations?
- Which consumer should be the first real pilot after R1: Stage 10, Stage 11, or R3?
- Which parts of disposition belong inside the kernel versus consumer-specific policy gates?

## Future enhancements from reviews

- **API-First Service**: сделать SPIK независимым сервисом (`FastAPI`), а не shared library. Потребители общаются только через API.
- **Event Bus / Pub-Sub**: когда ядро обновляет knowledge, оно рассылает событие `KnowledgeUpdated`. Потребители подписываются и пересчитывают свои проекции автоматически.
- **Локальные LLM для тяжёлых задач**: `spec extraction` и `category inference` сбрасывать в локальную очередь на мощное железо (`30B/70B` модели), а не жечь облачные токены.
- **`extraction_hash` + `source_snapshot_id`**: для traceability, чтобы при изменении страницы источника можно было доказать, откуда были взяты данные.
- **`ttl_expires_at` по типам данных**: характеристики вечны, цены протухают. Ядро должно знать, когда данные устарели.
- **`validation_errors[]` в `channel_listing_projection`**: если маркетплейс отклонил карточку, ошибка блокирует повторную публикацию до исправления.
- **Разделение Knowledge и Governance**: SPIK оценивает полноту знаний, но не принимает бизнес-решение о публикации.

---

## Review Log

| Date | Reviewer | Status change | Notes |
|------|----------|---------------|-------|
| 2026-03-31 | Owner | INBOX -> PARKED | SPIK captured as a parked architectural proposal; trigger is R1 stabilization plus provider adapter seam |
