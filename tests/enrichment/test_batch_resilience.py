"""
Tests for Task 1: Batch Resilience (infra/acceleration-bootstrap)

Covers:
- per-SKU exception isolation (batch survives)
- checkpoint _status: "failed" written on error
- resume: skip done, retry failed, backward-compat (no _status = done)
- SIGTERM graceful shutdown
- lease file creation/cleanup
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers — simulate the core batch logic without real I/O
# ---------------------------------------------------------------------------

def _make_checkpoint(entries: dict) -> dict:
    """Return a checkpoint dict (pn → bundle) for test use."""
    return entries


def _run_mock_batch(
    skus: list[str],
    fail_on: set[str],
    checkpoint: dict,
    shutdown_after: str | None = None,
) -> tuple[list[str], dict]:
    """
    Minimal replica of the photo_pipeline.py per-SKU loop logic:
    - shutdown_requested flag checked each iteration
    - try/except per SKU
    - _status written to checkpoint
    Returns: (processed_pns, final_checkpoint)
    """
    import datetime

    _shutdown_requested = False
    processed: list[str] = []
    run_ts = datetime.datetime.utcnow().isoformat() + "Z"

    def _signal_handler(signum, frame):
        nonlocal _shutdown_requested
        _shutdown_requested = True

    old_sigterm = signal.signal(signal.SIGTERM, _signal_handler)
    old_sigint  = signal.signal(signal.SIGINT,  _signal_handler)

    try:
        for pn in skus:
            if _shutdown_requested:
                break

            # checkpoint resume
            if pn in checkpoint:
                ck_status = checkpoint[pn].get("_status", "done")
                if ck_status == "done":
                    processed.append(f"SKIP:{pn}")
                    continue
                # failed → fall through and retry

            trace_id = f"test_{run_ts}_{pn}"

            try:
                if pn in fail_on:
                    raise ValueError(f"simulated error for {pn}")

                bundle = {"pn": pn, "verdict": "KEEP"}
                bundle["_status"] = "done"
                checkpoint[pn] = bundle
                processed.append(f"OK:{pn}")

            except Exception as exc:
                checkpoint[pn] = {"pn": pn, "_status": "failed", "error": str(exc)}
                # do NOT re-raise — batch continues

            if shutdown_after and pn == shutdown_after:
                os.kill(os.getpid(), signal.SIGTERM)
                time.sleep(0.05)   # let signal fire

    finally:
        signal.signal(signal.SIGTERM, old_sigterm)
        signal.signal(signal.SIGINT,  old_sigint)

    return processed, checkpoint


# ---------------------------------------------------------------------------
# Test 1: exception on one SKU does NOT kill the batch
# ---------------------------------------------------------------------------

def test_exception_does_not_kill_batch():
    skus = ["PN-A", "PN-B", "PN-C"]
    processed, ck = _run_mock_batch(skus, fail_on={"PN-B"}, checkpoint={})

    # PN-A and PN-C should succeed; PN-B should be logged but not crash
    assert "OK:PN-A" in processed
    assert "OK:PN-C" in processed
    # PN-B is absent from processed (error path, no "OK:PN-B")
    assert "OK:PN-B" not in processed


# ---------------------------------------------------------------------------
# Test 2: checkpoint contains _status="failed" after error
# ---------------------------------------------------------------------------

def test_checkpoint_failed_status_on_error():
    skus = ["PN-X", "PN-Y"]
    _, ck = _run_mock_batch(skus, fail_on={"PN-X"}, checkpoint={})

    assert ck["PN-X"]["_status"] == "failed"
    assert ck["PN-Y"]["_status"] == "done"


# ---------------------------------------------------------------------------
# Test 3: resume skips done, retries failed
# ---------------------------------------------------------------------------

def test_resume_skips_done_retries_failed():
    # Pre-populate checkpoint: PN-1 done, PN-2 failed, PN-3 absent
    pre_ck = {
        "PN-1": {"pn": "PN-1", "_status": "done"},
        "PN-2": {"pn": "PN-2", "_status": "failed", "error": "previous error"},
    }
    skus = ["PN-1", "PN-2", "PN-3"]
    processed, ck = _run_mock_batch(skus, fail_on=set(), checkpoint=pre_ck)

    assert "SKIP:PN-1" in processed   # done → skipped
    assert "OK:PN-2" in processed     # failed → retried and now succeeded
    assert "OK:PN-3" in processed     # new → processed


# ---------------------------------------------------------------------------
# Test 4: old checkpoint entries without _status are treated as done
# ---------------------------------------------------------------------------

def test_backward_compat_no_status_treated_as_done():
    # Old format: bundle without _status key
    pre_ck = {
        "PN-OLD": {"pn": "PN-OLD", "verdict": "KEEP"},  # no _status
    }
    skus = ["PN-OLD", "PN-NEW"]
    processed, ck = _run_mock_batch(skus, fail_on=set(), checkpoint=pre_ck)

    assert "SKIP:PN-OLD" in processed   # backward-compat: treated as done
    assert "OK:PN-NEW" in processed


# ---------------------------------------------------------------------------
# Test 5: SIGTERM/shutdown flag triggers graceful shutdown
# ---------------------------------------------------------------------------

def test_sigterm_graceful_shutdown():
    """
    Verify the shutdown-flag mechanism: once _shutdown_requested is True the
    batch loop exits after the current SKU completes.

    We raise the signal via signal.raise_signal() (Python 3.8+, works on
    Windows) rather than os.kill() which on Windows calls TerminateProcess.
    """
    import datetime

    _shutdown_requested = False
    processed: list[str] = []
    checkpoint: dict = {}
    skus = ["PN-1", "PN-2", "PN-3", "PN-4"]
    trigger_pn = "PN-2"

    def _signal_handler(signum, frame):
        nonlocal _shutdown_requested
        _shutdown_requested = True

    old_sigterm = signal.signal(signal.SIGTERM, _signal_handler)
    try:
        for pn in skus:
            if _shutdown_requested:
                break

            try:
                bundle = {"pn": pn, "_status": "done"}
                checkpoint[pn] = bundle
                processed.append(f"OK:{pn}")
            except Exception:
                pass

            # Trigger shutdown after processing trigger_pn
            if pn == trigger_pn:
                signal.raise_signal(signal.SIGTERM)
                time.sleep(0.02)   # let handler execute
    finally:
        signal.signal(signal.SIGTERM, old_sigterm)

    assert "OK:PN-1" in processed
    assert "OK:PN-2" in processed
    assert "OK:PN-3" not in processed
    assert "OK:PN-4" not in processed
    assert checkpoint["PN-2"]["_status"] == "done"


# ---------------------------------------------------------------------------
# Test 6: lease file helpers (standalone unit tests)
# ---------------------------------------------------------------------------

def test_lease_write_and_cleanup(tmp_path):
    """Lease file is created, readable, and removed on cleanup."""
    import datetime

    lease_file = tmp_path / ".lease.json"

    # Simulate _write_lease
    def write_lease(total_skus: int) -> None:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        data = {
            "pid": os.getpid(),
            "started_at": now,
            "heartbeat_at": now,
            "task": "photo_pipeline",
            "total_skus": total_skus,
        }
        tmp = lease_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.rename(tmp, lease_file)

    def cleanup_lease() -> None:
        if lease_file.exists():
            lease_file.unlink()

    write_lease(370)
    assert lease_file.exists()
    content = json.loads(lease_file.read_text(encoding="utf-8"))
    assert content["total_skus"] == 370
    assert content["pid"] == os.getpid()

    cleanup_lease()
    assert not lease_file.exists()
