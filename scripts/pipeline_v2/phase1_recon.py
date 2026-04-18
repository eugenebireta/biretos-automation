"""Pipeline v2 Phase 1 — Identity Recon via Haiku.

For WEAK SKUs: ask Haiku to find the product on trusted sites,
confirm brand + PN + product_type, return candidate_identity_records.

Uses identity capsule prompt pattern: tells AI what we know, asks to verify.
Cost: ~$0.001 per SKU (Haiku).

Source of truth: docs/PIPELINE_ARCHITECTURE_v2.md Layer 1 + section 9.
"""
from __future__ import annotations

import json
import sys
import io
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.pipeline_v2.enums import (
    BrandMatch, OriginGroup, PageType, PNMatch,
    ProductTypeMatch, SourceTier,
)
from scripts.pipeline_v2.models import CandidateIdentityRecord

ROOT = Path(__file__).resolve().parent.parent.parent
TRUST_CONFIG = ROOT / "config" / "seed_source_trust.json"
BRAND_RATING = ROOT / "config" / "brand_site_rating.json"

SYSTEM_PROMPT = (
    "You are a product identity verification assistant. "
    "Your task is to confirm whether a part number belongs to the claimed brand "
    "and identify what type of product it is.\n\n"
    "Return ONLY a JSON object with these fields:\n"
    '{"confirmed_brand":"","confirmed_pn":"","product_type":"","series":"","ean":"","sources":[]}\n\n'
    "Each source: {\"url\":\"\",\"domain\":\"\",\"page_type\":\"product_page|datasheet|catalog_page\","
    "\"extracted_title\":\"\",\"has_price\":false,\"has_photo\":false,\"has_specs\":false}\n\n"
    "Rules:\n"
    "- Find the product on official manufacturer sites and authorized distributors\n"
    "- If PN exists in multiple manufacturers' catalogs, identify which one matches the brand hint\n"
    "- Report actual URLs you found, not invented ones\n"
    "- If you cannot confirm, set confirmed_brand to empty string\n"
    "- product_type should be a short English label: switch_cover, valve, sensor, cable, etc.\n"
    "- ean should be the EAN/GTIN barcode if found, empty string if not\n"
)


def _build_search_hints(brand: str, pn: str) -> str:
    """Build search hints from brand_site_rating and trust config."""
    hints = []

    # Load brand rating for recommended sites
    try:
        rating = json.loads(BRAND_RATING.read_text(encoding="utf-8"))
        brand_entry = rating.get(brand, {})
        top_sites = brand_entry.get("all_sites", [])[:5]
        if top_sites:
            domains = [s["domain"] for s in top_sites]
            hints.append(f"Known sites for {brand}: {', '.join(domains)}")
    except Exception:
        pass

    # Load trusted domains
    try:
        trust = json.loads(TRUST_CONFIG.read_text(encoding="utf-8"))
        tier1 = trust.get("manufacturer_proof", [])
        trust.get("authorized_distributor", [])
        # Find brand-relevant manufacturer domains
        brand_lower = brand.lower()
        relevant = [d for d in tier1 if brand_lower in d.lower()]
        if relevant:
            hints.append(f"Manufacturer sites: {', '.join(relevant)}")
        hints.append("Check distributors: mouser.com, rs-online.com, digikey.com, farnell.com")
    except Exception:
        pass

    return "\n".join(hints)


def run_phase1_recon(
    pn: str,
    brand_hint: str,
    seed_name: str = "",
    our_price_raw: str = "",
) -> list[CandidateIdentityRecord]:
    """Run Phase 1 Haiku recon for one SKU.

    Returns candidate_identity_records from AI response.
    """
    from scripts.app_secrets import get_secret
    import anthropic

    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    search_hints = _build_search_hints(brand_hint, pn)

    user_prompt = (
        f"Verify this product identity:\n"
        f"  Part number: {pn}\n"
        f"  Brand hint: {brand_hint}\n"
    )
    if seed_name:
        user_prompt += f"  Product name from catalog: {seed_name}\n"
    if our_price_raw:
        user_prompt += f"  Reference price (RUB): {our_price_raw}\n"
    user_prompt += (
        f"\n{search_hints}\n\n"
        f"Find this exact PN on the manufacturer's site and at least one distributor. "
        f"Confirm the brand, product type, and EAN if available."
    )

    from orchestrator._api_cost_tracker import log_api_call, timed
    model = "claude-haiku-4-5-20251001"
    with timed() as t:
        resp = client.messages.create(
            model=model,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
    log_api_call(__file__, model, resp.usage, duration_ms=t.ms)

    text = resp.content[0].text.strip()
    # Parse JSON from response
    if "```" in text:
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    # Convert to candidate records
    candidates = []
    confirmed_brand = data.get("confirmed_brand", "")
    confirmed_pn = data.get("confirmed_pn", pn)
    product_type = data.get("product_type", "")
    ean = data.get("ean", "")

    trust = json.loads(TRUST_CONFIG.read_text(encoding="utf-8"))

    for src in data.get("sources", []):
        url = src.get("url", "")
        if not url:
            continue
        try:
            domain = urlparse(url).netloc.replace("www.", "")
        except Exception:
            continue

        # Classify tier
        source_tier = SourceTier.ORGANIC_DISCOVERY
        for tier_name, domains in [
            ("manufacturer_proof", trust.get("manufacturer_proof", [])),
            ("authorized_distributor", trust.get("authorized_distributor", [])),
            ("industrial_distributor", trust.get("industrial_distributor", [])),
        ]:
            if any(d in domain for d in domains):
                source_tier = SourceTier(tier_name)
                break

        # Classify page type
        page_type_str = src.get("page_type", "product_page")
        try:
            page_type = PageType(page_type_str)
        except ValueError:
            page_type = PageType.PRODUCT_PAGE

        # Origin group
        if source_tier == SourceTier.MANUFACTURER_PROOF:
            origin = OriginGroup.MANUFACTURER
        elif source_tier in (SourceTier.AUTHORIZED_DISTRIBUTOR, SourceTier.INDUSTRIAL_DISTRIBUTOR):
            origin = OriginGroup.DISTRIBUTOR
        else:
            origin = OriginGroup.AI_EXTRACTION

        # PN/brand match
        pn_match = PNMatch.EXACT if confirmed_pn.upper() == pn.upper() else PNMatch.NORMALIZED
        brand_match = BrandMatch.EXACT if confirmed_brand else BrandMatch.ABSENT

        candidates.append(CandidateIdentityRecord(
            record_id=f"cid_{pn}_haiku_{uuid.uuid4().hex[:6]}",
            search_batch_id="phase1_recon_test",
            requested_pn=pn,
            requested_brand_hint=brand_hint,
            source_url=url,
            source_domain=domain,
            source_tier=source_tier,
            page_type=page_type,
            origin_group=origin,
            extracted_pn=confirmed_pn,
            extracted_brand=confirmed_brand,
            extracted_ean=ean or None,
            extracted_title=src.get("extracted_title", ""),
            extracted_product_type=product_type,
            pn_match=pn_match,
            brand_match=brand_match,
            product_type_match=ProductTypeMatch.EXACT if product_type else ProductTypeMatch.UNKNOWN,
            identity_score=0.85,
            collected_at=datetime.now(timezone.utc),
            collected_by="phase1_haiku_recon",
        ))

    return candidates


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    weak_pns = [
        ("272369098", "Honeywell", ""),
        ("1050000000", "Weidmuller", ""),
        ("2208WFPT", "Dell", ""),
        ("CF274A", "HP", ""),
        ("D-71570", "Murrelektronik", ""),
        ("1006187", "Howard Leight", ""),
        ("2SM-3.0-SCU-SCU-1", "Optcom", ""),
    ]

    ev_dir = ROOT / "downloads" / "evidence"

    from scripts.pipeline_v2.resolver import resolve_identity

    print("=" * 90)
    print("Phase 1 Haiku Recon for 7 WEAK SKUs")
    print("=" * 90)

    for pn, brand, _ in weak_pns:
        # Load existing candidates from evidence
        ef = ev_dir / f"evidence_{pn}.json"
        d = json.loads(ef.read_text(encoding="utf-8"))
        seed_name = (d.get("content") or {}).get("seed_name", "") or d.get("name", "")
        our_price = str(d.get("our_price_raw", ""))

        print(f"\n  {pn} ({brand})...")

        # Run Haiku recon
        new_candidates = run_phase1_recon(pn, brand, seed_name, our_price)
        print(f"    Haiku returned {len(new_candidates)} sources:")
        for c in new_candidates:
            print(f"      {c.source_domain:<35} {c.source_tier.value:<25} type={c.extracted_product_type}")

        # Combine with existing evidence URLs
        existing_candidates = []
        trust_cfg = json.loads(TRUST_CONFIG.read_text(encoding="utf-8"))
        subbrand = d.get("subbrand", "")
        real_brand = subbrand or brand

        all_urls = set()
        for t in (d.get("training_urls") or []):
            u = t if isinstance(t, str) else t.get("url", "")
            if u: all_urls.add(u)
        if d.get("dr_image_url"): all_urls.add(d["dr_image_url"])
        dr = d.get("deep_research") or {}
        for src in (dr.get("sources") or []):
            if isinstance(src, dict) and src.get("url"):
                all_urls.add(src["url"])

        for i, url in enumerate(list(all_urls)[:10]):
            try:
                dom = urlparse(url).netloc.replace("www.", "")
            except Exception:
                continue
            tier = SourceTier.ORGANIC_DISCOVERY
            for tn, ds in [("manufacturer_proof", trust_cfg["manufacturer_proof"]),
                           ("authorized_distributor", trust_cfg["authorized_distributor"]),
                           ("industrial_distributor", trust_cfg["industrial_distributor"])]:
                if any(dd in dom for dd in ds):
                    tier = SourceTier(tn)
                    break
            if any(dd in dom for dd in trust_cfg.get("denylist", [])):
                continue
            origin = OriginGroup.MANUFACTURER if tier == SourceTier.MANUFACTURER_PROOF else OriginGroup.DISTRIBUTOR if "distributor" in tier.value else OriginGroup.AI_EXTRACTION
            existing_candidates.append(CandidateIdentityRecord(
                record_id=f"cid_{pn}_ev_{i}",
                requested_pn=pn, requested_brand_hint=brand,
                source_url=url, source_domain=dom,
                source_tier=tier, page_type=PageType.PRODUCT_PAGE,
                origin_group=origin,
                extracted_pn=pn, extracted_brand=real_brand,
                pn_match=PNMatch.EXACT,
                brand_match=BrandMatch.EXACT if real_brand else BrandMatch.ABSENT,
                identity_score=0.7,
                collected_at=datetime.now(timezone.utc), collected_by="existing_evidence",
            ))

        # Resolve with combined candidates
        all_candidates = existing_candidates + new_candidates
        verdict, capsule, event = resolve_identity(pn, brand, all_candidates)

        t1 = sum(1 for c in all_candidates if c.source_tier == SourceTier.MANUFACTURER_PROOF)
        t2 = sum(1 for c in all_candidates if c.source_tier == SourceTier.AUTHORIZED_DISTRIBUTOR)
        t3 = sum(1 for c in all_candidates if c.source_tier == SourceTier.INDUSTRIAL_DISTRIBUTOR)

        status = "PROMOTED!" if verdict.value == "CONFIRMED" else "still WEAK"
        print(f"    Resolve: {verdict.value:<10} total={len(all_candidates)} T1={t1} T2={t2} T3={t3}  {status}")
        if capsule:
            print(f"    Capsule: brand={capsule.confirmed_brand} type={capsule.product_type} ean={capsule.ean or '-'}")

    print("\n" + "=" * 90)
