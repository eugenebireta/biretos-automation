"""Pipeline v2 identity utilities — hash computation, PN normalization, re-bind check.

Source of truth: docs/PIPELINE_ARCHITECTURE_v2.md sections 4, 5.
"""
from __future__ import annotations

import hashlib
import re

from .enums import (
    BrandMatch,
    FieldAdmissibility,
    PageType,
    PNMatch,
    SourceTier,
)
from .models import (
    FieldAdmissibilityRecord,
    IdentityCapsule,
)


# ── Identity Hash ───────────────────────────────────────────────────────────


def compute_identity_hash(confirmed_brand: str, normalized_pn: str,
                          manufacturer_namespace: str) -> str:
    """Compute identity_hash = sha256(brand|pn|namespace).

    Does NOT include product_type, series, EAN, or version.
    """
    identity_key = f"{confirmed_brand}|{normalized_pn}|{manufacturer_namespace}"
    return hashlib.sha256(identity_key.encode("utf-8")).hexdigest()


def compute_identity_key(confirmed_brand: str, normalized_pn: str,
                         manufacturer_namespace: str) -> str:
    """Human-readable identity key."""
    return f"{confirmed_brand}|{normalized_pn}|{manufacturer_namespace}"


def verify_identity_hash(capsule: IdentityCapsule) -> bool:
    """Verify that capsule's identity_hash matches its fields.

    Returns True if hash is consistent, False if corrupted/tampered.
    """
    expected = compute_identity_hash(
        capsule.confirmed_brand,
        capsule.normalized_pn,
        capsule.manufacturer_namespace,
    )
    return capsule.identity_hash == expected


# ── PN Normalization ────────────────────────────────────────────────────────

# Known suffixes that don't change product identity
_STRIP_SUFFIXES = re.compile(
    r"[-/](BLK|WHT|BEI|CRM|GRY|RED|BLU|GRN|YEL|ANT)"  # color codes
    r"|[-/](Dialog|DIALOG|AURA|NOVA)"  # series names as suffix
    r"|\.10$|\.20$|\.30$"  # PEHA color suffixes
    r"|-RU$|-EU$|-US$|-UK$|-CN$"  # region codes
    r"|-L[0-9]$"  # kit/level codes
    , re.IGNORECASE
)


def normalize_pn(raw_pn: str, brand_prefix: str | None = None) -> str:
    """Normalize a part number for comparison.

    Steps per spec section 5, step 1:
    1. Strip brand prefix if matches confirmed brand
    2. Strip known non-identity suffixes
    3. Strip leading zeros
    4. Strip special characters (- / . space)
    5. Lowercase

    Note: brand names are never valid PNs in our catalog.
    If raw_pn equals brand_prefix exactly, it passes through unchanged.
    """
    pn = raw_pn.strip()
    if not pn:
        return ""

    # Step 1: Strip brand prefix (only if followed by separator)
    if brand_prefix:
        prefix = brand_prefix.upper().replace(" ", "")
        pn_upper = pn.upper().replace(" ", "")
        if pn_upper != prefix:  # guard: don't strip if PN IS the brand
            if pn_upper.startswith(prefix + "-") or pn_upper.startswith(prefix + "_"):
                pn = pn[len(prefix) + 1:]
            elif pn_upper.startswith(prefix):
                rest = pn[len(prefix):]
                if rest and not rest[0].isalnum():
                    pn = rest.lstrip("-_ ")

    # Step 2: Strip known suffixes
    pn = _STRIP_SUFFIXES.sub("", pn)

    # Step 3: Strip leading zeros (but keep at least 1 char)
    stripped = pn.lstrip("0")
    if stripped:
        pn = stripped

    # Step 4: Strip special characters
    pn = re.sub(r"[-/.\s]", "", pn)

    # Step 5: Lowercase
    pn = pn.lower()

    return pn


def strip_all(pn: str) -> str:
    """Strip ALL non-alphanumeric characters for fuzzy comparison.

    Handles both ASCII and Unicode (Cyrillic etc).
    """
    return re.sub(r"[^\w\d]", "", pn, flags=re.UNICODE).lower()


def normalize_brand(raw_brand: str) -> str:
    """Normalize brand name for comparison. Returns UPPERCASE by convention."""
    return raw_brand.strip().upper().replace(".", "").replace(",", "")


# ── Re-bind Check ──────────────────────────────────────────────────────────

# Page types that can provide content evidence (spec section 5)
_CONTENT_PAGE_TYPES = {
    PageType.PRODUCT_PAGE,
    PageType.DATASHEET,
    PageType.CATALOG_PAGE,
}


class ReBindResult:
    """Result of re-bind check."""

    def __init__(self, bound: bool, reason: str,
                 pn_match: PNMatch = PNMatch.ABSENT,
                 brand_match: BrandMatch = BrandMatch.ABSENT,
                 field_admissibility: FieldAdmissibilityRecord | None = None,
                 pack_qty: int | None = None,
                 pack_price_detected: bool = False):
        self.bound = bound
        self.reason = reason
        self.pn_match = pn_match
        self.brand_match = brand_match
        self.field_admissibility = field_admissibility or FieldAdmissibilityRecord()
        self.pack_qty = pack_qty
        self.pack_price_detected = pack_price_detected


# Pack signal patterns (from price_unit_judge + KNOW_HOW Conrad/computersalg)
_PACK_PATTERNS = re.compile(
    r"\b(\d{1,3})\s*(st|stk|stck|stuck|pcs|pieces|pack|er[\s-]?pack|set)\b"
    r"|\bpack\s+of\s+(\d{1,3})\b"
    r"|\b(\d{1,3})[\s-]?er\b",
    re.IGNORECASE,
)


def re_bind_check(
    extracted_pn: str | None,
    extracted_brand: str | None,
    extracted_product_type: str | None,
    page_type: PageType,
    source_tier: SourceTier,
    negative_evidence: list[str],
    context_text: str,
    capsule: IdentityCapsule,
) -> ReBindResult:
    """Execute re-bind check per Architecture spec section 5.

    All 7 steps implemented:
    1. Normalize
    2. Hard veto (negative evidence, forbidden pages, denylist, product_type conflict)
    3. PN match
    4. Brand match
    5. Pack detection
    6. Field admissibility
    7. Bind
    """

    # ── Step 2: HARD VETO ──
    if negative_evidence:
        return ReBindResult(False, f"veto:negative_evidence:{negative_evidence[0]}")

    if page_type in capsule.capsule_constraints.forbidden_page_types:
        return ReBindResult(False, f"veto:forbidden_page_type:{page_type.value}")

    if source_tier == SourceTier.DENYLIST:
        return ReBindResult(False, "veto:denylist_source")

    # Product type conflict check (CRITICAL-2 fix)
    if extracted_product_type and capsule.product_type:
        if _is_product_type_conflict(extracted_product_type, capsule.product_type):
            return ReBindResult(False,
                                f"veto:product_type_conflict:{extracted_product_type}_vs_{capsule.product_type}")

    # ── Step 1+3: NORMALIZE + PN MATCH ──
    if not extracted_pn or not extracted_pn.strip():
        return ReBindResult(False, "reject:pn_absent")

    norm_extracted = normalize_pn(extracted_pn, capsule.confirmed_brand)
    norm_capsule = capsule.normalized_pn

    pn_match_result: PNMatch
    if norm_extracted == norm_capsule:
        pn_match_result = PNMatch.EXACT
    elif norm_extracted in [normalize_pn(a, capsule.confirmed_brand)
                            for a in capsule.allowed_pn_aliases]:
        pn_match_result = PNMatch.ALIAS
    elif strip_all(extracted_pn) == strip_all(capsule.confirmed_pn):
        pn_match_result = PNMatch.NORMALIZED
    else:
        return ReBindResult(False, f"reject:pn_mismatch:{extracted_pn}",
                            pn_match=PNMatch.MISMATCH)

    # ── Step 4: BRAND MATCH ──
    brand_match_result: BrandMatch
    if extracted_brand and extracted_brand.strip():
        norm_brand_ext = normalize_brand(extracted_brand)
        norm_brand_cap = normalize_brand(capsule.confirmed_brand)

        if norm_brand_ext == norm_brand_cap:
            brand_match_result = BrandMatch.EXACT
        elif norm_brand_ext in [normalize_brand(a)
                                for a in capsule.allowed_brand_aliases]:
            brand_match_result = BrandMatch.ALIAS
        else:
            return ReBindResult(False, f"reject:brand_mismatch:{extracted_brand}",
                                pn_match=pn_match_result,
                                brand_match=BrandMatch.MISMATCH)
    else:
        # Brand absent on page — OK if PN exact, otherwise ambiguous
        brand_match_result = BrandMatch.ABSENT

    # ── Step 5: PACK DETECTION ──
    pack_qty = None
    pack_price_detected = False
    pack_match = _PACK_PATTERNS.search(context_text)
    if pack_match:
        for g in pack_match.groups():
            if g and g.isdigit():
                qty = int(g)
                if 2 <= qty <= 100:  # reasonable pack size bounds
                    pack_qty = qty
                    pack_price_detected = True
                break

    # ── Step 6: FIELD ADMISSIBILITY ──
    min_tier = capsule.capsule_constraints.min_source_tier_for_price
    tier_order = [SourceTier.MANUFACTURER_PROOF, SourceTier.AUTHORIZED_DISTRIBUTOR,
                  SourceTier.INDUSTRIAL_DISTRIBUTOR, SourceTier.ORGANIC_DISCOVERY]
    source_idx = tier_order.index(source_tier) if source_tier in tier_order else 99
    min_idx = tier_order.index(min_tier) if min_tier in tier_order else 0

    price_admitted = FieldAdmissibility.ADMITTED if source_idx <= min_idx else FieldAdmissibility.NOT_ADMITTED
    # Override: if pack detected, price still admitted but flagged
    if pack_price_detected and price_admitted == FieldAdmissibility.ADMITTED:
        price_admitted = FieldAdmissibility.ADMITTED  # builder will use pack_qty to divide

    is_content_page = page_type in _CONTENT_PAGE_TYPES
    photo_admitted = FieldAdmissibility.ADMITTED if is_content_page else FieldAdmissibility.NOT_ADMITTED
    desc_admitted = FieldAdmissibility.ADMITTED if is_content_page else FieldAdmissibility.NOT_ADMITTED
    specs_admitted = FieldAdmissibility.ADMITTED if is_content_page else FieldAdmissibility.NOT_ADMITTED

    admissibility = FieldAdmissibilityRecord(
        price=price_admitted,
        photo=photo_admitted,
        description=desc_admitted,
        specs=specs_admitted,
    )

    # ── Step 7: BIND ──
    reason_parts = [pn_match_result.value, brand_match_result.value]
    if pack_price_detected:
        reason_parts.append(f"pack_qty={pack_qty}")

    return ReBindResult(
        bound=True,
        reason="+".join(reason_parts),
        pn_match=pn_match_result,
        brand_match=brand_match_result,
        field_admissibility=admissibility,
        pack_qty=pack_qty,
        pack_price_detected=pack_price_detected,
    )


# ── Product Type Conflict Detection ────────────────────────────────────────

# Hard conflict pairs: if capsule says X and evidence says Y, it's definitely wrong
_HARD_CONFLICTS = [
    ({"switch", "switch_cover", "frame", "socket", "dimmer"},
     {"filter", "relay", "valve", "sensor", "controller", "pump", "motor",
      "aircraft", "cockpit", "aviation"}),
    ({"valve", "actuator"},
     {"switch", "frame", "socket", "lamp", "cable", "aircraft", "cockpit"}),
    ({"sensor", "detector", "thermostat"},
     {"frame", "socket", "lamp", "cable", "filter", "aircraft", "cockpit"}),
    ({"cable", "wire", "connector"},
     {"valve", "switch", "sensor", "pump", "aircraft", "cockpit"}),
    ({"cabinet", "enclosure", "server_cabinet", "rack"},
     {"aircraft", "cockpit", "aviation", "filter", "lamp", "cable", "pump"}),
    ({"aircraft", "cockpit", "aviation"},
     {"switch_cover", "frame", "socket", "valve", "sensor", "cable",
      "cabinet", "enclosure", "server_cabinet", "rack", "thermostat"}),
]


def _is_product_type_conflict(type_a: str, type_b: str) -> bool:
    """Check if two product types are hard-conflicting.

    Product type is an anti-hallucination filter (spec section 4):
    - "frame" vs "aircraft filter" = hard reject
    - "frame" vs "decor frame" = OK
    - unknown type = no conflict
    """
    a = type_a.lower().strip()
    b = type_b.lower().strip()

    if a == b:
        return False

    for group1, group2 in _HARD_CONFLICTS:
        a_in_1 = any(k in a for k in group1)
        a_in_2 = any(k in a for k in group2)
        b_in_1 = any(k in b for k in group1)
        b_in_2 = any(k in b for k in group2)

        if (a_in_1 and b_in_2) or (a_in_2 and b_in_1):
            return True

    return False
