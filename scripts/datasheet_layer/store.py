"""
SS-1.3 — Version store: read/write versioned datasheet records.

Atomic writes via temp file + os.replace (cross-platform safe).
File lock for concurrent write safety (cross-process via lockfile).
Per-PN directories: downloads/datasheets/{PN}/v1.json, v2.json, ...
Global index: downloads/datasheets/index.json
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_BASE = Path(__file__).resolve().parent.parent.parent / "downloads" / "datasheets"


def _structured_log(
    trace_id: str,
    outcome: str,
    *,
    error_class: str | None = None,
    severity: str = "INFO",
    retriable: bool = False,
    **extra: Any,
) -> None:
    """Structured log at decision boundary (DNA §7)."""
    entry = {
        "trace_id": trace_id,
        "module": "datasheet_store",
        "outcome": outcome,
        "severity": severity,
        **extra,
    }
    if error_class:
        entry["error_class"] = error_class
        entry["retriable"] = retriable
    log_fn = logger.error if severity == "ERROR" else logger.info
    log_fn(json.dumps(entry, ensure_ascii=False))


@contextmanager
def _file_lock(base_dir: Path, timeout: float = 10.0):
    """
    Cross-process file lock via lockfile.

    Uses atomic O_EXCL file creation. Falls back to no-lock if
    lock acquisition fails after timeout (logs warning, doesn't deadlock).
    """
    lock_path = base_dir / ".datasheet_store.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = None
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            time.sleep(0.05)
    if fd is None:
        logger.warning("datasheet_store: lock timeout after %.1fs, proceeding unlocked", timeout)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
            try:
                lock_path.unlink()
            except OSError:
                pass


def _atomic_write(path: Path, data: str) -> None:
    """Write data to path atomically via temp file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=".ds_"
    )
    try:
        os.write(fd, data.encode("utf-8"))
        os.close(fd)
        fd = None
        os.replace(tmp_path, str(path))
    except BaseException:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _load_index(base_dir: Path) -> dict:
    """Load global index.json. Returns empty dict if missing."""
    idx_path = base_dir / "index.json"
    if not idx_path.exists():
        return {}
    try:
        return json.loads(idx_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _structured_log(
            "", "index_load_error",
            error_class="TRANSIENT", severity="WARNING", retriable=True,
            error=str(exc),
        )
        return {}


def _save_index(base_dir: Path, index: dict) -> None:
    """Save global index.json atomically."""
    _atomic_write(
        base_dir / "index.json",
        json.dumps(index, indent=2, ensure_ascii=False),
    )


def get_pn_dir(base_dir: Path, pn: str) -> Path:
    """Get per-PN directory path."""
    return base_dir / pn


def get_latest_version(base_dir: Path, pn: str) -> int:
    """Get latest version number for a PN from index. Returns 0 if none."""
    index = _load_index(base_dir)
    entry = index.get(pn, {})
    return entry.get("latest_version", 0)


def write_version(
    base_dir: Path,
    record_dict: dict,
    trace_id: str = "",
) -> Path:
    """
    Write a versioned datasheet record. Thread/process safe via file lock.

    Dedup: if idempotency_key already exists for this PN, skip write.
    Atomic: v{N}.json written BEFORE index.json update.

    Returns path to written version file.
    Raises ValueError if dedup match found.
    """
    pn = record_dict["pn"]
    idem_key = record_dict.get("idempotency_key", "")
    version = record_dict["version"]

    pn_dir = get_pn_dir(base_dir, pn)

    with _file_lock(base_dir):
        # Dedup check under lock — no TOCTOU race
        if idem_key:
            existing = _find_by_idempotency_key(base_dir, pn, idem_key)
            if existing is not None:
                _structured_log(
                    trace_id, "dedup_skip",
                    pn=pn, idempotency_key=idem_key,
                    existing_version=existing,
                )
                raise ValueError(
                    f"Duplicate: {pn} already has version {existing} "
                    f"with idempotency_key={idem_key}"
                )

        # Write version file first (before index)
        version_path = pn_dir / f"v{version}.json"
        _atomic_write(
            version_path,
            json.dumps(record_dict, indent=2, ensure_ascii=False),
        )

        # Update index after version file is safely written
        index = _load_index(base_dir)
        index[pn] = {
            "latest_version": version,
            "version_count": version,
            "last_updated": record_dict.get("ingested_at", ""),
        }
        _save_index(base_dir, index)

    _structured_log(
        trace_id, "version_written",
        pn=pn, version=version,
        spec_count=len(record_dict.get("specs", {})),
    )
    return version_path


def read_version(base_dir: Path, pn: str, version: int) -> dict | None:
    """Read a specific version. Returns None if not found."""
    path = get_pn_dir(base_dir, pn) / f"v{version}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _structured_log(
            "", "version_read_error",
            error_class="TRANSIENT", severity="WARNING", retriable=True,
            pn=pn, version=version, error=str(exc),
        )
        return None


def read_latest(base_dir: Path, pn: str) -> dict | None:
    """Read the latest version for a PN."""
    latest_v = get_latest_version(base_dir, pn)
    if latest_v == 0:
        return None
    return read_version(base_dir, pn, latest_v)


def list_all_pns(base_dir: Path) -> list[str]:
    """List all PNs that have datasheet records."""
    index = _load_index(base_dir)
    return sorted(index.keys())


def _find_by_idempotency_key(
    base_dir: Path, pn: str, idem_key: str,
) -> int | None:
    """Find version number by idempotency_key. Returns None if not found."""
    pn_dir = get_pn_dir(base_dir, pn)
    if not pn_dir.exists():
        return None
    for vfile in sorted(pn_dir.glob("v*.json")):
        try:
            data = json.loads(vfile.read_text(encoding="utf-8"))
            if data.get("idempotency_key") == idem_key:
                return data.get("version")
        except (json.JSONDecodeError, OSError):
            continue
    return None
