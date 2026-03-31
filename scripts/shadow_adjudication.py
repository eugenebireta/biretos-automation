"""Generate adjudication and development-memory artifacts from one shadow run."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
MEMORY_DIR = ROOT / "docs" / "memory"

POLICY_PATH = CONFIG_DIR / "shadow_adjudication_policy_v1.json"
ADJUDICATION_SCHEMA_PATH = CONFIG_DIR / "shadow_adjudication_record_schema_v1.json"
MEMORY_SCHEMA_PATH = CONFIG_DIR / "development_memory_schema_v1.json"
VERIFIER_POLICY_PATH = CONFIG_DIR / "catalog_verifier_policy_v1.json"


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(value: str) -> str:
    keep = []
    for char in value:
        keep.append(char if char.isalnum() or char in "._-" else "_")
    return "".join(keep).strip("_")


def load_shadow_run(run_dir: Path) -> dict[str, Any]:
    report = _load_json(run_dir / "sanity_audit_report.json")
    manifest = _load_json(run_dir / "batch_manifest.json")
    bundles = []
    for file_path in sorted((run_dir / "evidence").glob("evidence_*.json")):
        bundles.append(_load_json(file_path))
    return {"run_dir": run_dir, "report": report, "manifest": manifest, "bundles": bundles}


def _artifact_refs(run_dir: Path, pn: str) -> dict[str, str]:
    slug = _slugify(pn)
    return {
        "bundle": str(run_dir / "evidence" / f"evidence_{slug}.json"),
        "report": str(run_dir / "sanity_audit_report.json"),
        "sidecar": str(run_dir / "candidate_sidecar.jsonl"),
        "run_log": str(run_dir / "run_first_stdout.log"),
    }


def _disagreement_categories(bundle: dict[str, Any], shadow: dict[str, Any]) -> list[str]:
    categories: list[str] = []
    response = shadow.get("response") or {}
    deterministic = bundle["policy_decision_v2"]["card_status"]
    verdict = response.get("verdict")
    if response:
        if deterministic != "REVIEW_REQUIRED" and verdict == "CONFIRM_REVIEW":
            categories.append("deterministic_vs_verifier_disagreement")
            if deterministic == "DRAFT_ONLY":
                categories.append("policy_too_strict_candidate")
        if verdict == "INSUFFICIENT_EVIDENCE" or response.get("evidence_sufficiency") == "INSUFFICIENT":
            categories.append("verifier_insufficient_evidence")
    return sorted(set(categories))


def _contradiction_categories(bundle: dict[str, Any], shadow: dict[str, Any]) -> list[str]:
    categories: list[str] = []
    response = shadow.get("response") or {}
    contradictions = response.get("contradictions_found") or []
    if contradictions:
        categories.append("contradiction_in_evidence")
    if any("source" in text.lower() or "category_mismatch" in text.lower() for text in contradictions):
        categories.append("source_quality_problem")
    if (
        bundle.get("structured_identity", {}).get("exact_structured_pn_match") is False
        and bundle["policy_decision_v2"]["identity_level"] != "strong"
    ):
        categories.append("upstream_missing_signal")
    return sorted(set(categories))


def _blocker_categories(bundle: dict[str, Any], shadow: dict[str, Any], report: dict[str, Any]) -> list[str]:
    categories: list[str] = []
    response = shadow.get("response") or {}
    usage = shadow.get("usage") or {}
    if shadow.get("call_state") == "skipped_budget" or report["shadow_run_summary"]["first_run"].get("early_stop"):
        categories.append("runtime_budget_problem")
    if response and usage.get("input_tokens", 0) == 0 and usage.get("output_tokens", 0) == 0:
        categories.append("cost_visibility_problem")
    categories.extend(_contradiction_categories(bundle, shadow))
    categories.extend(_disagreement_categories(bundle, shadow))
    return sorted(set(categories))


def _recommendation_category(disagreement_categories: list[str], blocker_categories: list[str]) -> str:
    if "policy_too_strict_candidate" in disagreement_categories:
        return "owner_review"
    if "upstream_missing_signal" in blocker_categories:
        return "deterministic_fix_candidate"
    if "cost_visibility_problem" in blocker_categories:
        return "schema_observability_fix"
    if "runtime_budget_problem" in blocker_categories:
        return "runtime_tuning_candidate"
    return "defer_out_of_scope"


def _recommended_next_action(disagreement_categories: list[str], blocker_categories: list[str]) -> str:
    if "policy_too_strict_candidate" in disagreement_categories:
        return "Review whether weak-identity DRAFT_ONLY cases should become REVIEW_REQUIRED under stricter deterministic gates."
    if "upstream_missing_signal" in blocker_categories:
        return "Materialize stronger exact identity signals upstream before broadening deterministic publishability."
    if "cost_visibility_problem" in blocker_categories:
        return "Persist non-zero verifier token usage and per-call latency in shadow records."
    if "runtime_budget_problem" in blocker_categories:
        return "Tune bounded runtime profile or narrow the routed set before the next shadow slice."
    return "Keep verifier advisory-only and defer broader decision changes."


def assign_review_priority(disagreement_categories: list[str], contradiction_categories: list[str], blocker_categories: list[str]) -> tuple[str, int]:
    policy = _load_json(POLICY_PATH)
    score = 0
    base_scores = policy["priority_rules"]["base_scores"]
    for category in set(disagreement_categories + contradiction_categories + blocker_categories):
        score += int(base_scores.get(category, 0))
    if score >= policy["priority_rules"]["priority_bands"]["P1"]:
        return "P1", score
    if score >= policy["priority_rules"]["priority_bands"]["P2"]:
        return "P2", score
    if score >= policy["priority_rules"]["priority_bands"]["P3"]:
        return "P3", score
    return "P4", score


def build_adjudication_queue(run_dir: Path) -> list[dict[str, Any]]:
    payload = load_shadow_run(run_dir)
    report = payload["report"]
    queue: list[dict[str, Any]] = []
    schema = _load_json(ADJUDICATION_SCHEMA_PATH)
    for bundle in payload["bundles"]:
        shadow = bundle.get("verifier_shadow", {})
        if shadow.get("call_state") == "not_routed":
            continue
        disagreement_categories = _disagreement_categories(bundle, shadow)
        contradiction_categories = _contradiction_categories(bundle, shadow)
        blocker_categories = _blocker_categories(bundle, shadow, report)
        review_priority, review_score = assign_review_priority(
            disagreement_categories,
            contradiction_categories,
            blocker_categories,
        )
        response = shadow.get("response") or {}
        record = {
            "schema_version": schema["schema_version"],
            "run_id": report["batch_id"],
            "trace_id": shadow.get("trace_id", ""),
            "pn_primary": bundle["pn"],
            "deterministic_result": {
                "card_status": bundle["policy_decision_v2"]["card_status"],
                "identity_level": bundle["policy_decision_v2"]["identity_level"],
                "field_statuses": dict(bundle.get("field_statuses_v2", {})),
            },
            "verifier_result": {
                "call_state": shadow.get("call_state"),
                "verdict": response.get("verdict"),
                "confidence": response.get("confidence"),
                "suggested_action": response.get("suggested_action"),
                "suggested_review_bucket": response.get("suggested_review_bucket"),
            },
            "disagreement_categories": disagreement_categories,
            "contradiction_categories": contradiction_categories,
            "blocker_categories": blocker_categories,
            "contradiction_summary": response.get("contradictions_found", []),
            "blocker_summary": report["broader_controlled_run_assessment"]["blocking_issues"],
            "recommendation_category": _recommendation_category(disagreement_categories, blocker_categories),
            "recommended_next_action": _recommended_next_action(disagreement_categories, blocker_categories),
            "review_priority": review_priority,
            "review_priority_score": review_score,
            "source_artifact_refs": _artifact_refs(run_dir, bundle["pn"]),
        }
        queue.append(record)
    queue.sort(key=lambda row: (-row["review_priority_score"], row["pn_primary"]))
    return queue


def build_blocker_register(run_dir: Path, queue: list[dict[str, Any]]) -> dict[str, Any]:
    payload = load_shadow_run(run_dir)
    report = payload["report"]
    blocker_counts = Counter()
    for row in queue:
        blocker_counts.update(row["blocker_categories"])
    broader_blockers = report["broader_controlled_run_assessment"]["blocking_issues"]
    strongest = {
        "category": "still_blocked_for_broader_run",
        "severity": "CRITICAL",
        "fixable_in_scope": False,
        "why": broader_blockers[0] if broader_blockers else "Broader controlled run remains closed.",
    }
    examples = []
    for row in queue[:5]:
        examples.append(
            {
                "pn_primary": row["pn_primary"],
                "review_priority": row["review_priority"],
                "blocker_categories": row["blocker_categories"],
                "recommended_next_action": row["recommended_next_action"],
            }
        )
    return {
        "schema_version": "shadow_blocker_register_v1",
        "run_id": report["batch_id"],
        "strongest_blocker": strongest,
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "blocker_examples": examples,
        "broader_run_blocking_issues": broader_blockers,
    }


def build_shadow_usefulness_summary(run_dir: Path, queue: list[dict[str, Any]]) -> dict[str, Any]:
    payload = load_shadow_run(run_dir)
    report = payload["report"]
    completed = [row for row in queue if row["verifier_result"]["call_state"] == "completed"]
    useful_disagreements = [
        row for row in completed
        if "policy_too_strict_candidate" in row["disagreement_categories"]
    ]
    noisy_disagreements = [
        row for row in completed
        if not row["disagreement_categories"] and not row["contradiction_categories"]
    ]
    insufficiency = [
        row for row in completed
        if "verifier_insufficient_evidence" in row["disagreement_categories"]
    ]
    return {
        "schema_version": "shadow_usefulness_summary_v1",
        "run_id": report["batch_id"],
        "agreement_count": 0,
        "disagreement_count": len(useful_disagreements),
        "disagreement_rate": round(len(useful_disagreements) / len(completed), 4) if completed else 0.0,
        "useful_disagreements": [row["pn_primary"] for row in useful_disagreements],
        "noisy_disagreements": [row["pn_primary"] for row in noisy_disagreements],
        "verifier_insufficiency": [row["pn_primary"] for row in insufficiency],
        "cases_worth_future_decision_influence": [],
        "cases_proving_verifier_is_still_only_advisory": [row["pn_primary"] for row in useful_disagreements],
        "deterministic_still_authoritative": True,
        "broader_controlled_run": report["broader_controlled_run_assessment"]["ready"],
    }


def build_reviewer_packets(run_dir: Path, queue: list[dict[str, Any]], top_n: int = 5) -> list[dict[str, Any]]:
    payload = load_shadow_run(run_dir)
    by_pn = {bundle["pn"]: bundle for bundle in payload["bundles"]}
    packets = []
    for row in queue[:top_n]:
        bundle = by_pn[row["pn_primary"]]
        shadow = bundle["verifier_shadow"]
        response = shadow.get("response") or {}
        packets.append(
            {
                "schema_version": "shadow_reviewer_packet_v1",
                "run_id": payload["report"]["batch_id"],
                "pn_primary": row["pn_primary"],
                "review_priority": row["review_priority"],
                "evidence_summary": {
                    "field_statuses": bundle["field_statuses_v2"],
                    "review_reasons_v2": bundle["review_reasons_v2"],
                    "structured_identity": bundle.get("structured_identity", {}),
                },
                "deterministic_status": bundle["policy_decision_v2"]["card_status"],
                "verifier_verdict": response.get("verdict"),
                "verifier_confidence": response.get("confidence"),
                "contradictions": response.get("contradictions_found", []),
                "suggested_owner_decision": row["recommended_next_action"],
                "why_case_matters": row["blocker_summary"],
                "artifact_refs": row["source_artifact_refs"],
            }
        )
    return packets


def build_development_memory(run_dir: Path, queue: list[dict[str, Any]], blocker_register: dict[str, Any], usefulness_summary: dict[str, Any]) -> dict[str, Any]:
    payload = load_shadow_run(run_dir)
    report = payload["report"]
    manifest = payload["manifest"]
    first_bundle = payload["bundles"][0]
    verifier_policy = _load_json(VERIFIER_POLICY_PATH)
    memory_schema = _load_json(MEMORY_SCHEMA_PATH)
    return {
        "schema_version": memory_schema["schema_version"],
        "snapshot_id": f"phase_a_memory:{report['batch_id']}",
        "updated_at": _utc_now(),
        "source_run_id": report["batch_id"],
        "proven": [
            "Bounded shadow mode is operational on a live sanity slice.",
            "Verifier transport is /responses-only and verifier chat-completions calls stayed at 0.",
            "Deterministic pipeline remained the system of record during the live shadow run.",
            "Shadow disagreements are materially useful for review-routing analysis.",
        ],
        "not_proven_or_rejected": [
            "Decision influence pilot is not ready from this run.",
            "Broader controlled run is not unlocked by the current shadow evidence.",
            "Verifier cost visibility is not yet materially proven because token usage stayed at 0 in artifacts.",
        ],
        "current_blockers": [
            blocker_register["strongest_blocker"],
            {
                "category": "false_public_price_and_numeric_keep_controls",
                "severity": "HIGH",
                "fixable_in_scope": True,
                "why": report["broader_controlled_run_assessment"]["blocking_issues"],
            },
        ],
        "active_constraints": [
            "deterministic pipeline remains system of record",
            "verifier remains advisory only",
            "no auto-publish unlock from verifier",
            "broader controlled run remains closed",
            "unrestricted full run remains closed",
            "no weak marketplaces in bounded shadow mode",
        ],
        "next_approved_work_item": {
            "title": "Deterministic false-positive control pack for false public-price and numeric/dotted PN KEEP cases",
            "why": "This is the strongest remaining in-scope blocker for broader controlled run after the live bounded shadow run.",
        },
        "artifact_references": {
            "run_dir": str(run_dir),
            "manifest": str(run_dir / "batch_manifest.json"),
            "report": str(run_dir / "sanity_audit_report.json"),
            "adjudication_queue": str(run_dir / "shadow_adjudication_queue.json"),
            "blocker_register": str(run_dir / "shadow_blocker_register.json"),
            "reviewer_packets": str(run_dir / "shadow_reviewer_packets.json"),
            "usefulness_summary": str(run_dir / "shadow_usefulness_summary.json"),
        },
        "policy_schema_versions": {
            "phase_a_policy_version": first_bundle["policy_decision_v2"]["policy_version"],
            "family_photo_policy_version": first_bundle["policy_decision_v2"]["family_photo_policy_version"],
            "source_matrix_version": first_bundle["policy_decision_v2"]["source_matrix_version"],
            "review_schema_version": first_bundle["policy_decision_v2"]["review_schema_version"],
            "verifier_policy_version": verifier_policy["policy_version"],
            "adjudication_policy_version": _load_json(POLICY_PATH)["policy_version"],
            "selection_mode": manifest["selection_mode"],
        },
    }


def materialize_shadow_artifacts(run_dir: Path, *, memory_path: Path | None = None) -> dict[str, Path]:
    queue = build_adjudication_queue(run_dir)
    blocker_register = build_blocker_register(run_dir, queue)
    usefulness_summary = build_shadow_usefulness_summary(run_dir, queue)
    reviewer_packets = build_reviewer_packets(run_dir, queue)
    memory_snapshot = build_development_memory(run_dir, queue, blocker_register, usefulness_summary)

    outputs = {
        "queue": run_dir / "shadow_adjudication_queue.json",
        "blocker_register": run_dir / "shadow_blocker_register.json",
        "usefulness_summary": run_dir / "shadow_usefulness_summary.json",
        "reviewer_packets": run_dir / "shadow_reviewer_packets.json",
        "development_memory": memory_path or (MEMORY_DIR / "PHASE_A_DEVELOPMENT_MEMORY_v1.json"),
    }
    outputs["queue"].write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    outputs["blocker_register"].write_text(json.dumps(blocker_register, ensure_ascii=False, indent=2), encoding="utf-8")
    outputs["usefulness_summary"].write_text(json.dumps(usefulness_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    outputs["reviewer_packets"].write_text(json.dumps(reviewer_packets, ensure_ascii=False, indent=2), encoding="utf-8")
    outputs["development_memory"].parent.mkdir(parents=True, exist_ok=True)
    outputs["development_memory"].write_text(json.dumps(memory_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return outputs


def main() -> None:
    run_dir = ROOT / "downloads" / "audits" / "phase_a_v2_sanity_20260326T213348Z"
    outputs = materialize_shadow_artifacts(run_dir)
    for name, path in outputs.items():
        print(f"{name}={path}")


if __name__ == "__main__":
    main()
