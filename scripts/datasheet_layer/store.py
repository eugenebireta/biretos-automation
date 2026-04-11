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
def _file_lock(base_dir: Path, timeout: float = 10.0, trace_id: str = ""):
    """
    Cross-process file lock via lockfile.

    Uses atomic O_EXCL file creation. Raises TimeoutError if lock
    cannot be acquired — never proceeds unlocked.
    """
    lock_path = base_dir / ".datasheet_store.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = None
    import time

    # Stale lock detection: if lock file exists and is older than 60s,
    # assume the holder crashed and remove it (PID-based detection is
    # unreliable cross-platform; age-based is sufficient for our scale).
    _STALE_LOCK_AGE_S = 60.0
    if lock_path.exists():
        try:
            lock_age = time.time() - lock_path.stat().st_mtime
            if lock_age > _STALE_LOCK_AGE_S:
                lock_path.unlink(missing_ok=True)
                _structured_log(
                    trace_id, "stale_lock_removed",
                    severity="WARNING",
                    lock_age_s=round(lock_age, 1),
                )
        except OSError:
            pass  # race with another process removing it — fine

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            time.sleep(0.05)
    if fd is None:
        _structured_log(
            trace_id, "lock_timeout",
            error_class="TRANSIENT", severity="ERROR", retriable=True,
            timeout=timeout,
        )
        raise TimeoutError(
            f"datasheet_store: lock acquisition timed out after {timeout:.1f}s"
        )
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


def _load_index(base_dir: Path, trace_id: str = "") -> dict:
    """Load global index.json. Returns empty dict if file is missing.

    Raises on corrupt/unreadable file to prevent data loss — a subsequent
    _save_index would overwrite all PN entries with an empty dict.
    """
    idx_path = base_dir / "index.json"
    if not idx_path.exists():
        return {}
    try:
        return json.loads(idx_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _structured_log(
            trace_id, "index_load_error",
            error_class="TRANSIENT", severity="ERROR", retriable=True,
            error=str(exc),
        )
        raise


def _save_index(base_dir: Path, index: dict) -> None:
    """Save global index.json atomically."""
    _atomic_write(
        base_dir / "index.json",
        json.dumps(index, indent=2, ensure_ascii=False),
    )


def get_pn_dir(base_dir: Path, pn: str) -> Path:
    """Get per-PN directory path."""
    return base_dir / pn


def get_latest_version(base_dir: Path, pn: str, trace_id: str = "") -> int:
    """Get latest version number for a PN from index. Returns 0 if none."""
    index = _load_index(base_dir, trace_id=trace_id)
    entry = index.get(pn, {})
    return entry.get("latest_version", 0)


def write_version(
    base_dir: Path,
    record_dict: dict,
    trace_id: str = "",
    auto_version: bool = False,
) -> tuple[Path, int, dict]:
    """
    Write a versioned datasheet record. Thread/process safe via file lock.

    Dedup: if idempotency_key already exists for this PN, skip write.
    Atomic: v{N}.json written BEFORE index.json update.
    Version assignment happens INSIDE the lock to prevent race conditions.

    Args:
        auto_version: if True, ignore record_dict["version"] and assign
            next version number inside the lock (prevents same-PN races).

    Returns path to written version file.
    Raises ValueError if dedup match found.
    """
    pn = record_dict["pn"]
    idem_key = record_dict.get("idempotency_key", "")

    pn_dir = get_pn_dir(base_dir, pn)

    # Global lock (base_dir level) — serialises all PNs. Acceptable for
    # current scale (<500 PNs, max ~5 versions each). For bulk migration
    # the bottleneck is I/O, not lock contention.
    with _file_lock(base_dir, trace_id=trace_id):
        # Dedup check under lock — no TOCTOU race
        if idem_key:
            existing = _find_by_idempotency_key(base_dir, pn, idem_key, trace_id=trace_id)
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

        # Version assignment inside lock — prevents same-PN race
        if auto_version:
            index = _load_index(base_dir, trace_id=trace_id)
            latest = index.get(pn, {}).get("latest_version", 0)
            version = latest + 1
            record_dict = {**record_dict, "version": version}
            if record_dict.get("supersedes") is None and latest > 0:
                record_dict["supersedes"] = latest
        else:
            version = record_dict["version"]

        # Write version file first (before index)
        version_path = pn_dir / f"v{version}.json"
        _atomic_write(
            version_path,
            json.dumps(record_dict, indent=2, ensure_ascii=False),
        )

        # Update index after version file is safely written
        if not auto_version:
            index = _load_index(base_dir, trace_id=trace_id)
        # Count actual version files on disk (not version number — may differ
        # for non-sequential manual writes).
        actual_count = len(list(pn_dir.glob("v*.json"))) if pn_dir.exists() else 1
        index[pn] = {
            "latest_version": version,
            "version_count": actual_count,
            "last_updated": record_dict.get("ingested_at", ""),
        }
        _save_index(base_dir, index)

    _structured_log(
        trace_id, "version_written",
        pn=pn, version=version,
        spec_count=len(record_dict.get("specs", {})),
    )
    return version_path, version, record_dict


def read_version(base_dir: Path, pn: str, version: int, trace_id: str = "") -> dict | None:
    """Read a specific version. Returns None if not found."""
    path = get_pn_dir(base_dir, pn) / f"v{version}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _structured_log(
            trace_id, "version_read_error",
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
    base_dir: Path, pn: str, idem_key: str, trace_id: str = "",
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
        except (json.JSONDecodeError, OSError) as exc:
            _structured_log(
                trace_id, "dedup_scan_corrupt_file",
                error_class="TRANSIENT", severity="WARNING", retriable=True,
                pn=pn, file=vfile.name, error=str(exc),
            )
            continue
    return None
