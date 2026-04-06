import json
import sys
from pathlib import Path


_scripts = Path(__file__).resolve().parents[2] / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from build_catalog_followup_queues import run


def test_build_catalog_followup_queues_splits_photo_and_price_followups(tmp_path):
    evidence_dir = tmp_path / "evidence"
    output_dir = tmp_path / "queues"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    reject_bundle = {
        "pn": "010130.10",
        "name": "Module",
        "brand": "Honeywell",
        "card_status": "REVIEW_REQUIRED",
        "photo": {"verdict": "REJECT", "verdict_reason": "wrong image"},
        "merchandising": {"image_status": "rejected", "image_local_path": ""},
        "price": {"price_status": "public_price", "source_url": "https://example.com/module"},
        "content": {"site_placement": "Каталог/Системы безопасности", "product_type": "Модуль", "description_source": "seed"},
    }
    price_gap_bundle = {
        "pn": "1011994",
        "name": "Earmuff",
        "brand": "Honeywell",
        "card_status": "REVIEW_REQUIRED",
        "photo": {"verdict": "KEEP"},
        "merchandising": {"image_status": "placeholder", "image_local_path": "D:/tmp/example.jpg"},
        "price": {"price_status": "no_price_found", "source_url": ""},
        "content": {"site_placement": "Каталог/СИЗ", "product_type": "Наушники", "description_source": "seed"},
    }
    (evidence_dir / "evidence_010130.10.json").write_text(json.dumps(reject_bundle, ensure_ascii=False), encoding="utf-8")
    (evidence_dir / "evidence_1011994.json").write_text(json.dumps(price_gap_bundle, ensure_ascii=False), encoding="utf-8")

    summary = run(evidence_dir=evidence_dir, output_dir=output_dir, prefix="test")

    assert summary["source_bundle_count"] == 2
    assert summary["photo_recovery_count"] == 1
    assert summary["price_followup_count"] == 1
    assert summary["queue_schema_version"] == "followup_queue_v2"
    assert summary["snapshot_id"].startswith("snap_")
    assert summary["source_evidence_fingerprint"].startswith("sha256:")
    assert summary["photo_recovery_queue_path"] == summary["photo_recovery_queue"]
    assert summary["price_followup_queue_path"] == summary["price_followup_queue"]

    photo_rows = [json.loads(line) for line in Path(summary["photo_recovery_queue"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    price_rows = [json.loads(line) for line in Path(summary["price_followup_queue"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    assert photo_rows[0]["pn"] == "010130.10"
    assert photo_rows[0]["part_number"] == "010130.10"
    assert photo_rows[0]["action_code"] == "photo_recovery"
    assert photo_rows[0]["snapshot_id"] == summary["snapshot_id"]
    assert photo_rows[0]["queue_schema_version"] == "followup_queue_v2"
    assert photo_rows[0]["suggested_action"] == "find_replacement_photo_from_trusted_source"
    assert price_rows[0]["pn"] == "1011994"
    assert price_rows[0]["part_number"] == "1011994"
    assert price_rows[0]["action_code"] == "scout_price"
    assert price_rows[0]["snapshot_id"] == summary["snapshot_id"]
    assert price_rows[0]["queue_schema_version"] == "followup_queue_v2"
    assert price_rows[0]["suggested_action"] == "find_admissible_price_source_or_confirm_no_price"


def test_build_catalog_followup_queues_uses_admissibility_verdicts(tmp_path):
    evidence_dir = tmp_path / "evidence"
    output_dir = tmp_path / "queues"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    bundles = [
        {
            "pn": "GOOD-1",
            "name": "Good",
            "brand": "Honeywell",
            "card_status": "REVIEW_REQUIRED",
            "photo": {"verdict": "KEEP"},
            "price": {
                "price_status": "public_price",
                "offer_admissibility_status": "admissible_public_price",
                "staleness_or_conflict_status": "clean",
                "price_per_unit": 9.95,
                "currency": "USD",
                "offer_qty": 1,
                "offer_unit_basis": "piece",
                "http_status": 200,
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_lineage_reason_code": "structured_exact_product_page",
                "price_source_clean_product_page": True,
                "page_product_class": "product",
                "source_url": "https://example.com/good",
            },
            "content": {},
        },
        {
            "pn": "101411-SEMANTIC",
            "name": "Frame",
            "brand": "Honeywell",
            "card_status": "REVIEW_REQUIRED",
            "photo": {"verdict": "KEEP"},
            "price": {
                "price_status": "public_price",
                "offer_admissibility_status": "ambiguous_offer",
                "string_lineage_status": "exact",
                "commercial_identity_status": "component_or_accessory",
                "staleness_or_conflict_status": "clean",
                "price_admissibility_reason_codes": ["PRICE_COMPONENT_OR_ACCESSORY"],
                "price_admissibility_review_bucket": "PRICE_ADMISSIBILITY_REVIEW",
                "source_url": "https://example.com/frame",
            },
            "content": {},
        },
        {
            "pn": "1011894-RU",
            "name": "Blocked",
            "brand": "Honeywell",
            "card_status": "REVIEW_REQUIRED",
            "photo": {"verdict": "KEEP"},
            "price": {
                "price_status": "no_price_found",
                "offer_admissibility_status": "blocked_or_auth_gated",
                "http_status": 403,
                "blocked_ui_detected": True,
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_lineage_reason_code": "structured_exact_product_page_weak_tier",
                "staleness_or_conflict_status": "clean",
                "price_admissibility_reason_codes": ["PRICE_BLOCKED_OR_AUTH_GATED"],
                "price_admissibility_review_bucket": "PRICE_BLOCKED_SURFACE",
                "source_url": "https://example.com/blocked",
            },
            "content": {},
        },
        {
            "pn": "104011",
            "name": "Stale",
            "brand": "Honeywell",
            "card_status": "REVIEW_REQUIRED",
            "photo": {"verdict": "KEEP"},
            "price": {
                "price_status": "no_price_found",
                "offer_admissibility_status": "ambiguous_offer",
                "string_lineage_status": "exact",
                "commercial_identity_status": "component_or_accessory",
                "staleness_or_conflict_status": "stale_historical_claim",
                "price_admissibility_reason_codes": ["PRICE_STALE_HISTORICAL_CLAIM"],
                "price_admissibility_review_bucket": "STALE_TRUTH_REVIEW",
                "source_url": "https://example.com/stale",
            },
            "content": {},
        },
        {
            "pn": "NO-PRICE-1",
            "name": "No price",
            "brand": "Honeywell",
            "card_status": "REVIEW_REQUIRED",
            "photo": {"verdict": "KEEP"},
            "price": {
                "price_status": "no_price_found",
                "offer_admissibility_status": "no_price_found",
                "string_lineage_status": "exact",
                "commercial_identity_status": "exact_product",
                "staleness_or_conflict_status": "clean",
                "source_url": "https://example.com/no-price",
            },
            "content": {},
        },
        {
            "pn": "101411",
            "name": "Semantic no-price",
            "brand": "Honeywell",
            "card_status": "REVIEW_REQUIRED",
            "photo": {"verdict": "KEEP"},
            "price": {
                "price_status": "no_price_found",
                "offer_admissibility_status": "no_price_found",
                "price_source_seen": True,
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_lineage_reason_code": "structured_exact_product_page",
                "price_source_clean_product_page": True,
                "page_product_class": "PEHA cover frame switchgear",
                "staleness_or_conflict_status": "clean",
                "price_admissibility_reason_codes": ["PRICE_COMPONENT_OR_ACCESSORY"],
                "price_admissibility_review_bucket": "PRICE_ADMISSIBILITY_REVIEW",
                "source_url": "https://example.com/semantic-no-price",
            },
            "content": {},
        },
    ]
    for bundle in bundles:
        (evidence_dir / f"evidence_{bundle['pn']}.json").write_text(
            json.dumps(bundle, ensure_ascii=False),
            encoding="utf-8",
        )

    summary = run(evidence_dir=evidence_dir, output_dir=output_dir, prefix="admissibility")

    price_rows = [
        json.loads(line)
        for line in Path(summary["price_followup_queue"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    row_by_pn = {row["part_number"]: row for row in price_rows}

    assert summary["price_followup_count"] == 5
    assert "GOOD-1" not in row_by_pn
    assert row_by_pn["101411-SEMANTIC"]["offer_admissibility_status"] == "ambiguous_offer"
    assert row_by_pn["101411-SEMANTIC"]["action_code"] == "admissibility_review"
    assert row_by_pn["101411-SEMANTIC"]["suggested_action"] == "review_ambiguous_offer_for_admissibility"
    assert row_by_pn["1011894-RU"]["offer_admissibility_status"] == "blocked_or_auth_gated"
    assert row_by_pn["1011894-RU"]["action_code"] == "admissibility_review"
    assert row_by_pn["1011894-RU"]["suggested_action"] == "review_blocked_surface_with_semantic_barrier"
    assert row_by_pn["104011"]["staleness_or_conflict_status"] == "stale_historical_claim"
    assert row_by_pn["104011"]["action_code"] == "stale_truth_reconcile"
    assert row_by_pn["104011"]["suggested_action"] == "reconcile_stale_truth_before_followup"
    assert row_by_pn["NO-PRICE-1"]["offer_admissibility_status"] == "no_price_found"
    assert row_by_pn["NO-PRICE-1"]["action_code"] == "scout_price"
    assert row_by_pn["NO-PRICE-1"]["suggested_action"] == "find_admissible_price_source_or_confirm_no_price"
    assert row_by_pn["101411"]["offer_admissibility_status"] == "no_price_found"
    assert row_by_pn["101411"]["action_code"] == "admissibility_review"
    assert row_by_pn["101411"]["suggested_action"] == "review_ambiguous_offer_for_admissibility"


def test_queue_recomputes_stale_embedded_admissibility_from_current_price_truth(tmp_path):
    evidence_dir = tmp_path / "evidence"
    output_dir = tmp_path / "queues"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    bundle = {
        "pn": "1012541",
        "name": "Earmuff",
        "brand": "Honeywell",
        "card_status": "REVIEW_REQUIRED",
        "photo": {"verdict": "KEEP"},
        "price": {
            "price_status": "public_price",
            "price_per_unit": 68.9,
            "currency": "PLN",
            "source_url": "https://behapownia.pl/nauszniki-nahelmowe-howard-l3h",
            "offer_qty": 1,
            "offer_unit_basis": "piece",
            "http_status": 200,
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_lineage_reason_code": "structured_exact_product_page",
            "price_source_clean_product_page": True,
            "page_product_class": "Nauszniki nahełmowe HOWARD L3H (1012541)",
            "price_source_surface_conflict_detected": True,
            "blocked_ui_detected": True,
            "blocked_surface_page_url": "https://www.vseinstrumenti.ru/product/blocked-tail",
            "offer_admissibility_status": "blocked_or_auth_gated",
            "staleness_or_conflict_status": "unresolved_conflict",
            "price_admissibility_review_bucket": "STALE_TRUTH_REVIEW",
            "price_admissibility_reason_codes": [
                "PRICE_BLOCKED_OR_AUTH_GATED",
                "PRICE_UNRESOLVED_CONFLICT",
            ],
        },
        "content": {},
    }
    (evidence_dir / "evidence_1012541.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")

    summary = run(evidence_dir=evidence_dir, output_dir=output_dir, prefix="recompute")
    rows = [
        json.loads(line)
        for line in Path(summary["price_followup_queue"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(rows) == 1
    assert rows[0]["part_number"] == "1012541"
    assert rows[0]["offer_admissibility_status"] == "admissible_public_price"
    assert rows[0]["staleness_or_conflict_status"] == "unresolved_conflict"
    assert rows[0]["action_code"] == "admissibility_review"


def test_unresolved_conflict_with_blocked_routes_to_blocked_owner_review(tmp_path):
    evidence_dir = tmp_path / "evidence"
    output_dir = tmp_path / "queues"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    bundle = {
        "pn": "1015021",
        "name": "Earmuff HiViz",
        "brand": "Honeywell",
        "card_status": "REVIEW_REQUIRED",
        "photo": {"verdict": "KEEP"},
        "price": {
            "price_status": "ambiguous_offer",
            "price_per_unit": 4314.4,
            "currency": "RUB",
            "source_url": "https://lemanapro.ru/product/1015021",
            "offer_qty": 1,
            "offer_unit_basis": "piece",
            "http_status": 401,
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_lineage_reason_code": "cu_vision_pn_confirmed",
            "price_source_surface_conflict_detected": True,
            "price_source_surface_conflict_reason_code": "current_surface_conflicts_with_prior",
            "price_admissibility_schema_version": "price_admissibility_v1",
            "offer_admissibility_status": "blocked_or_auth_gated",
            "staleness_or_conflict_status": "unresolved_conflict",
            "price_admissibility_review_bucket": "STALE_TRUTH_REVIEW",
            "price_admissibility_reason_codes": [
                "PRICE_BLOCKED_OR_AUTH_GATED",
                "PRICE_UNRESOLVED_CONFLICT",
            ],
        },
        "content": {},
    }
    (evidence_dir / "evidence_1015021.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")

    summary = run(evidence_dir=evidence_dir, output_dir=output_dir, prefix="blocked_conflict")
    rows = [
        json.loads(line)
        for line in Path(summary["price_followup_queue"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(rows) == 1
    assert rows[0]["part_number"] == "1015021"
    assert rows[0]["offer_admissibility_status"] == "blocked_or_auth_gated"
    assert rows[0]["staleness_or_conflict_status"] == "unresolved_conflict"
    assert rows[0]["action_code"] == "blocked_owner_review"


def test_unresolved_conflict_with_ambiguous_offer_stays_stale_truth(tmp_path):
    evidence_dir = tmp_path / "evidence"
    output_dir = tmp_path / "queues"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    bundle = {
        "pn": "FAKE001",
        "name": "Widget",
        "brand": "Test",
        "card_status": "REVIEW_REQUIRED",
        "photo": {"verdict": "KEEP"},
        "price": {
            "price_status": "ambiguous_offer",
            "price_per_unit": 50.0,
            "currency": "EUR",
            "source_url": "https://example.com/widget",
            "offer_qty": 1,
            "offer_unit_basis": "piece",
            "http_status": 200,
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_surface_conflict_detected": True,
            "price_admissibility_schema_version": "price_admissibility_v1",
            "offer_admissibility_status": "ambiguous_offer",
            "staleness_or_conflict_status": "unresolved_conflict",
            "price_admissibility_review_bucket": "STALE_TRUTH_REVIEW",
            "price_admissibility_reason_codes": ["PRICE_UNRESOLVED_CONFLICT"],
        },
        "content": {},
    }
    (evidence_dir / "evidence_FAKE001.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")

    summary = run(evidence_dir=evidence_dir, output_dir=output_dir, prefix="ambig_conflict")
    rows = [
        json.loads(line)
        for line in Path(summary["price_followup_queue"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(rows) == 1
    assert rows[0]["action_code"] == "stale_truth_reconcile"


def test_pure_blocked_without_semantic_barrier_stays_blocked_owner_review(tmp_path):
    evidence_dir = tmp_path / "evidence"
    output_dir = tmp_path / "queues"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    bundle = {
        "pn": "PURE-BLOCKED",
        "name": "Blocked exact product",
        "brand": "Test",
        "card_status": "REVIEW_REQUIRED",
        "photo": {"verdict": "KEEP"},
        "price": {
            "price_status": "no_price_found",
            "price_per_unit": None,
            "currency": None,
            "source_url": "https://example.com/blocked-exact",
            "offer_qty": 1,
            "offer_unit_basis": "piece",
            "http_status": 403,
            "blocked_ui_detected": True,
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_lineage_reason_code": "structured_exact_product_page",
            "price_source_clean_product_page": True,
            "page_product_class": "Exact Product Page",
            "price_admissibility_schema_version": "price_admissibility_v1",
            "offer_admissibility_status": "blocked_or_auth_gated",
            "staleness_or_conflict_status": "clean",
            "price_admissibility_reason_codes": ["PRICE_BLOCKED_OR_AUTH_GATED"],
            "price_admissibility_review_bucket": "PRICE_BLOCKED_SURFACE",
        },
        "content": {},
    }
    (evidence_dir / "evidence_PURE-BLOCKED.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")

    summary = run(evidence_dir=evidence_dir, output_dir=output_dir, prefix="pure_blocked")
    rows = [
        json.loads(line)
        for line in Path(summary["price_followup_queue"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(rows) == 1
    assert rows[0]["action_code"] == "blocked_owner_review"
    assert rows[0]["suggested_action"] == "confirm_blocked_surface_or_owner_review"
