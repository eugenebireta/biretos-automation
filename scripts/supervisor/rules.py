from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from supervisor.launcher import (
    CommandSpec,
    build_photo_command,
    build_price_command,
    build_rebuild_command,
    build_refresh_command,
)
from supervisor.packets import find_packet_by_idempotency_key
from supervisor.reader import WorkspaceSnapshot


ALLOWLIST_BUSINESS_CASES = {
    "price_followup_owner_review": {
        "business_question": "В очереди остались SKU, которые нельзя продолжить автоматически без owner review.",
        "recommended_option": "defer",
        "default_option_id": "defer",
        "options": [
            {"id": "defer", "label": "Отложить", "next_action": "set_idle"},
            {"id": "review", "label": "Взять в manual owner lane", "next_action": "set_idle"},
        ],
    }
}


@dataclass(frozen=True)
class RuleDecision:
    rule_name: str
    kind: str
    action: str
    status: str
    reason: str = ""
    result_kind: str = ""
    command_spec: CommandSpec | None = None
    packet: dict[str, Any] | None = None
    dispatch_id: str = ""
    rerun_intent_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_z(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def build_trace_id(now: datetime | None = None) -> str:
    moment = now or utc_now()
    digest = hashlib.sha256(moment.isoformat().encode("utf-8")).hexdigest()[:6]
    return f"sup_{moment.strftime('%Y%m%dT%H%M%S')}_{digest}"


def _sha256_hexdigest(parts: list[str]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(str(part).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def build_dispatch_id(snapshot_id: str, command: list[str], params: dict[str, Any]) -> str:
    normalized_command = json.dumps(command, ensure_ascii=False, separators=(",", ":"))
    normalized_params = json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"dispatch_{_sha256_hexdigest([snapshot_id, normalized_command, normalized_params])[:20]}"


def build_packet_id(trace_id: str, packet_type: str) -> str:
    return f"pkt_{packet_type}_{trace_id}"


def build_packet_idempotency_key(
    *,
    packet_type: str,
    snapshot_id: str,
    rule_name: str,
    normalized_options: list[dict[str, Any]],
) -> str:
    normalized = json.dumps(normalized_options, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"idem_{_sha256_hexdigest([packet_type, snapshot_id, rule_name, normalized])[:24]}"


def build_owner_decision_packet(
    *,
    trace_id: str,
    snapshot: WorkspaceSnapshot,
    case_code: str,
    affected_sku_count: int,
    decision_deadline_at: str | None = None,
) -> dict[str, Any]:
    if case_code not in ALLOWLIST_BUSINESS_CASES:
        raise ValueError(f"Unsupported business case: {case_code}")
    spec = ALLOWLIST_BUSINESS_CASES[case_code]
    packet_id = build_packet_id(trace_id, "owner")
    options = list(spec["options"])
    idempotency_key = build_packet_idempotency_key(
        packet_type="owner_decision",
        snapshot_id=snapshot.snapshot_id,
        rule_name="RULE 8",
        normalized_options=options,
    )
    return {
        "event_type": "created",
        "type": "owner_decision",
        "packet_id": packet_id,
        "idempotency_key": idempotency_key,
        "delivery_status": "pending_send",
        "delivery_attempts": 0,
        "decision_status": "pending",
        "applied_option_id": None,
        "telegram_message_id": None,
        "telegram_update_id": None,
        "case_code": case_code,
        "what_blocked": "В follow-up backlog остались неисполняемые автоматически review-кейсы.",
        "why_not_auto": "Эти action_code не входят в bounded scout lane supervisor-а.",
        "business_question": spec["business_question"],
        "affected_sku_count": affected_sku_count,
        "recommended_option": spec["recommended_option"],
        "default_if_no_reply": spec["default_option_id"],
        "decision_deadline_at": decision_deadline_at,
        "snapshot_id": snapshot.snapshot_id,
        "artifact_refs": [
            str(snapshot.summary_path),
            str(snapshot.price_queue_path),
        ],
        "options": options,
        "trace_id": trace_id,
    }


def build_incident_packet(
    *,
    trace_id: str,
    action: str,
    command: list[str],
    exit_code: int,
    stdout_path: str,
    stderr_path: str,
    snapshot: WorkspaceSnapshot | None,
    error_class: str = "PERMANENT",
) -> dict[str, Any]:
    packet_id = build_packet_id(trace_id, "incident")
    idempotency_key = build_packet_idempotency_key(
        packet_type="incident",
        snapshot_id=snapshot.snapshot_id if snapshot else "no_snapshot",
        rule_name="RULE 7",
        normalized_options=[{"action": action, "exit_code": exit_code}],
    )
    artifact_refs = [stdout_path, stderr_path]
    if snapshot is not None:
        artifact_refs.append(str(snapshot.summary_path))
    return {
        "event_type": "created",
        "type": "incident",
        "packet_id": packet_id,
        "idempotency_key": idempotency_key,
        "delivery_status": "pending_send",
        "delivery_attempts": 0,
        "decision_status": None,
        "trace_id": trace_id,
        "script": action,
        "command": command,
        "exit_code": int(exit_code),
        "error_class": error_class,
        "artifact_refs": artifact_refs,
    }


def _build_launch_decision(rule_name: str, command_spec: CommandSpec, snapshot_id: str) -> RuleDecision:
    return RuleDecision(
        rule_name=rule_name,
        kind="launch",
        action=command_spec.action,
        status="completed",
        command_spec=command_spec,
        dispatch_id=build_dispatch_id(snapshot_id, command_spec.command, command_spec.params),
    )


def determine_next_action(
    *,
    manifest: dict[str, Any],
    snapshot: WorkspaceSnapshot | None,
    current_evidence_fingerprint: str,
    packet_states: dict[str, dict[str, Any]],
    photo_limit: int = 10,
    price_limit: int = 20,
    now: datetime | None = None,
    force_rerun: bool = False,
) -> RuleDecision:
    moment = now or utc_now()

    if str(manifest.get("status") or "") == "awaiting_packet_delivery":
        pending_packet_id = str(manifest.get("pending_packet_id") or "").strip()
        packet = dict(packet_states.get(pending_packet_id) or {})
        delivery_status = str(packet.get("delivery_status") or "").strip()
        next_retry_at = str(packet.get("next_retry_at") or "").strip()
        if packet and delivery_status in {"pending_send", "send_failed"}:
            if not next_retry_at:
                return RuleDecision(
                    rule_name="RULE T0",
                    kind="deliver",
                    action="deliver_packet",
                    status="awaiting_packet_delivery",
                    reason="packet_delivery_pending",
                    result_kind="delivery_attempt",
                    packet=packet,
                )
            try:
                retry_at = datetime.fromisoformat(next_retry_at.replace("Z", "+00:00"))
            except ValueError:
                retry_at = None
            if retry_at is None or retry_at <= moment:
                return RuleDecision(
                    rule_name="RULE T0",
                    kind="deliver",
                    action="deliver_packet",
                    status="awaiting_packet_delivery",
                    reason="packet_delivery_retry_due",
                    result_kind="delivery_attempt",
                    packet=packet,
                )
        return RuleDecision(
            rule_name="RULE T0",
            kind="noop",
            action="awaiting_packet_delivery",
            status="awaiting_packet_delivery",
            reason="packet_delivery_pending",
            result_kind="delivery_pending",
        )

    if str(manifest.get("status") or "") == "error":
        return RuleDecision(
            rule_name="RULE E0",
            kind="noop",
            action="error_halted",
            status="error",
            reason="supervisor halted after incident",
            result_kind="error_halted",
        )

    if bool(manifest.get("awaiting_owner_reply")):
        pending_packet_id = str(manifest.get("pending_packet_id") or "").strip()
        packet = packet_states.get(pending_packet_id, {})
        decision_status = str(packet.get("decision_status") or "").strip()
        applied_option_id = str(packet.get("applied_option_id") or "").strip()
        next_actions = dict(manifest.get("next_actions") or {})
        if decision_status == "applied" and applied_option_id and applied_option_id in next_actions:
            return RuleDecision(
                rule_name="RULE 1",
                kind="noop",
                action=str(next_actions[applied_option_id]),
                status="completed",
                reason="owner_reply_applied",
                result_kind="owner_reply_applied",
            )
        deadline_at = str(manifest.get("decision_deadline_at") or "").strip()
        default_option_id = str(manifest.get("default_option_id") or "").strip()
        if deadline_at and default_option_id:
            try:
                deadline = datetime.fromisoformat(deadline_at.replace("Z", "+00:00"))
            except ValueError:
                deadline = None
            if deadline is not None and moment >= deadline:
                return RuleDecision(
                    rule_name="RULE 2",
                    kind="noop",
                    action=str(next_actions.get(default_option_id) or "set_idle"),
                    status="completed",
                    reason="owner_reply_timeout_default",
                    result_kind="default_applied",
                    extra={"applied_option_id": default_option_id},
                )
        return RuleDecision(
            rule_name="RULE 3",
            kind="noop",
            action="still_waiting",
            status="awaiting_owner_reply",
            reason="owner_reply_pending",
            result_kind="still_waiting",
        )

    last_action = str(manifest.get("last_action") or "").strip()
    refresh_generation = int(manifest.get("refresh_generation") or 0)
    last_rebuild_generation = int(manifest.get("last_rebuild_generation") or 0)
    post_refresh_fingerprint = str(manifest.get("post_refresh_fingerprint") or "").strip()
    last_evidence_fingerprint = str(manifest.get("last_evidence_fingerprint") or "").strip()

    if last_action == "refresh" and last_rebuild_generation < refresh_generation:
        if current_evidence_fingerprint and post_refresh_fingerprint and current_evidence_fingerprint != post_refresh_fingerprint:
            return RuleDecision(
                rule_name="RULE 5C",
                kind="noop",
                action="concurrent_evidence_churn",
                status="error",
                reason="current fingerprint changed again after refresh before rebuild",
                result_kind="deferred",
            )
        if current_evidence_fingerprint and current_evidence_fingerprint == post_refresh_fingerprint:
            command_spec = build_rebuild_command()
            return _build_launch_decision("RULE 5B", command_spec, snapshot.snapshot_id if snapshot else "no_snapshot")

    if snapshot is not None and snapshot.photo_recovery_count > 0:
        command_spec = build_photo_command(snapshot.photo_queue_path, limit=photo_limit)
        dispatch_id = build_dispatch_id(snapshot.snapshot_id, command_spec.command, command_spec.params)
        if not force_rerun and dispatch_id == str(manifest.get("last_dispatch_id") or "").strip():
            return RuleDecision(
                rule_name="RULE 4",
                kind="noop",
                action="duplicate_dispatch_blocked",
                status="completed",
                reason="same dispatch_id already completed",
                result_kind="duplicate_dispatch_blocked",
                dispatch_id=dispatch_id,
            )
        rerun_intent_id = ""
        if force_rerun:
            rerun_intent_id = f"rerun_{_sha256_hexdigest([dispatch_id, isoformat_z(moment)])[:12]}"
        return RuleDecision(
            rule_name="RULE 4",
            kind="launch",
            action=command_spec.action,
            status="completed",
            command_spec=command_spec,
            dispatch_id=dispatch_id,
            rerun_intent_id=rerun_intent_id,
        )

    if snapshot is not None and snapshot.scout_price_count > 0:
        command_spec = build_price_command(snapshot.price_queue_path, limit=price_limit)
        dispatch_id = build_dispatch_id(snapshot.snapshot_id, command_spec.command, command_spec.params)
        if not force_rerun and dispatch_id == str(manifest.get("last_dispatch_id") or "").strip():
            return RuleDecision(
                rule_name="RULE 5",
                kind="noop",
                action="duplicate_dispatch_blocked",
                status="completed",
                reason="same dispatch_id already completed",
                result_kind="duplicate_dispatch_blocked",
                dispatch_id=dispatch_id,
            )
        rerun_intent_id = ""
        if force_rerun:
            rerun_intent_id = f"rerun_{_sha256_hexdigest([dispatch_id, isoformat_z(moment)])[:12]}"
        return RuleDecision(
            rule_name="RULE 5",
            kind="launch",
            action=command_spec.action,
            status="completed",
            command_spec=command_spec,
            dispatch_id=dispatch_id,
            rerun_intent_id=rerun_intent_id,
        )

    if current_evidence_fingerprint and current_evidence_fingerprint != last_evidence_fingerprint:
        command_spec = build_refresh_command()
        return _build_launch_decision("RULE 5A", command_spec, snapshot.snapshot_id if snapshot else current_evidence_fingerprint)

    if snapshot is not None and snapshot.non_executable_price_count > 0:
        packet = build_owner_decision_packet(
            trace_id=build_trace_id(moment),
            snapshot=snapshot,
            case_code="price_followup_owner_review",
            affected_sku_count=snapshot.non_executable_price_count,
            decision_deadline_at=isoformat_z(moment.replace(microsecond=0) + timedelta(hours=24)),
        )
        existing_packet = find_packet_by_idempotency_key(packet_states, packet["idempotency_key"])
        if existing_packet is not None:
            return RuleDecision(
                rule_name="RULE 8",
                kind="noop",
                action="awaiting_packet_delivery",
                status="awaiting_packet_delivery",
                reason="existing_owner_packet_present",
                result_kind="packet_already_created",
                packet=existing_packet,
            )
        return RuleDecision(
            rule_name="RULE 8",
            kind="packet",
            action="owner_decision_packet",
            status="awaiting_packet_delivery",
            reason="non_executable_price_review_backlog",
            result_kind="owner_decision_created",
            packet=packet,
        )

    return RuleDecision(
        rule_name="RULE 6",
        kind="noop",
        action="idle",
        status="completed",
        reason="nothing_pending",
        result_kind="idle",
    )
