"""card_status.py - Phase A deterministic field/card policy layer."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

_CONFIG_DIR = Path(__file__).parent.parent / "config"
_ENUM_PATH = _CONFIG_DIR / "catalog_enum_contract_v1.json"
_POLICY_PATH = _CONFIG_DIR / "catalog_evidence_policy_v1.json"
_FAMILY_POLICY_PATH = _CONFIG_DIR / "family_photo_policy_v1.json"
_SOURCE_MATRIX_PATH = _CONFIG_DIR / "source_role_field_matrix_v1.json"
_REVIEW_SCHEMA_PATH = _CONFIG_DIR / "review_reason_schema_v1.json"

_PUBLISHABLE_PRICE = {"public_price", "rfq_only"}
_PRICE_EXISTS = {"public_price", "rfq_only", "owner_price"}
_STRUCTURED_CONTEXTS = {"jsonld", "title", "h1", "product_context"}
_PDF_IDENTITY_ALLOWED_TIERS = {"official", "authorized"}

_enum_cache: dict | None = None
_policy_cache: dict | None = None
_family_policy_cache: dict | None = None
_source_matrix_cache: dict | None = None
_review_schema_cache: dict | None = None


def load_enum_contract() -> dict:
    global _enum_cache
    if _enum_cache is None:
        with open(_ENUM_PATH, encoding="utf-8") as f:
            _enum_cache = json.load(f)
    return dict(_enum_cache)


def load_catalog_evidence_policy() -> dict:
    global _policy_cache
    if _policy_cache is None:
        with open(_POLICY_PATH, encoding="utf-8") as f:
            _policy_cache = json.load(f)
    return dict(_policy_cache)


def load_family_photo_policy() -> dict:
    global _family_policy_cache
    if _family_policy_cache is None:
        with open(_FAMILY_POLICY_PATH, encoding="utf-8") as f:
            _family_policy_cache = json.load(f)
    return dict(_family_policy_cache)


def load_source_role_field_matrix() -> dict:
    global _source_matrix_cache
    if _source_matrix_cache is None:
        with open(_SOURCE_MATRIX_PATH, encoding="utf-8") as f:
            _source_matrix_cache = json.load(f)
    return dict(_source_matrix_cache)


def load_review_reason_schema() -> dict:
    global _review_schema_cache
    if _review_schema_cache is None:
        with open(_REVIEW_SCHEMA_PATH, encoding="utf-8") as f:
            _review_schema_cache = json.load(f)
    return dict(_review_schema_cache)


_ENUMS = load_enum_contract()
_VALID_FIELD_STATUS = set(_ENUMS["field_status"])
_VALID_CARD_STATUS = set(_ENUMS["card_status"])
_VALID_REASON_CODES = set(_ENUMS["reason_code"])
_VALID_BUCKETS = set(_ENUMS["review_bucket"])
_VALID_IDENTITY = set(_ENUMS["identity_level"])
_VALID_SEVERITY = set(_ENUMS["severity"])
_VALID_PHOTO_STATUS = {"exact_evidence", "family_evidence", "placeholder", "rejected"}


@dataclass(frozen=True)
class CardDecision:
    identity_strength: str
    photo_type: str
    price_status: str
    mismatch: str
    result: str
    rule_id: str
    reason: str
    review_reasons: list[str]


@dataclass(frozen=True)
class ReviewReasonRecord:
    reason_code: str
    field: str
    severity: str
    candidate_ids: list[str]
    evidence_ids: list[str]
    policy_rule_id: str
    bucket: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CardStatusDecisionRecord:
    decision_id: str
    policy_version: str
    family_photo_policy_version: str
    source_matrix_version: str
    review_schema_version: str
    identity_level: str
    title_status: str
    image_status: str
    price_status: str
    pdf_status: str
    card_status: str
    review_reasons: list[ReviewReasonRecord] = field(default_factory=list)
    review_buckets: list[str] = field(default_factory=list)
    policy_rule_id: str = ""

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "policy_version": self.policy_version,
            "family_photo_policy_version": self.family_photo_policy_version,
            "source_matrix_version": self.source_matrix_version,
            "review_schema_version": self.review_schema_version,
            "identity_level": self.identity_level,
            "title_status": self.title_status,
            "image_status": self.image_status,
            "price_status": self.price_status,
            "pdf_status": self.pdf_status,
            "card_status": self.card_status,
            "review_reasons": [r.to_dict() for r in self.review_reasons],
            "review_buckets": self.review_buckets,
            "policy_rule_id": self.policy_rule_id,
        }


def load_decision_table() -> list[dict]:
    """Compatibility loader for simplified Phase A decision rows."""
    return list(load_catalog_evidence_policy().get("card_rules", []))


def calculate_card_status(
    identity_strength: str,
    photo_type: str,
    price_status: str,
    mismatch: str = "none",
) -> CardDecision:
    """Compatibility API backed by catalog_evidence_policy_v1."""
    ident = _normalize_identity(identity_strength)
    photo = _normalize_photo_type(photo_type)
    price = _normalize_price_state(price_status)
    mismatch_norm = _normalize_mismatch(mismatch)

    row = _match_policy_rule(ident, photo, price, mismatch_norm)
    if row is None:
        raise ValueError(
            "No policy rule matched "
            f"identity={ident} photo={photo} price={price} mismatch={mismatch_norm}"
        )

    return CardDecision(
        identity_strength=ident,
        photo_type=photo,
        price_status=price,
        mismatch=mismatch_norm,
        result=row["result"],
        rule_id=row["id"],
        reason=f"{ident}/{photo}/{price}/{mismatch_norm}",
        review_reasons=_derive_simple_review_reasons(ident, photo, price, mismatch_norm),
    )


def card_status_calculator(
    identity_level: str,
    title_signal: Optional[dict] = None,
    image_signal: Optional[dict] = None,
    price_signal: Optional[dict] = None,
    pdf_signal: Optional[dict] = None,
    mismatch: str = "none",
    decision_id: str = "",
) -> CardStatusDecisionRecord:
    """Compute field-level and card-level statuses with replayable review reasons."""
    ident = _normalize_identity(identity_level)
    mismatch_norm = _normalize_mismatch(mismatch)
    title_signal = title_signal or {}
    image_signal = image_signal or {}
    price_signal = price_signal or {}
    pdf_signal = pdf_signal or {}

    title_status = _compute_title_status(title_signal)
    image_status = _compute_image_status(image_signal)
    price_status = _compute_price_status(price_signal)
    pdf_status = _compute_pdf_status(pdf_signal)

    policy = load_catalog_evidence_policy()
    family_policy = load_family_photo_policy()
    source_matrix = load_source_role_field_matrix()
    review_schema = load_review_reason_schema()

    image_state = _image_state_from_status(image_signal, image_status)
    price_state = _price_state_from_signal(price_signal, price_status)
    rule = _match_weak_identity_review_route(
        policy=policy,
        identity_level=ident,
        mismatch=mismatch_norm,
        title_status=title_status,
        image_signal=image_signal,
        image_status=image_status,
        price_signal=price_signal,
        price_status=price_status,
    )
    if rule is None:
        rule = _match_numeric_guard_review_route(
            policy=policy,
            identity_level=ident,
            mismatch=mismatch_norm,
            title_status=title_status,
            image_signal=image_signal,
            image_status=image_status,
            price_signal=price_signal,
            price_status=price_status,
        )
    if rule is None:
        rule = _match_admissible_source_conflict_no_price_route(
            policy=policy,
            identity_level=ident,
            mismatch=mismatch_norm,
            title_status=title_status,
            image_signal=image_signal,
            price_signal=price_signal,
            price_status=price_status,
        )
    if rule is None:
        rule = _match_admissible_source_exact_lineage_no_price_route(
            policy=policy,
            identity_level=ident,
            mismatch=mismatch_norm,
            title_status=title_status,
            image_signal=image_signal,
            price_signal=price_signal,
            price_status=price_status,
        )
    if rule is None:
        rule = _match_terminal_weak_no_price_route(
            policy=policy,
            identity_level=ident,
            mismatch=mismatch_norm,
            title_status=title_status,
            image_signal=image_signal,
            price_signal=price_signal,
            price_status=price_status,
        )
    if rule is None:
        rule = _match_policy_rule(ident, image_state, price_state, mismatch_norm)
    if rule is None:
        raise ValueError(
            "No policy rule matched "
            f"identity={ident} image={image_state} price={price_state} mismatch={mismatch_norm}"
        )

    reasons = _build_review_reasons(
        identity_level=ident,
        mismatch=mismatch_norm,
        title_signal=title_signal,
        title_status=title_status,
        image_signal=image_signal,
        image_status=image_status,
        price_signal=price_signal,
        price_status=price_status,
        pdf_signal=pdf_signal,
        pdf_status=pdf_status,
        policy_rule_id=rule["id"],
        review_bucket_mapping=policy["review_bucket_mapping"],
    )

    decision_ref = decision_id or _make_decision_id(
        {
            "identity_level": ident,
            "title_status": title_status,
            "image_status": image_status,
            "price_status": price_status,
            "pdf_status": pdf_status,
            "card_status": rule["result"],
            "policy_rule_id": rule["id"],
        }
    )

    return CardStatusDecisionRecord(
        decision_id=decision_ref,
        policy_version=policy["policy_version"],
        family_photo_policy_version=family_policy["policy_version"],
        source_matrix_version=source_matrix["matrix_version"],
        review_schema_version=review_schema["schema_version"],
        identity_level=ident,
        title_status=title_status,
        image_status=image_status,
        price_status=price_status,
        pdf_status=pdf_status,
        card_status=rule["result"],
        review_reasons=reasons,
        review_buckets=sorted({r.bucket for r in reasons}),
        policy_rule_id=rule["id"],
    )


def normalize_photo_status(value: str) -> str:
    norm = (value or "").strip().lower()
    if norm not in _VALID_PHOTO_STATUS:
        raise ValueError(f"Unsupported photo_status: {value}")
    return norm


def derive_photo_contract_fields(photo_status: str) -> dict[str, Any]:
    status = normalize_photo_status(photo_status)
    role_map = {
        "exact_evidence": "exact",
        "family_evidence": "family_supporting",
        "placeholder": "merch_only",
        "rejected": "none",
    }
    is_temporary = status == "placeholder"
    return {
        "photo_status": status,
        "photo_evidence_role": role_map[status],
        "photo_is_temporary": is_temporary,
        "replacement_required": is_temporary,
    }


def build_decision_record_v2_from_legacy_inputs(
    pn: str,
    name: str,
    assembled_title: str,
    photo_result: dict,
    vision_verdict: dict,
    price_result: dict,
    datasheet_result: dict,
) -> dict:
    """Compatibility adapter that creates a v2 decision snapshot from legacy data."""
    photo_status = derive_photo_status_from_legacy_inputs(photo_result, vision_verdict)
    title_signal = {
        "derived_title": assembled_title or name,
        "candidate_ids": [f"cand_title_{pn}"],
        "evidence_ids": [f"ev_title_{pn}"],
    }
    image_signal = {
        "photo_status": photo_status,
        "family_photo_allowed": bool(photo_result.get("family_photo_allowed", False)),
        "numeric_keep_guard_applied": bool(photo_result.get("numeric_keep_guard_applied", False)),
        "candidate_ids": [f"cand_image_{pn}"],
        "evidence_ids": [f"ev_image_{pn}"],
    }
    price_signal = {
        "price_status": price_result.get("price_status", "no_price_found"),
        "source_role": _map_legacy_source_role(price_result),
        "exact_pn_confirmed": _legacy_exact_price_confirmed(price_result),
        "exact_product_page": _legacy_exact_price_confirmed(price_result),
        "page_context_clean": not (
            price_result.get("category_mismatch") or price_result.get("brand_mismatch")
        ),
        "price_source_seen": bool(price_result.get("price_source_seen")),
        "price_source_lineage_confirmed": bool(price_result.get("price_source_lineage_confirmed")),
        "price_source_exact_product_lineage_confirmed": bool(price_result.get("price_source_exact_product_lineage_confirmed")),
        "price_source_lineage_reason_code": price_result.get("price_source_lineage_reason_code", ""),
        "price_source_admissible_replacement_confirmed": bool(price_result.get("price_source_admissible_replacement_confirmed")),
        "price_source_terminal_weak_lineage": bool(price_result.get("price_source_terminal_weak_lineage")),
        "price_source_replacement_reason_code": price_result.get("price_source_replacement_reason_code", ""),
        "price_source_surface_conflict_detected": bool(price_result.get("price_source_surface_conflict_detected")),
        "price_source_surface_conflict_reason_code": price_result.get("price_source_surface_conflict_reason_code", ""),
        "reviewable_no_price_candidate": bool(price_result.get("price_reviewable_no_price_candidate")),
        "no_price_reason_code": price_result.get("price_no_price_reason_code", ""),
        "candidate_ids": [f"cand_price_{pn}"],
        "evidence_ids": [f"ev_price_{pn}"],
    }
    pdf_signal = {
        "datasheet_status": datasheet_result.get("datasheet_status", "missing"),
        "source_role": _map_legacy_pdf_source_role(datasheet_result),
        "exact_pn_confirmed": bool(datasheet_result.get("pdf_exact_pn_confirmed")),
        "source_asset_same_as_page": bool(datasheet_result.get("source_asset_same_as_page", False)),
        "candidate_ids": [f"cand_pdf_{pn}"],
        "evidence_ids": [f"ev_pdf_{pn}"],
    }
    decision = card_status_calculator(
        identity_level=_infer_identity_level(photo_result, datasheet_result),
        title_signal=title_signal,
        image_signal=image_signal,
        price_signal=price_signal,
        pdf_signal=pdf_signal,
        mismatch="any_critical" if (
            price_result.get("category_mismatch") or price_result.get("brand_mismatch")
        ) else "none",
        decision_id=f"dec_{pn}",
    )
    return decision.to_dict()


def assign_card_status_legacy(
    photo_verdict: str,
    price_status: str,
    category_mismatch: bool = False,
    brand_mismatch: bool = False,
    stock_photo_flag: bool = False,
) -> tuple[str, list[str]]:
    """Preserve current export behavior until live policy migration is approved."""
    reasons: list[str] = []
    has_good_photo = photo_verdict == "KEEP"
    has_valid_price = price_status in _PUBLISHABLE_PRICE
    has_blocking_mismatch = category_mismatch or brand_mismatch
    has_price_at_all = price_status not in ("no_price_found", "")

    if stock_photo_flag:
        reasons.append("stock_photo_flag")
    if category_mismatch:
        reasons.append("category_mismatch")
    if brand_mismatch:
        reasons.append("brand_mismatch")

    if has_good_photo and has_valid_price and not has_blocking_mismatch:
        return "AUTO_PUBLISH", reasons
    if has_good_photo or (has_valid_price and not has_blocking_mismatch):
        if has_blocking_mismatch:
            reasons.append("mismatch_blocks_publish")
        return "REVIEW_REQUIRED", reasons

    reasons.append(
        "no_photo_and_no_price" if not has_good_photo and not has_price_at_all
        else "photo_rejected_or_missing"
    )
    return "DRAFT_ONLY", reasons


def _compute_title_status(signal: dict) -> str:
    if signal.get("field_status"):
        return _normalize_field_status(signal["field_status"])
    if signal.get("derived_title"):
        return "ACCEPTED"
    return "INSUFFICIENT"


def _compute_image_status(signal: dict) -> str:
    if signal.get("field_status"):
        return _normalize_field_status(signal["field_status"])
    photo_type = _effective_photo_type(signal)
    if photo_type == "exact":
        return "ACCEPTED"
    if photo_type == "family":
        return "REVIEW_REQUIRED" if signal.get("family_photo_allowed") else "REJECTED"
    if photo_type == "unknown":
        return "REVIEW_REQUIRED"
    return "INSUFFICIENT"


def _compute_price_status(signal: dict) -> str:
    if signal.get("field_status"):
        return _normalize_field_status(signal["field_status"])
    price_state = _normalize_price_status(signal.get("price_status", "no_price_found"))
    if price_state == "no_price":
        return "INSUFFICIENT"
    role = signal.get("source_role", "organic_discovery")
    if role not in {"manufacturer_proof", "authorized_distributor", "industrial_distributor"}:
        return "REVIEW_REQUIRED"
    if role == "manufacturer_proof":
        if signal.get("exact_pn_confirmed") and signal.get("exact_product_page") and price_state == "public_price":
            return "ACCEPTED"
        return "REVIEW_REQUIRED"
    if role == "authorized_distributor":
        if (
            signal.get("exact_pn_confirmed")
            and signal.get("exact_product_page")
            and signal.get("page_context_clean", True)
            and price_state in {"public_price", "rfq_only"}
        ):
            return "ACCEPTED"
        return "REVIEW_REQUIRED"
    if role == "industrial_distributor":
        if (
            signal.get("exact_pn_confirmed")
            and signal.get("exact_product_page")
            and signal.get("page_context_clean", True)
            and not signal.get("cross_pollination", False)
            and price_state in {"public_price", "rfq_only"}
        ):
            return "ACCEPTED"
        return "REVIEW_REQUIRED"
    return "REVIEW_REQUIRED"


def _compute_pdf_status(signal: dict) -> str:
    if signal.get("field_status"):
        return _normalize_field_status(signal["field_status"])
    if signal.get("datasheet_status") != "found":
        return "INSUFFICIENT"
    role = signal.get("source_role", "organic_discovery")
    if role in {"manufacturer_proof", "official_pdf_proof"} and signal.get("exact_pn_confirmed"):
        return "ACCEPTED"
    if role == "authorized_distributor":
        if (
            signal.get("exact_pn_confirmed")
            and signal.get("source_asset_same_as_page")
            and signal.get("page_context_clean", True)
        ):
            return "ACCEPTED"
        return "REVIEW_REQUIRED"
    return "REVIEW_REQUIRED"


def _build_review_reasons(
    identity_level: str,
    mismatch: str,
    title_signal: dict,
    title_status: str,
    image_signal: dict,
    image_status: str,
    price_signal: dict,
    price_status: str,
    pdf_signal: dict,
    pdf_status: str,
    policy_rule_id: str,
    review_bucket_mapping: dict,
) -> list[ReviewReasonRecord]:
    reasons: list[ReviewReasonRecord] = []

    def add(reason_code: str, field_name: str, severity: str, signal: dict) -> None:
        if reason_code not in _VALID_REASON_CODES:
            raise ValueError(f"Unsupported reason_code: {reason_code}")
        bucket = review_bucket_mapping[reason_code]
        reasons.append(
            ReviewReasonRecord(
                reason_code=reason_code,
                field=field_name,
                severity=severity,
                candidate_ids=list(signal.get("candidate_ids", [])),
                evidence_ids=list(signal.get("evidence_ids", [])),
                policy_rule_id=policy_rule_id,
                bucket=bucket,
            )
        )

    if identity_level == "medium":
        add("IDENTITY_MEDIUM", "identity", "WARNING", title_signal)
    elif identity_level == "weak":
        add("IDENTITY_WEAK", "identity", "ERROR", title_signal)

    if mismatch == "any_critical":
        add("CRITICAL_MISMATCH", "identity", "ERROR", price_signal or image_signal)

    if title_status == "INSUFFICIENT":
        add("NO_TITLE_EVIDENCE", "title", "INFO", title_signal)

    image_type = _effective_photo_type(image_signal)
    if image_type == "family":
        if image_signal.get("family_photo_allowed"):
            add("FAMILY_PHOTO_POLICY_REVIEW", "image", "WARNING", image_signal)
        else:
            add("FAMILY_PHOTO_POLICY_BLOCK", "image", "ERROR", image_signal)
    elif image_status == "REVIEW_REQUIRED":
        add("IMAGE_UNKNOWN", "image", "WARNING", image_signal)
    elif image_status == "INSUFFICIENT":
        add("NO_IMAGE_EVIDENCE", "image", "INFO", image_signal)

    price_state = _normalize_price_status(price_signal.get("price_status", "no_price_found"))
    if price_status == "INSUFFICIENT":
        if _is_admissible_source_conflict_no_price_case(price_signal):
            add("ADMISSIBLE_SOURCE_NO_PRICE_CONFLICT", "price", "WARNING", price_signal)
        elif _is_admissible_source_exact_lineage_no_price_case(price_signal):
            add("ADMISSIBLE_SOURCE_NO_PRICE_EXACT_LINEAGE", "price", "WARNING", price_signal)
        elif price_signal.get("price_source_terminal_weak_lineage"):
            add("TERMINAL_WEAK_NO_PRICE_LINEAGE", "price", "WARNING", price_signal)
        else:
            add("NO_PRICE_EVIDENCE", "price", "INFO", price_signal)
    elif price_status == "REVIEW_REQUIRED":
        if price_signal.get("source_role") not in {
            "manufacturer_proof",
            "authorized_distributor",
            "industrial_distributor",
        }:
            add("PRICE_ROLE_NOT_ADMISSIBLE", "price", "WARNING", price_signal)
        elif price_state == "public_price":
            add("PUBLIC_PRICE_RESTRICTED", "price", "WARNING", price_signal)

    if pdf_status == "INSUFFICIENT":
        add("NO_PDF_EVIDENCE", "pdf", "INFO", pdf_signal)
    elif pdf_status == "REVIEW_REQUIRED":
        add("PDF_NOT_EXACT_CONFIRMED", "pdf", "WARNING", pdf_signal)

    return reasons


def _is_admissible_source_conflict_no_price_case(price_signal: dict[str, Any]) -> bool:
    replacement_reason = price_signal.get("price_source_replacement_reason_code", "")
    return all(
        (
            price_signal.get("price_source_exact_product_lineage_confirmed", False),
            price_signal.get("price_source_admissible_replacement_confirmed", False),
            not price_signal.get("price_source_terminal_weak_lineage", False),
            replacement_reason in {"source_already_admissible", "admissible_replacement_confirmed"},
            price_signal.get("price_source_surface_conflict_detected", False),
            price_signal.get("price_source_surface_conflict_reason_code", "")
            == "current_surface_conflicts_with_prior",
            not price_signal.get("reviewable_no_price_candidate", False),
        )
    )


def _is_admissible_source_exact_lineage_no_price_case(price_signal: dict[str, Any]) -> bool:
    replacement_reason = price_signal.get("price_source_replacement_reason_code", "")
    return all(
        (
            price_signal.get("price_source_exact_product_lineage_confirmed", False),
            price_signal.get("price_source_admissible_replacement_confirmed", False),
            not price_signal.get("price_source_terminal_weak_lineage", False),
            replacement_reason in {"source_already_admissible", "admissible_replacement_confirmed"},
            not price_signal.get("price_source_surface_conflict_detected", False),
            not price_signal.get("reviewable_no_price_candidate", False),
        )
    )


def _match_weak_identity_review_route(
    *,
    policy: dict,
    identity_level: str,
    mismatch: str,
    title_status: str,
    image_signal: dict,
    image_status: str,
    price_signal: dict,
    price_status: str,
) -> Optional[dict]:
    route = policy.get("weak_identity_review_route", {})
    if not route:
        return None
    if not policy.get("ambiguity_rules", {}).get("weak_identity_clean_review_route_enabled"):
        return None
    if identity_level != "weak" or mismatch != "none":
        return None

    requires = route.get("requires", {})
    if title_status != requires.get("title_status", "ACCEPTED"):
        return None
    if image_status != requires.get("image_status", "INSUFFICIENT"):
        return None
    if price_status != requires.get("price_status", "ACCEPTED"):
        return None
    if not price_signal.get("page_context_clean", False):
        return None
    if not price_signal.get("exact_product_page", False):
        return None
    if image_signal.get("numeric_keep_guard_applied", False):
        return None

    photo_type = _effective_photo_type(image_signal)
    if photo_type == "family" or image_signal.get("family_photo_allowed"):
        return None

    return {
        "id": route["policy_rule_id"],
        "result": route["result"],
    }


def _match_admissible_source_conflict_no_price_route(
    *,
    policy: dict,
    identity_level: str,
    mismatch: str,
    title_status: str,
    image_signal: dict,
    price_signal: dict,
    price_status: str,
) -> Optional[dict]:
    route = policy.get("admissible_source_conflict_no_price_route", {})
    if not route:
        return None
    if not policy.get("ambiguity_rules", {}).get("admissible_source_conflict_no_price_disposition_enabled"):
        return None
    if identity_level != "weak" or mismatch != "none":
        return None

    requires = route.get("requires", {})
    if title_status != requires.get("title_status", "ACCEPTED"):
        return None
    if price_status != requires.get("price_status", "INSUFFICIENT"):
        return None
    if not _is_admissible_source_conflict_no_price_case(price_signal):
        return None

    photo_type = _effective_photo_type(image_signal)
    if photo_type == "family" or image_signal.get("family_photo_allowed"):
        return None

    return {
        "id": route["policy_rule_id"],
        "result": route["result"],
    }


def _match_admissible_source_exact_lineage_no_price_route(
    *,
    policy: dict,
    identity_level: str,
    mismatch: str,
    title_status: str,
    image_signal: dict,
    price_signal: dict,
    price_status: str,
) -> Optional[dict]:
    route = policy.get("admissible_source_exact_lineage_no_price_route", {})
    if not route:
        return None
    if not policy.get("ambiguity_rules", {}).get("admissible_source_exact_lineage_no_price_disposition_enabled"):
        return None
    if identity_level != "weak" or mismatch != "none":
        return None

    requires = route.get("requires", {})
    if title_status != requires.get("title_status", "ACCEPTED"):
        return None
    if price_status != requires.get("price_status", "INSUFFICIENT"):
        return None
    if not _is_admissible_source_exact_lineage_no_price_case(price_signal):
        return None

    photo_type = _effective_photo_type(image_signal)
    if photo_type == "family" or image_signal.get("family_photo_allowed"):
        return None

    return {
        "id": route["policy_rule_id"],
        "result": route["result"],
    }


def _match_numeric_guard_review_route(
    *,
    policy: dict,
    identity_level: str,
    mismatch: str,
    title_status: str,
    image_signal: dict,
    image_status: str,
    price_signal: dict,
    price_status: str,
) -> Optional[dict]:
    route = policy.get("numeric_guard_review_route", {})
    if not route:
        return None
    if not policy.get("ambiguity_rules", {}).get("numeric_guarded_review_route_enabled"):
        return None
    if identity_level != "weak" or mismatch != "none":
        return None

    requires = route.get("requires", {})
    if title_status != requires.get("title_status", "ACCEPTED"):
        return None
    if image_status != requires.get("image_status", "INSUFFICIENT"):
        return None
    if price_status != requires.get("price_status", "ACCEPTED"):
        return None
    if not price_signal.get("page_context_clean", False):
        return None
    if not price_signal.get("exact_product_page", False):
        return None
    if not image_signal.get("numeric_keep_guard_applied", False):
        return None

    photo_type = _effective_photo_type(image_signal)
    if photo_type == "family" or image_signal.get("family_photo_allowed"):
        return None

    return {
        "id": route["policy_rule_id"],
        "result": route["result"],
    }


def _match_terminal_weak_no_price_route(
    *,
    policy: dict,
    identity_level: str,
    mismatch: str,
    title_status: str,
    image_signal: dict,
    price_signal: dict,
    price_status: str,
) -> Optional[dict]:
    route = policy.get("terminal_weak_no_price_route", {})
    if not route:
        return None
    if not policy.get("ambiguity_rules", {}).get("terminal_weak_no_price_disposition_enabled"):
        return None
    if identity_level != "weak" or mismatch != "none":
        return None

    requires = route.get("requires", {})
    if title_status != requires.get("title_status", "ACCEPTED"):
        return None
    if price_status != requires.get("price_status", "INSUFFICIENT"):
        return None
    if not price_signal.get("price_source_exact_product_lineage_confirmed", False):
        return None
    if price_signal.get("price_source_admissible_replacement_confirmed", False):
        return None
    if not price_signal.get("price_source_terminal_weak_lineage", False):
        return None
    if price_signal.get("reviewable_no_price_candidate", False):
        return None

    photo_type = _effective_photo_type(image_signal)
    if photo_type == "family" or image_signal.get("family_photo_allowed"):
        return None

    return {
        "id": route["policy_rule_id"],
        "result": route["result"],
    }


def _match_policy_rule(identity_level: str, image_state: str, price_state: str, mismatch: str) -> Optional[dict]:
    for row in load_decision_table():
        if not _rule_matches(row["identity_level"], identity_level):
            continue
        if not _rule_matches(row["image_state"], image_state):
            continue
        if not _rule_matches(row["price_state"], price_state):
            continue
        if not _rule_matches(row["mismatch"], mismatch):
            continue
        return row
    return None


def _rule_matches(rule_value: str, actual: str) -> bool:
    return rule_value == "any" or rule_value == actual


def _normalize_identity(value: str) -> str:
    norm = (value or "").strip().lower()
    if norm not in _VALID_IDENTITY:
        raise ValueError(f"Unsupported identity_level: {value}")
    return norm


def _normalize_photo_type(value: str) -> str:
    norm = (value or "").strip().lower()
    aliases = {"exact_photo": "exact", "family_photo": "family", "no_photo": "none"}
    norm = aliases.get(norm, norm)
    if norm not in {"exact", "family", "unknown", "none"}:
        raise ValueError(f"Unsupported photo_type: {value}")
    return norm


def _effective_photo_type(signal: dict) -> str:
    raw_status = signal.get("photo_status")
    if raw_status:
        status = normalize_photo_status(str(raw_status))
        return {
            "exact_evidence": "exact",
            "family_evidence": "family",
            "placeholder": "none",
            "rejected": "none",
        }[status]
    return _normalize_photo_type(signal.get("photo_type", "unknown"))


def _normalize_price_status(value: str) -> str:
    norm = (value or "").strip().lower()
    aliases = {
        "hidden_price": "no_price",
        "ambiguous_offer": "no_price",
        "ambiguous_unit": "no_price",
        "category_mismatch_only": "no_price",
        "brand_mismatch_only": "no_price",
        "no_price_found": "no_price",
        "": "no_price",
    }
    norm = aliases.get(norm, norm)
    # owner_price is mapped to rfq_only for policy matching:
    # it counts as "has price" (→ REVIEW_REQUIRED) but not as publishable market price
    if norm == "owner_price":
        return "rfq_only"
    if norm not in {"public_price", "rfq_only", "no_price"}:
        raise ValueError(f"Unsupported price_status: {value}")
    return norm


def _normalize_price_state(value: str) -> str:
    return _normalize_price_status(value)


def _normalize_mismatch(value: str) -> str:
    norm = (value or "").strip().lower()
    if norm not in {"none", "any_critical"}:
        raise ValueError(f"Unsupported mismatch: {value}")
    return norm


def _normalize_field_status(value: str) -> str:
    norm = (value or "").strip().upper()
    if norm not in _VALID_FIELD_STATUS:
        raise ValueError(f"Unsupported field_status: {value}")
    return norm


def _image_state_from_status(signal: dict, status: str) -> str:
    if status == "ACCEPTED":
        return "exact"
    photo_type = _effective_photo_type(signal)
    if photo_type == "family":
        return "family"
    if status == "INSUFFICIENT":
        return "none"
    return "unknown"


def _price_state_from_signal(signal: dict, status: str) -> str:
    if status == "INSUFFICIENT":
        return "no_price"
    return _normalize_price_status(signal.get("price_status", "no_price_found"))


def _make_decision_id(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return "dec_" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _derive_simple_review_reasons(
    identity_strength: str,
    photo_type: str,
    price_status: str,
    mismatch: str,
) -> list[str]:
    reasons: list[str] = []
    if mismatch == "any_critical":
        reasons.append("critical_mismatch")
    if identity_strength == "medium":
        reasons.append("identity_medium")
    elif identity_strength == "weak":
        reasons.append("identity_weak")
    if photo_type == "family":
        reasons.append("family_photo")
    elif photo_type == "unknown":
        reasons.append("photo_unknown")
    elif photo_type == "none":
        reasons.append("no_photo")
    if price_status == "no_price":
        reasons.append("no_price")
    return reasons


def _infer_identity_level(photo_result: dict, datasheet_result: dict) -> str:
    # Prefer explicit structured match flags from extract_structured_pn_flags()
    if photo_result.get("exact_structured_pn_match"):
        return "strong"
    struct_loc = str(photo_result.get("structured_pn_match_location", "")).strip().lower()
    # Strip suffix-variant suffix so "title_suffix_variant" still maps to "title"
    base_struct_loc = struct_loc.split("_suffix_variant")[0]
    if base_struct_loc in _STRUCTURED_CONTEXTS:
        return "strong"
    # Legacy fallback: pn_match_location from PNMatchResult (alphanumeric body matches)
    location = str(photo_result.get("pn_match_location", "")).strip().lower()
    if location in _STRUCTURED_CONTEXTS or _has_exact_pdf_identity_evidence(datasheet_result):
        return "strong"
    if location == "body":
        return "medium"
    return "weak"


def _has_exact_pdf_identity_evidence(datasheet_result: dict) -> bool:
    if bool(datasheet_result.get("pdf_exact_pn_confirmed")):
        return True

    datasheet_status = str(datasheet_result.get("datasheet_status", "")).strip().lower()
    pdf_source_tier = str(datasheet_result.get("pdf_source_tier", "")).strip().lower()
    pn_confirmed_in_pdf = bool(datasheet_result.get("pn_confirmed_in_pdf"))

    # Only explicit exact-PN confirmation can upgrade identity from legacy PDF data.
    return (
        pn_confirmed_in_pdf
        and datasheet_status == "found"
        and pdf_source_tier in _PDF_IDENTITY_ALLOWED_TIERS
    )


def _infer_legacy_photo_type(photo_result: dict, vision_verdict: dict) -> str:
    if vision_verdict.get("verdict") != "KEEP":
        return "none"
    if photo_result.get("photo_type"):
        return _normalize_photo_type(photo_result["photo_type"])
    if photo_result.get("stock_photo_flag"):
        return "family"
    if photo_result.get("mpn_confirmed") or photo_result.get("pn_match_location") in _STRUCTURED_CONTEXTS:
        return "exact"
    return "unknown"


def derive_photo_status_from_legacy_inputs(photo_result: dict | None, vision_verdict: dict | None) -> str:
    photo_result = dict(photo_result or {})
    vision_verdict = dict(vision_verdict or {})

    if photo_result.get("photo_status"):
        return normalize_photo_status(str(photo_result["photo_status"]))

    legacy_type = _infer_legacy_photo_type(photo_result, vision_verdict)
    if legacy_type == "exact":
        return "exact_evidence"
    if legacy_type == "family":
        return "family_evidence"
    if vision_verdict.get("verdict") == "KEEP":
        return "placeholder"
    return "rejected"


def _legacy_exact_price_confirmed(price_result: dict) -> bool:
    if price_result.get("category_mismatch") or price_result.get("brand_mismatch"):
        return False
    if price_result.get("suffix_conflict"):
        return False
    return price_result.get("price_status") in {"public_price", "rfq_only"}


def _map_legacy_source_role(price_result: dict) -> str:
    tier = (price_result.get("source_tier") or "").strip().lower()
    if tier == "official":
        return "manufacturer_proof"
    if tier == "authorized":
        return "authorized_distributor"
    if tier in {"industrial", "ru_b2b"}:
        return "industrial_distributor"
    return "organic_discovery"


def _map_legacy_pdf_source_role(datasheet_result: dict) -> str:
    if datasheet_result.get("source_role"):
        return datasheet_result["source_role"]
    return "official_pdf_proof" if datasheet_result.get("datasheet_status") == "found" else "organic_discovery"
