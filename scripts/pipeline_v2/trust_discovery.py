"""Pipeline v2 Trust Discovery — auto-discover trusted domains from DR results.

Scans all evidence files, extracts domains from training_urls + dr.sources,
cross-validates (5+ refs with correct data for different PNs of same brand),
and proposes additions to seed_source_trust.json.

Also builds per-brand site rating: which domain gives best price/photo/specs/datasheet
for which brand, based on actual evidence data.

Source of truth: docs/PIPELINE_ARCHITECTURE_v2.md section 6.
"""
from __future__ import annotations

import json
import sys
import io
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent.parent
EVIDENCE_DIR = ROOT / "downloads" / "evidence"
TRUST_CONFIG = ROOT / "config" / "seed_source_trust.json"
BRAND_RATING_FILE = ROOT / "config" / "brand_site_rating.json"
DISCOVERY_REPORT = ROOT / "downloads" / "staging" / "trust_discovery_report.json"


def load_trust_config() -> dict:
    return json.loads(TRUST_CONFIG.read_text(encoding="utf-8"))


def _get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "").lower()
    except Exception:
        return ""


def _classify_tier(domain: str, trust: dict) -> str:
    for tier_name in ("manufacturer_proof", "authorized_distributor",
                      "industrial_distributor", "denylist"):
        if any(t in domain for t in trust.get(tier_name, [])):
            return tier_name
    return "organic"


def scan_evidence() -> dict:
    """Scan all evidence files and collect domain usage data.

    Returns dict with:
    - domain_stats: {domain: {brands, pn_count, has_price, has_photo, has_specs, ...}}
    - brand_stats: {brand: {domain: {field: success_count}}}
    """
    trust = load_trust_config()

    domain_stats: dict[str, dict] = {}
    brand_site_data: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )

    for f in sorted(EVIDENCE_DIR.glob("evidence_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        if not pn or pn.strip("-_") == "":
            continue

        si = d.get("structured_identity") or {}
        norm = d.get("normalized") or {}
        dr = d.get("deep_research") or {}
        brand = d.get("brand", "") or si.get("confirmed_manufacturer", "")
        subbrand = d.get("subbrand", "")
        real_brand = subbrand or brand
        if not real_brand:
            continue

        # Collect all URLs from evidence
        url_sources: list[tuple[str, str]] = []  # (url, context)

        # training_urls
        for tu in (d.get("training_urls") or []):
            url = tu if isinstance(tu, str) else tu.get("url", "")
            if url:
                url_sources.append((url, "training_url"))

        # DR image
        if d.get("dr_image_url"):
            url_sources.append((d["dr_image_url"], "dr_image"))

        # DR sources
        for src in (dr.get("sources") or []):
            if isinstance(src, dict) and src.get("url"):
                ctx_parts = []
                if src.get("has_price"):
                    ctx_parts.append("has_price")
                if src.get("has_specs"):
                    ctx_parts.append("has_specs")
                if src.get("has_photo"):
                    ctx_parts.append("has_photo")
                url_sources.append((src["url"], ",".join(ctx_parts) or "dr_source"))

        # Photo sources
        photo_src = (d.get("photo") or {}).get("source_url", "")
        if photo_src:
            url_sources.append((photo_src, "photo_source"))

        # Datasheet sources
        ds = d.get("datasheet") or {}
        if ds.get("url"):
            url_sources.append((ds["url"], "datasheet"))

        # Price source
        price_data = d.get("price") or {}
        if price_data.get("page_url"):
            url_sources.append((price_data["page_url"], "price_source"))

        # Determine what data this PN actually has
        has_price = bool(norm.get("best_price") or d.get("dr_price"))
        has_photo = bool(norm.get("best_photo_url") or d.get("dr_image_url"))
        has_description = bool(norm.get("best_description") or dr.get("description_ru"))
        bool(dr.get("specs"))
        bool(ds.get("url") or ds.get("local_path"))

        # Attribute fields to source domains based on normalized data provenance
        price_source_domain = _get_domain(norm.get("best_price_source", "")) or ""
        photo_source_domain = _get_domain(norm.get("best_photo_url", "")) or ""
        desc_source_domain = _get_domain(norm.get("best_description_source", "")) or ""

        # Track which domain actually provided each field
        if has_price and price_source_domain:
            brand_site_data[real_brand][price_source_domain]["price"] += 1
        if has_photo and photo_source_domain:
            brand_site_data[real_brand][photo_source_domain]["photo"] += 1
        if has_description and desc_source_domain:
            brand_site_data[real_brand][desc_source_domain]["description"] += 1

        for url, context in url_sources:
            domain = _get_domain(url)
            if not domain or len(domain) < 4:
                continue

            # Domain stats
            if domain not in domain_stats:
                domain_stats[domain] = {
                    "domain": domain,
                    "brands": set(),
                    "pns": set(),
                    "current_tier": _classify_tier(domain, trust),
                    "contexts": Counter(),
                    "field_evidence": {
                        "price": 0, "photo": 0, "description": 0,
                        "specs": 0, "datasheet": 0,
                    },
                }
            ds_entry = domain_stats[domain]
            ds_entry["brands"].add(real_brand)
            ds_entry["pns"].add(pn)
            ds_entry["contexts"][context] += 1

            # Track what fields this domain provided
            if "dr_image" in context or "photo" in context:
                ds_entry["field_evidence"]["photo"] += 1
                brand_site_data[real_brand][domain]["photo"] += 1
            if "has_price" in context or "price" in context:
                ds_entry["field_evidence"]["price"] += 1
                brand_site_data[real_brand][domain]["price"] += 1
            if "has_specs" in context:
                ds_entry["field_evidence"]["specs"] += 1
                brand_site_data[real_brand][domain]["specs"] += 1
            if "has_photo" in context:
                ds_entry["field_evidence"]["photo"] += 1
                brand_site_data[real_brand][domain]["photo"] += 1
            if "datasheet" in context:
                ds_entry["field_evidence"]["datasheet"] += 1
                brand_site_data[real_brand][domain]["datasheet"] += 1
            if "training_url" in context:
                # Training URLs generally provide some combination
                brand_site_data[real_brand][domain]["referenced"] += 1

    # Convert sets to counts for JSON serialization
    for dom, stats in domain_stats.items():
        stats["brand_count"] = len(stats["brands"])
        stats["pn_count"] = len(stats["pns"])
        stats["brands"] = sorted(stats["brands"])
        stats["pns"] = sorted(stats["pns"])[:10]  # sample only
        stats["contexts"] = dict(stats["contexts"])

    return {
        "domain_stats": domain_stats,
        "brand_site_data": dict(brand_site_data),
    }


def discover_new_trusted(domain_stats: dict, min_refs: int = 5) -> dict:
    """Find domains that should be added to trust config.

    Rules:
    - 5+ refs across different PNs = candidate for tier3
    - 10+ refs + 3+ brands = candidate for tier2
    - Already in trust config = skip
    - In denylist = skip
    """
    trust = load_trust_config()
    denylist = set(trust.get("denylist", []))

    candidates = {"tier2_candidates": [], "tier3_candidates": [], "denylist_candidates": []}

    for domain, stats in domain_stats.items():
        # Skip already trusted
        if stats["current_tier"] != "organic":
            continue

        # Skip denylist patterns
        if any(d in domain for d in denylist):
            continue

        # Skip obvious marketplace/social/CDN
        skip_patterns = ["facebook.", "twitter.", "youtube.", "instagram.",
                         "linkedin.", "pinterest.", "reddit.", "cdn.", "cloudfront.",
                         "googleapis.", "gstatic.", "wp-content", "imgur.",
                         "wikipedia.", "wikimedia."]
        if any(p in domain for p in skip_patterns):
            continue

        pn_count = stats["pn_count"]
        brand_count = stats["brand_count"]

        if pn_count >= 10 and brand_count >= 3:
            candidates["tier2_candidates"].append({
                "domain": domain,
                "pn_count": pn_count,
                "brand_count": brand_count,
                "brands": stats["brands"][:5],
                "field_evidence": stats["field_evidence"],
                "reason": f"{pn_count} refs, {brand_count} brands",
            })
        elif pn_count >= min_refs:
            candidates["tier3_candidates"].append({
                "domain": domain,
                "pn_count": pn_count,
                "brand_count": brand_count,
                "brands": stats["brands"][:5],
                "field_evidence": stats["field_evidence"],
                "reason": f"{pn_count} refs",
            })

    # Sort by ref count
    candidates["tier2_candidates"].sort(key=lambda x: -x["pn_count"])
    candidates["tier3_candidates"].sort(key=lambda x: -x["pn_count"])

    return candidates


def build_brand_site_rating(brand_site_data: dict) -> dict:
    """Build per-brand site rating.

    For each brand, rank sites by field success count.
    """
    rating: dict[str, dict] = {}
    trust = load_trust_config()

    for brand, sites in sorted(brand_site_data.items()):
        brand_entry: dict[str, list] = {
            "best_for_price": [],
            "best_for_photo": [],
            "best_for_specs": [],
            "best_for_datasheet": [],
            "all_sites": [],
        }

        for domain, fields in sorted(sites.items(), key=lambda x: -sum(x[1].values())):
            tier = _classify_tier(domain, trust)
            total = sum(fields.values())
            if total < 1:
                continue

            site_entry = {
                "domain": domain,
                "tier": tier,
                "total_refs": total,
                "fields": dict(fields),
            }
            brand_entry["all_sites"].append(site_entry)

            if fields.get("price", 0) >= 1:
                brand_entry["best_for_price"].append({
                    "domain": domain, "tier": tier,
                    "success_count": fields["price"],
                })
            if fields.get("photo", 0) >= 1:
                brand_entry["best_for_photo"].append({
                    "domain": domain, "tier": tier,
                    "success_count": fields["photo"],
                })
            if fields.get("specs", 0) >= 1:
                brand_entry["best_for_specs"].append({
                    "domain": domain, "tier": tier,
                    "success_count": fields["specs"],
                })
            if fields.get("datasheet", 0) >= 1:
                brand_entry["best_for_datasheet"].append({
                    "domain": domain, "tier": tier,
                    "success_count": fields["datasheet"],
                })

        # Sort each best_for by tier strength then success count
        tier_rank = {"manufacturer_proof": 0, "authorized_distributor": 1,
                     "industrial_distributor": 2, "organic": 3}
        for key in ("best_for_price", "best_for_photo", "best_for_specs", "best_for_datasheet"):
            brand_entry[key].sort(
                key=lambda x: (tier_rank.get(x["tier"], 5), -x["success_count"])
            )

        rating[brand] = brand_entry

    return rating


def update_trust_config(candidates: dict, auto_apply: bool = False) -> int:
    """Update seed_source_trust.json with discovered domains.

    Returns count of domains added.
    """
    if not auto_apply:
        return 0

    trust = load_trust_config()
    added = 0

    for cand in candidates.get("tier2_candidates", []):
        domain = cand["domain"]
        if domain not in trust["authorized_distributor"]:
            trust["authorized_distributor"].append(domain)
            added += 1

    for cand in candidates.get("tier3_candidates", []):
        domain = cand["domain"]
        if domain not in trust["industrial_distributor"]:
            trust["industrial_distributor"].append(domain)
            added += 1

    if added:
        TRUST_CONFIG.write_text(
            json.dumps(trust, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return added


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Trust Discovery from DR results")
    parser.add_argument("--apply", action="store_true", help="Auto-apply to trust config")
    parser.add_argument("--min-refs", type=int, default=5, help="Min refs for tier3 candidate")
    args = parser.parse_args()

    print("=== Trust Discovery: scanning evidence ===")
    data = scan_evidence()
    domain_stats = data["domain_stats"]
    brand_site_data = data["brand_site_data"]

    print(f"  Total domains found: {len(domain_stats)}")
    print(f"  Total brands: {len(brand_site_data)}")

    # Discover new trusted
    candidates = discover_new_trusted(domain_stats, min_refs=args.min_refs)

    print("\n=== New Trusted Domain Candidates ===")
    print("\nTIER 2 candidates (10+ refs, 3+ brands):")
    for c in candidates["tier2_candidates"]:
        fe = c["field_evidence"]
        print(f"  {c['domain']:<40} refs={c['pn_count']:<4} brands={c['brand_count']}  "
              f"price={fe.get('price',0)} photo={fe.get('photo',0)} "
              f"specs={fe.get('specs',0)} ds={fe.get('datasheet',0)}  "
              f"{c['brands']}")

    print(f"\nTIER 3 candidates ({args.min_refs}+ refs):")
    for c in candidates["tier3_candidates"][:20]:
        fe = c["field_evidence"]
        print(f"  {c['domain']:<40} refs={c['pn_count']:<4} brands={c['brand_count']}  "
              f"price={fe.get('price',0)} photo={fe.get('photo',0)} "
              f"specs={fe.get('specs',0)} ds={fe.get('datasheet',0)}  "
              f"{c['brands']}")

    # Build brand site rating
    print("\n=== Brand Site Rating ===")
    rating = build_brand_site_rating(brand_site_data)

    for brand in sorted(rating.keys()):
        entry = rating[brand]
        n_sites = len(entry["all_sites"])
        if n_sites < 2:
            continue
        print(f"\n  {brand} ({n_sites} sites):")
        for field_key, label in [
            ("best_for_price", "price"),
            ("best_for_photo", "photo"),
            ("best_for_specs", "specs"),
            ("best_for_datasheet", "datasheet"),
        ]:
            sites = entry[field_key][:3]
            if sites:
                top = ", ".join(f"{s['domain']}({s['success_count']})" for s in sites)
                print(f"    {label:<12}: {top}")

    # Save results
    DISCOVERY_REPORT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "candidates": candidates,
        "brand_rating_summary": {
            brand: {
                "n_sites": len(e["all_sites"]),
                "best_price": e["best_for_price"][0]["domain"] if e["best_for_price"] else None,
                "best_photo": e["best_for_photo"][0]["domain"] if e["best_for_photo"] else None,
                "best_specs": e["best_for_specs"][0]["domain"] if e["best_for_specs"] else None,
                "best_datasheet": e["best_for_datasheet"][0]["domain"] if e["best_for_datasheet"] else None,
            }
            for brand, e in rating.items()
        },
    }
    DISCOVERY_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Save full brand rating
    BRAND_RATING_FILE.write_text(json.dumps(rating, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n  Report: {DISCOVERY_REPORT}")
    print(f"  Brand rating: {BRAND_RATING_FILE}")

    # Apply if requested
    if args.apply:
        added = update_trust_config(candidates, auto_apply=True)
        print(f"\n  Applied: {added} domains added to trust config")
    else:
        total = len(candidates["tier2_candidates"]) + len(candidates["tier3_candidates"])
        print(f"\n  Dry run. {total} candidates found. Use --apply to update trust config.")


if __name__ == "__main__":
    main()
