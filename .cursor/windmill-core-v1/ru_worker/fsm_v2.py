"""
FSM v2 - Pure Deterministic State Machine

ВАЖНО: FSM v2 = pure function, без side-effects:
- НЕ читает БД
- НЕ пишет в БД
- НЕ вызывает внешние API
- НЕ использует текущее время (now())
- НЕ логирует
- НЕ знает про job_queue

FSM принимает event + current ledger state → возвращает описание изменений.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, Literal
from uuid import UUID

from domain.fsm_guards import ALLOWED_TRANSITIONS, STATES


@dataclass
class Event:
    """Canonical event structure"""
    event_id: UUID
    source: str
    event_type: str
    occurred_at: str  # ISO8601 timestamp
    payload: Dict[str, Any]


@dataclass
class LedgerRecord:
    """Current ledger state"""
    order_id: UUID
    state: str
    state_history: list  # JSONB array
    metadata: Dict[str, Any]  # JSONB object


@dataclass
class FSMResult:
    """FSM processing result"""
    action: Literal["transition", "skip", "error"]
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    state_history_entry: Optional[Dict[str, Any]] = None
    metadata_patch: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


def fsm_v2_process_event(event: Event, ledger_record: LedgerRecord) -> FSMResult:
    """
    Pure FSM v2 function: processes event against current ledger state.
    
    Returns FSMResult describing what changes should be made (if any).
    Does NOT modify database or call external APIs.
    
    Args:
        event: Canonical event structure
        ledger_record: Current ledger state
    
    Returns:
        FSMResult with action (transition|skip|error) and change description
    """
    current_state = ledger_record.state
    
    # Validate current state
    if current_state not in STATES:
        return FSMResult(
            action="error",
            error={
                "error_type": "invalid_state",
                "message": f"Invalid current state: {current_state}",
                "context": {"current_state": current_state}
            }
        )
    
    # Map event to target state.
    target_state_result = _map_event_to_target_state(event, current_state)
    if target_state_result["action"] == "error":
        return FSMResult(
            action="error",
            error=target_state_result["error"]
        )
    
    target_state = target_state_result["target_state"]
    
    # Idempotency check: if already in target state, skip
    if current_state == target_state:
        return FSMResult(
            action="skip",
            from_state=current_state,
            to_state=target_state
        )
    
    # Check if transition is allowed
    allowed_next_states = ALLOWED_TRANSITIONS.get(current_state, [])
    if target_state not in allowed_next_states:
        return FSMResult(
            action="error",
            error={
                "error_type": "transition_not_allowed",
                "message": f"Transition {current_state} → {target_state} is not allowed",
                "context": {
                    "current_state": current_state,
                    "target_state": target_state,
                    "allowed_states": allowed_next_states
                }
            }
        )
    
    # Build state history entry
    state_history_entry = {
        "from_state": current_state,
        "to_state": target_state,
        "reason": f"{event.source}:{event.event_type}",
        "context": {},
        "timestamp": event.occurred_at,
        "event_source": event.source,
        "event_type": event.event_type,
        "event_id": str(event.event_id)
    }
    
    # Get metadata patch from event mapping
    metadata_patch = target_state_result.get("metadata_patch", {})
    
    return FSMResult(
        action="transition",
        from_state=current_state,
        to_state=target_state,
        state_history_entry=state_history_entry,
        metadata_patch=metadata_patch
    )


def _map_event_to_target_state(event: Event, current_state: str) -> Dict[str, Any]:
    """
    Maps event (source + event_type) to target state and metadata patch.
    
    Returns:
        {
            "action": "ok" | "error",
            "target_state": str (if action="ok"),
            "metadata_patch": dict (if action="ok"),
            "error": dict (if action="error")
        }
    """
    # T-Bank events
    if event.source == "tbank" and event.event_type == "INVOICE_PAID":
        payment_is_partial = bool(event.payload.get("is_partial"))
        target_state = "partially_paid" if payment_is_partial else "paid"
        metadata_patch = {
            "last_paid_at": event.payload.get("paid_at"),
            "last_transition_reason": f"{event.source}:{event.event_type}",
            "last_transition_context": {}
        }
        
        # Add invoice_number if present
        invoice_number = event.payload.get("invoice_number")
        if invoice_number:
            metadata_patch["invoice_number"] = invoice_number
        
        return {
            "action": "ok",
            "target_state": target_state,
            "metadata_patch": metadata_patch
        }

    if event.source == "tbank" and event.event_type == "PAYMENT_PARTIAL":
        return {
            "action": "ok",
            "target_state": "partially_paid",
            "metadata_patch": {
                "last_transition_reason": f"{event.source}:{event.event_type}",
                "last_transition_context": {},
            },
        }
    
    # T-Bank invoice creation
    if event.source == "tbank" and event.event_type == "INVOICE_CREATED":
        target_state = "invoice_created"
        metadata_patch = {
            "last_transition_reason": f"{event.source}:{event.event_type}",
            "last_transition_context": {}
        }
        
        # Add invoice data if present
        invoice_id = event.payload.get("invoice_id")
        invoice_number = event.payload.get("invoice_number")
        pdf_url = event.payload.get("pdf_url")
        
        if invoice_id:
            metadata_patch["tbank_invoice_id"] = invoice_id
        if invoice_number:
            metadata_patch["invoiceNumber"] = invoice_number
        if pdf_url:
            metadata_patch["pdfUrl"] = pdf_url
        
        return {
            "action": "ok",
            "target_state": target_state,
            "metadata_patch": metadata_patch
        }
    
    # Shipment requested
    if event.source in {"system", "cdek"} and event.event_type == "SHIPMENT_REQUESTED":
        return {
            "action": "ok",
            "target_state": "shipment_pending",
            "metadata_patch": {
                "last_transition_reason": f"{event.source}:{event.event_type}",
                "last_transition_context": {},
            },
        }

    # CDEK shipment creation
    if event.source == "cdek" and event.event_type == "SHIPMENT_CREATED":
        target_state = "partially_shipped"
        if event.payload.get("all_lines_shipped"):
            target_state = "shipped"
        metadata_patch = {
            "last_transition_reason": f"{event.source}:{event.event_type}",
            "last_transition_context": {}
        }
        
        # Add cdek_uuid if present
        cdek_uuid = event.payload.get("cdek_uuid")
        if cdek_uuid:
            metadata_patch["cdek_uuid"] = cdek_uuid
        
        return {
            "action": "ok",
            "target_state": target_state,
            "metadata_patch": metadata_patch
        }

    if event.source == "shipment" and event.event_type == "ALL_DELIVERED":
        return {
            "action": "ok",
            "target_state": "completed",
            "metadata_patch": {
                "last_transition_reason": f"{event.source}:{event.event_type}",
                "last_transition_context": {},
            },
        }

    if event.source == "shipment" and event.event_type == "PARTIAL_DELIVERED":
        return {
            "action": "ok",
            "target_state": "shipped",
            "metadata_patch": {
                "last_transition_reason": f"{event.source}:{event.event_type}",
                "last_transition_context": {},
            },
        }

    if event.source in {"system", "order"} and event.event_type == "ORDER_CANCELLED":
        return {
            "action": "ok",
            "target_state": "cancelled",
            "metadata_patch": {
                "last_transition_reason": f"{event.source}:{event.event_type}",
                "last_transition_context": {},
            },
        }

    if event.source == "system" and event.event_type == "CSG_HOLD":
        return {
            "action": "ok",
            "target_state": "pending_approval",
            "metadata_patch": {
                "last_transition_reason": f"{event.source}:{event.event_type}",
                "last_transition_context": {
                    "gate_name": event.payload.get("gate_name"),
                    "reason": event.payload.get("reason"),
                },
            },
        }

    if event.source == "system" and event.event_type == "QUARANTINE_ACTIVATE":
        return {
            "action": "ok",
            "target_state": "quarantined",
            "metadata_patch": {
                "last_transition_reason": f"{event.source}:{event.event_type}",
                "last_transition_context": {
                    "reason": event.payload.get("reason"),
                },
            },
        }

    if event.source == "system" and event.event_type == "HUMAN_DECISION_TIMEOUT":
        return {
            "action": "ok",
            "target_state": "human_decision_timeout",
            "metadata_patch": {
                "last_transition_reason": f"{event.source}:{event.event_type}",
                "last_transition_context": {
                    "reason": event.payload.get("reason", "human_decision_timeout"),
                },
            },
        }

    if event.source == "system" and event.event_type == "QUARANTINE_EXPIRED":
        return {
            "action": "ok",
            "target_state": "quarantine_expired",
            "metadata_patch": {
                "last_transition_reason": f"{event.source}:{event.event_type}",
                "last_transition_context": {
                    "reason": event.payload.get("reason", "quarantine_expired"),
                },
            },
        }
    
    # Unsupported event
    return {
        "action": "error",
        "error": {
            "error_type": "unsupported_event",
            "message": f"Unsupported event: {event.source}:{event.event_type}",
            "context": {
                "source": event.source,
                "event_type": event.event_type
            }
        }
    }

