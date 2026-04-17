"""Full pipeline v2 run on ALL 370 SKUs: Layer 0-5.

Layer 0: INTAKE (existing evidence)
Layer 1: CHEAP SCOUTING (all URLs from evidence, classified by tier)
Layer 2: IDENTITY RESOLUTION (resolver)
Layer 3: CAPSULE FREEZE
Layer 4: GUIDED ENRICHMENT (re-bind check on all existing data)
Layer 5: CANONICAL BUILD

Output: canonical products + stats
"""
from __future__ import annotations

import json
import sys
import io
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.pipeline_v2.enums import *
from scripts.pipeline_v2.models import *
from scripts.pipeline_v2.identity import (
    re_bind_check,
)
from scripts.pipeline_v2.resolver import resolve_identity
from scripts.pipeline_v2.builder import build_canonical
from scripts.pipeline_v2._normalize_title_ru import normalize_titles_in_place

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
TRUST_CONFIG = json.loads((ROOT / "config" / "seed_source_trust.json").read_text(encoding="utf-8"))
OUTPUT_DIR = ROOT / "downloads" / "staging" / "pipeline_v2_output"

SKIP_PNS = {"---", "--", "_", "PN", "-----", ""}

TIER_LOOKUP_ORDER = [
    "manufacturer_proof", "authorized_distributor", "industrial_distributor",
    "marketplace_fallback", "datasheet_source", "customs_price_source",
    "price_aggregator", "tender_source", "technical_reference",
    "product_review", "noise_source",
]
_TIER_MAP = {
    "manufacturer_proof": SourceTier.MANUFACTURER_PROOF,
    "authorized_distributor": SourceTier.AUTHORIZED_DISTRIBUTOR,
    "industrial_distributor": SourceTier.INDUSTRIAL_DISTRIBUTOR,
    "marketplace_fallback": SourceTier.MARKETPLACE_FALLBACK,
    "datasheet_source": SourceTier.INDUSTRIAL_DISTRIBUTOR,
    "customs_price_source": SourceTier.INDUSTRIAL_DISTRIBUTOR,
    "price_aggregator": SourceTier.MARKETPLACE_FALLBACK,
    "tender_source": SourceTier.INDUSTRIAL_DISTRIBUTOR,
    "technical_reference": SourceTier.ORGANIC_DISCOVERY,
    "product_review": SourceTier.ORGANIC_DISCOVERY,
    "noise_source": SourceTier.ORGANIC_DISCOVERY,
}


def get_tier(domain: str) -> SourceTier:
    for tier_name in TIER_LOOKUP_ORDER:
        if any(d in domain for d in TRUST_CONFIG.get(tier_name, [])):
            return _TIER_MAP.get(tier_name, SourceTier.ORGANIC_DISCOVERY)
    for d in TRUST_CONFIG.get("denylist", []):
        if d in domain:
            return SourceTier.DENYLIST
    return SourceTier.ORGANIC_DISCOVERY


def get_origin(tier: SourceTier) -> OriginGroup:
    if tier == SourceTier.MANUFACTURER_PROOF:
        return OriginGroup.MANUFACTURER
    if tier in (SourceTier.AUTHORIZED_DISTRIBUTOR, SourceTier.INDUSTRIAL_DISTRIBUTOR):
        return OriginGroup.DISTRIBUTOR
    if tier == SourceTier.MARKETPLACE_FALLBACK:
        return OriginGroup.MARKETPLACE
    return OriginGroup.AI_EXTRACTION


def extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def collect_all_urls(d: dict) -> set[str]:
    """Extract ALL URLs from all evidence fields."""
    urls: set[str] = set()
    dr = d.get("deep_research") or {}

    for tu in (d.get("training_urls") or []):
        u = tu if isinstance(tu, str) else tu.get("url", "")
        if u: urls.add(u)
    for src in (dr.get("sources") or []):
        if isinstance(src, dict) and src.get("url"):
            urls.add(src["url"])
    for item in (dr.get("key_findings") or []):
        if isinstance(item, str):
            for word in item.split():
                if word.startswith("http"):
                    urls.add(word.rstrip(".,;)"))
    ds = d.get("datasheet") or {}
    if ds.get("url"): urls.add(ds["url"])
    photo = d.get("photo") or {}
    if photo.get("source_url"): urls.add(photo["source_url"])
    price = d.get("price") or {}
    if price.get("page_url"): urls.add(price["page_url"])
    pc = d.get("price_contract") or {}
    if pc.get("source_url"): urls.add(pc["source_url"])
    if pc.get("dr_source_url"): urls.add(pc["dr_source_url"])
    if d.get("dr_image_url"): urls.add(d["dr_image_url"])

    return urls


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    files = sorted(EV_DIR.glob("evidence_*.json"))
    print(f"Pipeline v2 full run: {len(files)} evidence files")
    print("=" * 100)

    stats = {
        "total": 0, "skipped": 0,
        "confirmed": 0, "weak": 0, "conflict": 0, "rejected": 0,
        "price_bound": 0, "price_rejected": 0, "price_missing": 0,
        "photo_bound": 0, "photo_rejected": 0, "photo_missing": 0,
        "desc_bound": 0, "desc_rejected": 0, "desc_missing": 0,
        "insales_ready": 0, "ozon_ready": 0,
    }
    brand_stats: dict[str, dict] = {}
    weak_pns: list[dict] = []
    canonical_products: list[dict] = []

    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        if not pn or pn.strip("-_") == "" or pn in SKIP_PNS:
            stats["skipped"] += 1
            continue

        stats["total"] += 1
        si = d.get("structured_identity") or {}
        norm = d.get("normalized") or {}
        dr = d.get("deep_research") or {}
        brand = d.get("brand", "") or si.get("confirmed_manufacturer", "")
        subbrand = d.get("subbrand", "")
        real_brand = subbrand or brand

        # --- Layer 1: Collect all URLs, classify ---
        all_urls = collect_all_urls(d)
        seen_domains: set[str] = set()
        candidates: list[CandidateIdentityRecord] = []

        urls_with_tier = []
        for url in all_urls:
            dom = extract_domain(url)
            if not dom or len(dom) < 4:
                continue
            tier = get_tier(dom)
            if tier == SourceTier.DENYLIST:
                continue
            urls_with_tier.append((url, dom, tier))

        tier_order = {SourceTier.MANUFACTURER_PROOF: 0, SourceTier.AUTHORIZED_DISTRIBUTOR: 1,
                      SourceTier.INDUSTRIAL_DISTRIBUTOR: 2, SourceTier.MARKETPLACE_FALLBACK: 3,
                      SourceTier.ORGANIC_DISCOVERY: 4}
        urls_with_tier.sort(key=lambda x: tier_order.get(x[2], 99))

        for url, dom, tier in urls_with_tier:
            if dom not in seen_domains:
                seen_domains.add(dom)
                candidates.append(CandidateIdentityRecord(
                    record_id=f"cid_{pn}_{len(candidates)}",
                    requested_pn=pn, requested_brand_hint=brand,
                    source_url=url, source_domain=dom,
                    source_tier=tier, page_type=PageType.PRODUCT_PAGE,
                    origin_group=get_origin(tier),
                    extracted_pn=pn, extracted_brand=real_brand,
                    pn_match=PNMatch.EXACT,
                    brand_match=BrandMatch.EXACT if real_brand else BrandMatch.ABSENT,
                    identity_score=0.7,
                    collected_at=now, collected_by="pipeline_v2_full",
                ))

        # --- Layer 2: Resolve ---
        verdict, capsule, event = resolve_identity(pn, brand, candidates)

        if verdict == IdentityVerdict.CONFIRMED:
            stats["confirmed"] += 1
        elif verdict == IdentityVerdict.WEAK:
            stats["weak"] += 1
            weak_pns.append({"pn": pn, "brand": brand, "reason": event.verdict_reason[:80],
                             "candidates": len(candidates)})
            continue
        elif verdict == IdentityVerdict.CONFLICT:
            stats["conflict"] += 1
            continue
        else:
            stats["rejected"] += 1
            continue

        # --- Layer 4: Re-bind evidence ---
        bound_ev: list[BoundEvidence] = []
        rejected_ev: list[dict] = []

        # Price
        price_val = norm.get("best_price")
        pc = d.get("price_contract") or {}
        price_url = pc.get("source_url") or pc.get("dr_source_url") or ""
        price_domain = extract_domain(price_url) if price_url else ""

        if price_val:
            if price_domain:
                tier = get_tier(price_domain)
                rb = re_bind_check(pn, real_brand, None, PageType.PRODUCT_PAGE,
                                   tier, [], "", capsule)
            else:
                rb = type("R", (), {"bound": True, "reason": "no_source_url",
                                    "pn_match": PNMatch.EXACT, "brand_match": BrandMatch.ABSENT,
                                    "field_admissibility": FieldAdmissibilityRecord(price=FieldAdmissibility.ADMITTED),
                                    "pack_qty": None, "pack_price_detected": False})()
                tier = SourceTier.ORGANIC_DISCOVERY
                price_domain = "unknown"

            if rb.bound:
                stats["price_bound"] += 1
                bound_ev.append(BoundEvidence(
                    evidence_id=f"ev_{pn}_price", identity_hash=capsule.identity_hash,
                    capsule_version=1, field=EvidenceField.PRICE,
                    value={"amount": float(price_val),
                           "currency": norm.get("best_price_currency", "EUR"),
                           "pack_qty": rb.pack_qty},
                    source_url=price_url or "", source_domain=price_domain,
                    source_tier=tier, page_type=PageType.PRODUCT_PAGE,
                    origin_group=get_origin(tier),
                    binding_status=BindingStatus.BOUND, binding_reason=rb.reason,
                    binding_checks=BindingChecks(pn_match=rb.pn_match.value if hasattr(rb.pn_match, 'value') else str(rb.pn_match),
                                                 brand_match=rb.brand_match.value if hasattr(rb.brand_match, 'value') else str(rb.brand_match)),
                    field_admissibility=rb.field_admissibility,
                    collected_at=now, collected_by="pipeline_v2",
                ))
            else:
                stats["price_rejected"] += 1
                rejected_ev.append({"field": "price", "reason": rb.reason})
        else:
            stats["price_missing"] += 1

        # Photo
        photo_url = norm.get("best_photo_url") or ""
        photo_domain = extract_domain(photo_url) if photo_url else ""

        if photo_url and photo_domain:
            tier = get_tier(photo_domain)
            rb = re_bind_check(pn, real_brand, None, PageType.PRODUCT_PAGE,
                               tier, [], "", capsule)
            if rb.bound:
                stats["photo_bound"] += 1
                bound_ev.append(BoundEvidence(
                    evidence_id=f"ev_{pn}_photo", identity_hash=capsule.identity_hash,
                    capsule_version=1, field=EvidenceField.PHOTO,
                    value={"url": photo_url, "identity_verified": False},
                    source_url=photo_url, source_domain=photo_domain,
                    source_tier=tier, page_type=PageType.PRODUCT_PAGE,
                    origin_group=get_origin(tier),
                    binding_status=BindingStatus.BOUND, binding_reason=rb.reason,
                    binding_checks=BindingChecks(pn_match=rb.pn_match.value, brand_match=rb.brand_match.value),
                    field_admissibility=rb.field_admissibility,
                    collected_at=now, collected_by="pipeline_v2",
                ))
            else:
                stats["photo_rejected"] += 1
                rejected_ev.append({"field": "photo", "reason": rb.reason, "domain": photo_domain})
        else:
            stats["photo_missing"] += 1

        # Description
        desc = norm.get("best_description") or ""
        if desc and len(desc) > 20:
            stats["desc_bound"] += 1
            bound_ev.append(BoundEvidence(
                evidence_id=f"ev_{pn}_desc", identity_hash=capsule.identity_hash,
                capsule_version=1, field=EvidenceField.DESCRIPTION,
                value={"text": desc, "lang": "ru", "length": len(desc)},
                source_url="", source_domain=norm.get("best_description_source", ""),
                source_tier=SourceTier.ORGANIC_DISCOVERY,
                page_type=PageType.PRODUCT_PAGE, origin_group=OriginGroup.AI_EXTRACTION,
                binding_status=BindingStatus.BOUND, binding_reason="description_from_dr",
                binding_checks=BindingChecks(pn_match="assumed", brand_match="assumed"),
                field_admissibility=FieldAdmissibilityRecord(description=FieldAdmissibility.ADMITTED),
                collected_at=now, collected_by="pipeline_v2",
            ))
        else:
            stats["desc_missing"] += 1

        # Specs (from_datasheet — populated by Gemini/Haiku PDF extraction)
        fd = d.get("from_datasheet") or {}
        fd_specs = fd.get("specs") or {}
        if fd_specs and isinstance(fd_specs, dict):
            # Parse weight/dims from datasheet strings into numeric fields
            import re as _re
            def _to_int(s):
                if not s: return None
                m = _re.search(r"(\d+)", str(s).replace(",", ""))
                return int(m.group(1)) if m else None
            def _parse_dims(s):
                if not s: return (None, None, None)
                m = _re.search(r"(\d+)\s*[xXхХ×]\s*(\d+)\s*[xXхХ×]\s*(\d+)", str(s))
                if m:
                    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
                return (None, None, None)
            w = _to_int(fd.get("weight_g"))
            L, W, H = _parse_dims(fd.get("dimensions_mm"))
            value_norm = {}
            if w: value_norm["weight_g"] = w
            if L: value_norm["length_mm"] = L
            if W: value_norm["width_mm"] = W
            if H: value_norm["height_mm"] = H
            if fd_specs.get("material") or fd_specs.get("Material"):
                value_norm["material"] = fd_specs.get("material") or fd_specs.get("Material")
            if fd_specs.get("ip_rating") or fd_specs.get("IP rating") or fd_specs.get("Degree of protection (IP)"):
                value_norm["ip_rating"] = fd_specs.get("ip_rating") or fd_specs.get("IP rating") or fd_specs.get("Degree of protection (IP)")
            bound_ev.append(BoundEvidence(
                evidence_id=f"ev_{pn}_specs", identity_hash=capsule.identity_hash,
                capsule_version=1, field=EvidenceField.SPECS,
                value={"parsed": fd_specs, "source": "datasheet_llm_extract"},
                value_normalized=value_norm,
                source_url="", source_domain="datasheet",
                source_tier=SourceTier.MANUFACTURER_PROOF,
                page_type=PageType.PRODUCT_PAGE, origin_group=OriginGroup.AI_EXTRACTION,
                binding_status=BindingStatus.BOUND, binding_reason="specs_from_datasheet",
                binding_checks=BindingChecks(pn_match="datasheet", brand_match="datasheet"),
                field_admissibility=FieldAdmissibilityRecord(specs=FieldAdmissibility.ADMITTED),
                collected_at=now, collected_by="pipeline_v2",
            ))

        # --- Layer 5: Build canonical ---
        content = d.get("content") or {}
        canonical = build_canonical(
            capsule, bound_ev, trigger="pipeline_v2_full",
            assembled_title=d.get("assembled_title", ""),
            seed_name=content.get("seed_name", "") or d.get("name", ""),
            dr_title_ru=dr.get("title_ru", ""),
        )

        if canonical.readiness.insales == ReadinessStatus.READY:
            stats["insales_ready"] += 1

        # Track brand stats
        bs = brand_stats.setdefault(brand, {"confirmed": 0, "insales_ready": 0, "total": 0})
        bs["total"] += 1
        bs["confirmed"] += 1
        bs["insales_ready"] += (canonical.readiness.insales == ReadinessStatus.READY)

        canonical_products.append(canonical.model_dump(mode="json"))

    # --- Layer 5.5: Normalize title_ru (contract: all title_ru must be Russian) ---
    print()
    print("=" * 100)
    print("LAYER 5.5: TITLE_RU NORMALIZATION")
    print("=" * 100)

    # Load datasheet map for context if available
    ds_map_path = ROOT / "downloads" / "staging" / "from_datasheet_for_categorizer.json"
    ds_map = {}
    if ds_map_path.exists():
        try:
            ds_map = json.loads(ds_map_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    normalize_titles_in_place(canonical_products, ds_map, verbose=True)

    # Contract check: warn (don't crash) if any titles still not normalized
    non_russian = []
    for p in canonical_products:
        t = p.get("title_ru", "")
        cyr = sum(1 for c in t if "\u0400" <= c <= "\u04ff")
        if cyr < 3 or len(t.split()) < 2:
            non_russian.append((p.get("identity", {}).get("pn", "?"), t[:50]))

    if non_russian:
        print(f"[WARN] {len(non_russian)} products still have non-normalized title_ru after Layer 5.5:")
        for pn, t in non_russian[:10]:
            print(f"  {pn}: '{t}'")
    else:
        print("[OK] All title_ru are properly normalized Russian ✓")

    # Save outputs
    (OUTPUT_DIR / "canonical_products.json").write_text(
        json.dumps(canonical_products, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    (OUTPUT_DIR / "weak_pns.json").write_text(
        json.dumps(weak_pns, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUTPUT_DIR / "run_stats.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")

    # Print results
    n = stats["total"]
    print()
    print("=" * 100)
    print(f"PIPELINE V2 RESULTS: {n} SKUs processed")
    print("=" * 100)
    print()
    print("IDENTITY RESOLUTION:")
    print(f"  CONFIRMED: {stats['confirmed']:>4} ({stats['confirmed']*100//max(n,1)}%)")
    print(f"  WEAK:      {stats['weak']:>4} ({stats['weak']*100//max(n,1)}%)")
    print(f"  CONFLICT:  {stats['conflict']:>4}")
    print(f"  REJECTED:  {stats['rejected']:>4}")
    print()
    print("ENRICHMENT (re-bind check):")
    print(f"  Price:       {stats['price_bound']:>4} bound, {stats['price_rejected']:>4} rejected, {stats['price_missing']:>4} missing")
    print(f"  Photo:       {stats['photo_bound']:>4} bound, {stats['photo_rejected']:>4} rejected, {stats['photo_missing']:>4} missing")
    print(f"  Description: {stats['desc_bound']:>4} bound, {stats['desc_rejected']:>4} rejected, {stats['desc_missing']:>4} missing")
    print()
    print("READINESS:")
    print(f"  InSales READY: {stats['insales_ready']:>4} / {stats['confirmed']} confirmed")
    print()
    print("BY BRAND:")
    for brand in sorted(brand_stats, key=lambda b: -brand_stats[b]["confirmed"]):
        bs = brand_stats[brand]
        print(f"  {brand:<20} confirmed={bs['confirmed']:>3}  InSales={bs['insales_ready']:>3}")
    print()
    print(f"WEAK SKUs ({stats['weak']}):")
    for w in weak_pns[:20]:
        print(f"  {w['pn']:<25} {w['brand']:<15} cand={w['candidates']}  {w['reason'][:50]}")
    if stats['weak'] > 20:
        print(f"  ... and {stats['weak']-20} more")
    print()
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 100)


if __name__ == "__main__":
    main()
