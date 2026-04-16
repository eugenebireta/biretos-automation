"""Full pipeline test: Resolver + Builder on 29 real SKUs."""
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


TIER_LOOKUP_ORDER = [
    "manufacturer_proof",
    "authorized_distributor",
    "industrial_distributor",
    "marketplace_fallback",
    "datasheet_source",
    "customs_price_source",
    "price_aggregator",
    "tender_source",
    "technical_reference",
    "product_review",
    "noise_source",
]

# Map specialized tiers to SourceTier enum (they act as industrial_distributor level for resolver)
_TIER_MAP = {
    "manufacturer_proof": SourceTier.MANUFACTURER_PROOF,
    "authorized_distributor": SourceTier.AUTHORIZED_DISTRIBUTOR,
    "industrial_distributor": SourceTier.INDUSTRIAL_DISTRIBUTOR,
    "marketplace_fallback": SourceTier.MARKETPLACE_FALLBACK,
    "datasheet_source": SourceTier.INDUSTRIAL_DISTRIBUTOR,  # specs authority
    "customs_price_source": SourceTier.INDUSTRIAL_DISTRIBUTOR,  # price authority
    "price_aggregator": SourceTier.MARKETPLACE_FALLBACK,  # price reference
    "tender_source": SourceTier.INDUSTRIAL_DISTRIBUTOR,  # real procurement price
    "technical_reference": SourceTier.ORGANIC_DISCOVERY,  # not for identity
    "product_review": SourceTier.ORGANIC_DISCOVERY,  # not for identity
    "noise_source": SourceTier.ORGANIC_DISCOVERY,  # ignore for identity
}

# SerpAPI results we already found for WEAK SKUs (manufacturer sites)
SERP_MANUFACTURER_HITS = {
    "1050000000": [
        ("https://eshop.weidmueller.com/en/wap-2-5-10/p/1050000000", "weidmueller.com"),
        ("https://datasheet.weidmueller.com/pdf/en/1050000000/scope/2/", "datasheet.weidmueller.com"),
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
    "272369098": [],  # not found on manufacturer site
}


def get_tier(domain: str) -> SourceTier:
    for tier_name in TIER_LOOKUP_ORDER:
        tier_domains = trust_config.get(tier_name, [])
        if any(d in domain for d in tier_domains):
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
    return OriginGroup.AI_EXTRACTION


def main():
    print("=" * 110)
    print("FULL PIPELINE TEST: Resolver + Builder on 29 real SKUs")
    print("=" * 110)

    verdicts = {"CONFIRMED": 0, "WEAK": 0, "CONFLICT": 0, "REJECTED": 0}
    readiness_counts = {"insales_ready": 0, "ozon_ready": 0, "wb_ready": 0}

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
        dr_image_url = d.get("dr_image_url", "")

        # Build candidate records from evidence
        candidates: list[CandidateIdentityRecord] = []

        if dr_image_url:
            try:
                domain = urlparse(dr_image_url).netloc.replace("www.", "")
            except Exception:
                domain = ""
            tier = get_tier(domain)
            candidates.append(CandidateIdentityRecord(
                record_id=f"cid_{pn}_dr",
                requested_pn=pn, requested_brand_hint=brand,
                source_url=dr_image_url, source_domain=domain,
                source_tier=tier, page_type=PageType.PRODUCT_PAGE,
                origin_group=get_origin(tier),
                extracted_pn=pn, extracted_brand=real_brand,
                pn_match=PNMatch.EXACT,
                brand_match=BrandMatch.EXACT if real_brand else BrandMatch.ABSENT,
                identity_score=0.8,
                collected_at=datetime.now(timezone.utc), collected_by="dr_import",
            ))

        # Collect ALL URLs from ALL evidence fields
        all_evidence_urls: set[str] = set()

        # training_urls
        for tu_item in (d.get("training_urls") or []):
            url = tu_item if isinstance(tu_item, str) else tu_item.get("url", "")
            if url: all_evidence_urls.add(url)

        # DR sources
        for src in (dr.get("sources") or []):
            if isinstance(src, dict) and src.get("url"):
                all_evidence_urls.add(src["url"])

        # key_findings URLs
        for item in (dr.get("key_findings") or []):
            if isinstance(item, str):
                for word in item.split():
                    if word.startswith("http"):
                        all_evidence_urls.add(word.rstrip(".,;)"))

        # datasheet
        ds = d.get("datasheet") or {}
        if ds.get("url"): all_evidence_urls.add(ds["url"])

        # photo source
        photo = d.get("photo") or {}
        if photo.get("source_url"): all_evidence_urls.add(photo["source_url"])

        # price source
        price_data = d.get("price") or {}
        if price_data.get("page_url"): all_evidence_urls.add(price_data["page_url"])

        # price_contract source
        pc = d.get("price_contract") or {}
        if pc.get("source_url"): all_evidence_urls.add(pc["source_url"])
        if pc.get("dr_source_url"): all_evidence_urls.add(pc["dr_source_url"])

        # Classify and prioritize
        urls_with_tier = []
        for url in all_evidence_urls:
            try:
                dom = urlparse(url).netloc.replace("www.", "")
            except Exception:
                continue
            if not dom or len(dom) < 4:
                continue
            tier = get_tier(dom)
            if tier == SourceTier.DENYLIST:
                continue
            urls_with_tier.append((url, dom, tier))

        tier_order = {SourceTier.MANUFACTURER_PROOF: 0, SourceTier.AUTHORIZED_DISTRIBUTOR: 1,
                      SourceTier.INDUSTRIAL_DISTRIBUTOR: 2, SourceTier.ORGANIC_DISCOVERY: 3}
        urls_with_tier.sort(key=lambda x: tier_order.get(x[2], 99))

        # Deduplicate by domain (keep first = best tier)
        seen_domains: set[str] = set()
        deduped = []
        for url, dom, tier in urls_with_tier:
            if dom not in seen_domains:
                seen_domains.add(dom)
                deduped.append((url, dom, tier))

        for i, (url, domain, tier) in enumerate(deduped[:12]):
            candidates.append(CandidateIdentityRecord(
                record_id=f"cid_{pn}_tu{i}",
                requested_pn=pn, requested_brand_hint=brand,
                source_url=url, source_domain=domain,
                source_tier=tier, page_type=PageType.PRODUCT_PAGE,
                origin_group=get_origin(tier),
                extracted_pn=pn, extracted_brand=real_brand,
                pn_match=PNMatch.EXACT,
                brand_match=BrandMatch.EXACT if real_brand else BrandMatch.ABSENT,
                identity_score=0.7,
                collected_at=datetime.now(timezone.utc), collected_by="training_urls",
            ))

        # Add SerpAPI manufacturer hits (already discovered)
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
                    collected_at=datetime.now(timezone.utc), collected_by="serpapi_manufacturer",
                ))

        # Resolve
        verdict, capsule, event = resolve_identity(pn, brand, candidates)
        verdicts[verdict.value] += 1

        # Build canonical
        canonical = None
        if capsule:
            bound: list[BoundEvidence] = []
            now = datetime.now(timezone.utc)

            if norm.get("best_price"):
                bound.append(BoundEvidence(
                    evidence_id=f"ev_{pn}_price", identity_hash=capsule.identity_hash,
                    capsule_version=1, field=EvidenceField.PRICE,
                    value={"amount": float(norm["best_price"]),
                           "currency": norm.get("best_price_currency", "EUR")},
                    source_url="", source_domain=norm.get("best_price_source", ""),
                    source_tier=SourceTier.AUTHORIZED_DISTRIBUTOR,
                    page_type=PageType.PRODUCT_PAGE, origin_group=OriginGroup.DISTRIBUTOR,
                    binding_status=BindingStatus.BOUND, binding_reason="exact+exact",
                    binding_checks=BindingChecks(pn_match="exact", brand_match="exact"),
                    field_admissibility=FieldAdmissibilityRecord(price=FieldAdmissibility.ADMITTED),
                    collected_at=now, collected_by="normalize",
                ))

            if norm.get("best_photo_url"):
                bound.append(BoundEvidence(
                    evidence_id=f"ev_{pn}_photo", identity_hash=capsule.identity_hash,
                    capsule_version=1, field=EvidenceField.PHOTO,
                    value={"url": norm["best_photo_url"]},
                    source_url=norm["best_photo_url"],
                    source_domain=norm.get("best_photo_source", ""),
                    source_tier=SourceTier.AUTHORIZED_DISTRIBUTOR,
                    page_type=PageType.PRODUCT_PAGE, origin_group=OriginGroup.DISTRIBUTOR,
                    binding_status=BindingStatus.BOUND, binding_reason="exact+exact",
                    binding_checks=BindingChecks(pn_match="exact", brand_match="exact"),
                    field_admissibility=FieldAdmissibilityRecord(photo=FieldAdmissibility.ADMITTED),
                    collected_at=now, collected_by="photo_collector",
                ))

            if norm.get("best_description"):
                desc_text = norm["best_description"]
                bound.append(BoundEvidence(
                    evidence_id=f"ev_{pn}_desc", identity_hash=capsule.identity_hash,
                    capsule_version=1, field=EvidenceField.DESCRIPTION,
                    value={"text": desc_text, "lang": "ru", "length": len(desc_text)},
                    source_url="", source_domain=norm.get("best_description_source", ""),
                    source_tier=SourceTier.AUTHORIZED_DISTRIBUTOR,
                    page_type=PageType.PRODUCT_PAGE, origin_group=OriginGroup.DISTRIBUTOR,
                    binding_status=BindingStatus.BOUND, binding_reason="exact+exact",
                    binding_checks=BindingChecks(pn_match="exact", brand_match="exact"),
                    field_admissibility=FieldAdmissibilityRecord(
                        description=FieldAdmissibility.ADMITTED),
                    collected_at=now, collected_by="dr_import",
                ))

            canonical = build_canonical(capsule, bound, trigger="test")
            readiness_counts["insales_ready"] += (canonical.readiness.insales == ReadinessStatus.READY)
            readiness_counts["ozon_ready"] += (canonical.readiness.ozon == ReadinessStatus.READY)
            readiness_counts["wb_ready"] += (canonical.readiness.wb == ReadinessStatus.READY)

        # Report
        n_cand = len(candidates)
        line = f"  {pn:<25} {verdict.value:<10} cand={n_cand:<3}"
        if capsule:
            line += f" class={capsule.identity_class.value:<15}"
        if canonical:
            line += f" InS={canonical.readiness.insales.value:<6}"
            line += f" Oz={canonical.readiness.ozon.value:<22}"
            line += f" ev={canonical.evidence_stats.bound_count}"
        else:
            line += f" reason: {event.verdict_reason[:55]}"
        print(line)

    print()
    print("=" * 110)
    print(f"VERDICTS:  {verdicts}")
    print(f"READINESS: {readiness_counts} (of {verdicts['CONFIRMED']} confirmed)")
    print("=" * 110)


if __name__ == "__main__":
    main()
