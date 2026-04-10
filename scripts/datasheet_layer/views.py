"""
SS-1.4 — Read-only views over datasheet storage.

Pure read accessors. No mutations.
Backward compatible: reads both legacy evidence.datasheet and new versioned format.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .store import (
    read_latest,
    read_version,
    list_all_pns,
    get_latest_version,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE = Path(__file__).resolve().parent.parent.parent / "downloads" / "datasheets"


def get_latest_datasheet(pn: str, base_dir: Path | None = None) -> dict | None:
    """Get the latest versioned datasheet record for a PN."""
    if base_dir is None:
        base_dir = _DEFAULT_BASE
    return read_latest(base_dir, pn)


def get_datasheet_by_version(
    pn: str, version: int, base_dir: Path | None = None,
) -> dict | None:
    """Get a specific version of a datasheet record."""
    if base_dir is None:
        base_dir = _DEFAULT_BASE
    return read_version(base_dir, pn, version)


def get_specs(pn: str, base_dir: Path | None = None) -> dict[str, str]:
    """Get extracted specs from the latest datasheet. Empty dict if none."""
    record = get_latest_datasheet(pn, base_dir)
    if record is None:
        return {}
    return record.get("specs", {})


def get_version_history(pn: str, base_dir: Path | None = None) -> list[dict]:
    """
    Get all versions for a PN, ordered by version number.

    Returns list of dicts with version, ingested_at, content_hash, source_tier.
    """
    if base_dir is None:
        base_dir = _DEFAULT_BASE
    latest = get_latest_version(base_dir, pn)
    if latest == 0:
        return []
    history = []
    for v in range(1, latest + 1):
        record = read_version(base_dir, pn, v)
        if record:
            history.append({
                "version": record.get("version", v),
                "ingested_at": record.get("ingested_at", ""),
                "content_hash": record.get("content_hash", ""),
                "source_tier": record.get("source_tier", ""),
                "pn_confirmed": record.get("pn_confirmed", False),
                "supersedes": record.get("supersedes"),
            })
    return history


def list_datasheets(base_dir: Path | None = None) -> list[str]:
    """List all PNs that have datasheet records."""
    if base_dir is None:
        base_dir = _DEFAULT_BASE
    return list_all_pns(base_dir)


def get_from_legacy_evidence(
    evidence: dict,
) -> dict | None:
    """
    Read datasheet data from legacy evidence.datasheet block.

    Backward compatible accessor for evidence files that haven't been
    migrated to versioned storage yet.
    """
    ds = evidence.get("datasheet", {})
    if not ds or ds.get("datasheet_status") != "found":
        return None
    return ds
