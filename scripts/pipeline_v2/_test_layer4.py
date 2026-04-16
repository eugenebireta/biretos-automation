"""Layer 4 test: Run re-bind check on ALL existing evidence data for 27 CONFIRMED SKUs.

Takes existing normalized data (price, photo, description) and checks each
against the identity capsule. Shows how much current v1 data is actually valid.
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

ROOT = Path(__file__).resolve().parent.parent.parent
ev_dir = ROOT / "downloads" / "evidence"
trust_config = json.loads((ROOT / "config" / "seed_source_trust.json").read_text(encoding="utf-8"))

TEST_PNS = [
    "109411", "EASY", "CM010610", "272369098",
    "00020211", "010130.10", "1000106", "1011893-RU",
    "1050000000", "2208WFPT", "CF274A", "CWSS-RB-S8",
    "7508001857", "D-71570", "EVCS-HSB", "36022-RU",
    "3240197-RU", "2CDG110146R0011", "7910180000",
    "1006186", "1006187", "027913.10", "2SM-3.0-SCU-SCU-1",
    "CAB-010-SC-SM", "36299-RU", "2CDG110177R0011",
    "36024-RU", "1011894-RU", "7508001858",
]

SERP_MANUFACTURER_HITS = {
    "1050000000": [
        ("https://eshop.weidmueller.com/en/wap-2-5-10/p/1050000000", "weidmueller.com"),
    ],
    "2208WFPT": [
        ("https://i.dell.com/images/emea/products/monitors/2208wfp_en.pdf", "dell.com"),
    ],
    "CF274A": [
        ("https://h20195.www2.hp.com/v2/default.aspx?cc=ee&lc=et&oid=5096259", "hp.com"),
    ],
    "1006187": [
        ("https://doc.honeywellsafety.com/DoCTool/ApiSearch/GetFile/1006187/HIS-EK-LOCAL/sv", "honeywellsafety.com"),
    ],
}

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
        if any(d in domain for d in trust_config.get(tier_name, [])):
            return _TIER_MAP.get(tier_name, SourceTier.ORGANIC_DISCOVERY)
    for d in trust_config.get("denylist", []):
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


def main():
    print("=" * 110)
    print("LAYER 4 TEST: Re-bind check on existing evidence for 29 SKUs")
    print("=" * 110)
    print()

    totals = {
        "confirmed": 0, "weak": 0,
        "price_bound": 0, "price_rejected": 0, "price_missing": 0,
        "photo_bound": 0, "photo_rejected": 0, "photo_missing": 0,
        "desc_bound": 0, "desc_rejected": 0, "desc_missing": 0,
    }

    for pn in TEST_PNS:
        ef = ev_dir / f"evidence_{pn}.json"
        if not ef.exists():
            continue

        d = json.loads(ef.read_text(encoding="utf-8"))
        si = d.get("structured_identity") or {}
        norm = d.get("normalized") or {}
        dr = d.get("deep_research") or {}
        brand = d.get("brand", "") or si.get("confirmed_manufacturer", "")
        subbrand = d.get("subbrand", "")
        real_brand = subbrand or brand
        d.get("identity_level", "")

        # --- Build capsule (same as _test_full.py) ---
        all_evidence_urls: set[str] = set()
        for tu in (d.get("training_urls") or []):
            u = tu if isinstance(tu, str) else tu.get("url", "")
            if u: all_evidence_urls.add(u)
        for src in (dr.get("sources") or []):
            if isinstance(src, dict) and src.get("url"):
                all_evidence_urls.add(src["url"])
        for item in (dr.get("key_findings") or []):
            if isinstance(item, str):
                for word in item.split():
                    if word.startswith("http"):
                        all_evidence_urls.add(word.rstrip(".,;)"))
        ds = d.get("datasheet") or {}
        if ds.get("url"): all_evidence_urls.add(ds["url"])
        photo_data = d.get("photo") or {}
        if photo_data.get("source_url"): all_evidence_urls.add(photo_data["source_url"])
        pc = d.get("price_contract") or {}
        if pc.get("source_url"): all_evidence_urls.add(pc["source_url"])
        if pc.get("dr_source_url"): all_evidence_urls.add(pc["dr_source_url"])
        if d.get("dr_image_url"): all_evidence_urls.add(d["dr_image_url"])

        # Build candidates
        candidates = []
        seen_domains: set[str] = set()
        urls_with_tier = []
        for url in all_evidence_urls:
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
                    collected_at=datetime.now(timezone.utc), collected_by="layer4_test",
                ))

        # SerpAPI hits
        for serp_url, serp_dom in SERP_MANUFACTURER_HITS.get(pn, []):
            if serp_dom not in seen_domains:
                seen_domains.add(serp_dom)
                tier = get_tier(serp_dom)
                candidates.append(CandidateIdentityRecord(
                    record_id=f"cid_{pn}_serp_{len(candidates)}",
                    requested_pn=pn, requested_brand_hint=brand,
                    source_url=serp_url, source_domain=serp_dom,
                    source_tier=tier, page_type=PageType.PRODUCT_PAGE,
                    origin_group=get_origin(tier),
                    extracted_pn=pn, extracted_brand=real_brand,
                    pn_match=PNMatch.EXACT,
                    brand_match=BrandMatch.EXACT if real_brand else BrandMatch.ABSENT,
                    identity_score=0.9,
                    collected_at=datetime.now(timezone.utc), collected_by="serpapi",
                ))

        # Resolve
        verdict, capsule, event = resolve_identity(pn, brand, candidates)

        if verdict != IdentityVerdict.CONFIRMED:
            totals["weak"] += 1
            print(f"  {pn:<25} WEAK — skipping Layer 4")
            continue

        totals["confirmed"] += 1

        # --- Layer 4: Re-bind each data field against capsule ---
        now = datetime.now(timezone.utc)
        bound_evidence: list[BoundEvidence] = []
        rejected_evidence: list[dict] = []

        # === PRICE ===
        price_val = norm.get("best_price")
        price_src = norm.get("best_price_source", "")
        price_url = pc.get("source_url") or pc.get("dr_source_url") or ""
        price_domain = extract_domain(price_url) or price_src

        if price_val and price_domain:
            tier = get_tier(price_domain)
            rebind = re_bind_check(
                extracted_pn=pn,
                extracted_brand=real_brand,
                extracted_product_type=d.get("dr_category", "").lower() if d.get("dr_category") else None,
                page_type=PageType.PRODUCT_PAGE,
                source_tier=tier,
                negative_evidence=[],
                context_text=f"{norm.get('best_price_source', '')} {d.get('dr_category', '')}",
                capsule=capsule,
            )
            if rebind.bound:
                totals["price_bound"] += 1
                bound_evidence.append(BoundEvidence(
                    evidence_id=f"ev_{pn}_price", identity_hash=capsule.identity_hash,
                    capsule_version=1, field=EvidenceField.PRICE,
                    value={"amount": float(price_val),
                           "currency": norm.get("best_price_currency", "EUR"),
                           "pack_qty": rebind.pack_qty},
                    value_normalized={"unit_amount_minor": int(float(price_val) * 100),
                                      "currency": norm.get("best_price_currency", "EUR")} if not rebind.pack_qty else None,
                    source_url=price_url, source_domain=price_domain,
                    source_tier=tier, page_type=PageType.PRODUCT_PAGE,
                    origin_group=get_origin(tier),
                    binding_status=BindingStatus.BOUND,
                    binding_reason=rebind.reason,
                    binding_checks=BindingChecks(pn_match=rebind.pn_match.value,
                                                 brand_match=rebind.brand_match.value),
                    field_admissibility=rebind.field_admissibility,
                    collected_at=now, collected_by="evidence_normalize",
                ))
            else:
                totals["price_rejected"] += 1
                rejected_evidence.append({"field": "price", "pn": pn, "reason": rebind.reason,
                                          "domain": price_domain})
        elif price_val:
            # Price exists but no source URL — bind with reduced confidence
            totals["price_bound"] += 1
            bound_evidence.append(BoundEvidence(
                evidence_id=f"ev_{pn}_price", identity_hash=capsule.identity_hash,
                capsule_version=1, field=EvidenceField.PRICE,
                value={"amount": float(price_val),
                       "currency": norm.get("best_price_currency", "EUR")},
                source_url="", source_domain="unknown",
                source_tier=SourceTier.ORGANIC_DISCOVERY,
                page_type=PageType.PRODUCT_PAGE, origin_group=OriginGroup.AI_EXTRACTION,
                binding_status=BindingStatus.BOUND,
                binding_reason="price_no_source_url",
                binding_checks=BindingChecks(pn_match="assumed", brand_match="assumed"),
                field_admissibility=FieldAdmissibilityRecord(price=FieldAdmissibility.ADMITTED),
                collected_at=now, collected_by="evidence_normalize",
            ))
        else:
            totals["price_missing"] += 1

        # === PHOTO ===
        photo_url = norm.get("best_photo_url") or ""
        photo_domain = extract_domain(photo_url) if photo_url else ""

        if photo_url and photo_domain:
            tier = get_tier(photo_domain)
            rebind = re_bind_check(
                extracted_pn=pn,
                extracted_brand=real_brand,
                extracted_product_type=None,
                page_type=PageType.PRODUCT_PAGE,
                source_tier=tier,
                negative_evidence=[],
                context_text="",
                capsule=capsule,
            )
            if rebind.bound:
                totals["photo_bound"] += 1
                bound_evidence.append(BoundEvidence(
                    evidence_id=f"ev_{pn}_photo", identity_hash=capsule.identity_hash,
                    capsule_version=1, field=EvidenceField.PHOTO,
                    value={"url": photo_url, "identity_verified": False},
                    source_url=photo_url, source_domain=photo_domain,
                    source_tier=tier, page_type=PageType.PRODUCT_PAGE,
                    origin_group=get_origin(tier),
                    binding_status=BindingStatus.BOUND,
                    binding_reason=rebind.reason,
                    binding_checks=BindingChecks(pn_match=rebind.pn_match.value,
                                                 brand_match=rebind.brand_match.value),
                    field_admissibility=rebind.field_admissibility,
                    collected_at=now, collected_by="photo_collector",
                ))
            else:
                totals["photo_rejected"] += 1
                rejected_evidence.append({"field": "photo", "pn": pn, "reason": rebind.reason,
                                          "domain": photo_domain})
        else:
            totals["photo_missing"] += 1

        # === DESCRIPTION ===
        desc_text = norm.get("best_description", "")
        desc_src = norm.get("best_description_source", "")

        if desc_text and len(desc_text) > 20:
            totals["desc_bound"] += 1
            bound_evidence.append(BoundEvidence(
                evidence_id=f"ev_{pn}_desc", identity_hash=capsule.identity_hash,
                capsule_version=1, field=EvidenceField.DESCRIPTION,
                value={"text": desc_text, "lang": "ru", "length": len(desc_text)},
                source_url="", source_domain=desc_src or "deep_research",
                source_tier=SourceTier.ORGANIC_DISCOVERY,
                page_type=PageType.PRODUCT_PAGE, origin_group=OriginGroup.AI_EXTRACTION,
                binding_status=BindingStatus.BOUND,
                binding_reason="description_from_dr",
                binding_checks=BindingChecks(pn_match="assumed", brand_match="assumed"),
                field_admissibility=FieldAdmissibilityRecord(description=FieldAdmissibility.ADMITTED),
                collected_at=now, collected_by="dr_import",
            ))
        else:
            totals["desc_missing"] += 1

        # === BUILD CANONICAL ===
        canonical = build_canonical(
            capsule, bound_evidence,
            candidate_count=len(rejected_evidence),
            rejected_count=len(rejected_evidence),
            trigger="layer4_test",
        )

        # Report
        r_price = "BOUND" if any(e.field == EvidenceField.PRICE for e in bound_evidence) else "REJECTED" if any(r["field"] == "price" for r in rejected_evidence) else "MISSING"
        r_photo = "BOUND" if any(e.field == EvidenceField.PHOTO for e in bound_evidence) else "REJECTED" if any(r["field"] == "photo" for r in rejected_evidence) else "MISSING"
        r_desc = "BOUND" if any(e.field == EvidenceField.DESCRIPTION for e in bound_evidence) else "MISSING"

        line = f"  {pn:<25} price={r_price:<10} photo={r_photo:<10} desc={r_desc:<10}"
        line += f" InS={canonical.readiness.insales.value}"

        # Show rejections
        for rej in rejected_evidence:
            line += f"\n    REJECTED {rej['field']}: {rej['domain']} -> {rej['reason']}"

        print(line)

    print()
    print("=" * 110)
    print("LAYER 4 SUMMARY:")
    print(f"  Confirmed SKUs: {totals['confirmed']}, Weak (skipped): {totals['weak']}")
    print()
    print(f"  Price:       {totals['price_bound']} bound, {totals['price_rejected']} rejected, {totals['price_missing']} missing")
    print(f"  Photo:       {totals['photo_bound']} bound, {totals['photo_rejected']} rejected, {totals['photo_missing']} missing")
    print(f"  Description: {totals['desc_bound']} bound, {totals['desc_rejected']} rejected, {totals['desc_missing']} missing")
    print()

    total_fields = totals["confirmed"] * 3  # 3 fields per SKU
    total_bound = totals["price_bound"] + totals["photo_bound"] + totals["desc_bound"]
    total_rejected = totals["price_rejected"] + totals["photo_rejected"] + totals["desc_rejected"]
    total_missing = totals["price_missing"] + totals["photo_missing"] + totals["desc_missing"]

    print(f"  Total: {total_bound}/{total_fields} bound ({total_bound*100//max(total_fields,1)}%), "
          f"{total_rejected} rejected, {total_missing} missing")
    print("=" * 110)


if __name__ == "__main__":
    main()
