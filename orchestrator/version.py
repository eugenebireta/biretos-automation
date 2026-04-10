"""
version.py — Version module for the Meta Orchestrator.

Provides VERSION constant and get_version() accessor.

Usage:
    from orchestrator.version import VERSION, get_version
    v = get_version(trace_id="...")
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

VERSION = "1.0.0"


def get_version(
    *,
    trace_id: str,
    idempotency_key: str | None = None,
) -> str:
    """Return the current orchestrator version string.

    Args:
        trace_id: Required trace ID for structured logging.
        idempotency_key: Optional idempotency key.

    Returns:
        Version string (e.g. '1.0.0').
    """
    logger.info(
        "get_version called",
        extra={
            "trace_id": trace_id,
            "idempotency_key": idempotency_key,
            "version": VERSION,
        },
    )
    return VERSION
