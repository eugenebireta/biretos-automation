from __future__ import annotations

import hashlib
import json
from typing import Dict

# Canonical PII dependency classifications for replay propagation.
# Values MUST remain stable unless policy_hash/schema_version is bumped.
PII_STEP_CLASSIFICATIONS: Dict[str, str] = {
    "execute_invoice_create": "PII_DEPENDENT",
    "execute_cdek_shipment": "PII_DEPENDENT",
    "execute_tbank_invoice_paid": "PII_INDEPENDENT",
    "execute_order_event": "PII_INDEPENDENT",
    "execute_rfq_v1_from_ocr": "PII_INDEPENDENT",
    "dispatch_action": "PII_INDEPENDENT",
}


def get_pii_dependency_hash() -> str:
    """Deterministic hash for PII dependency metadata."""
    canonical = json.dumps(PII_STEP_CLASSIFICATIONS, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

