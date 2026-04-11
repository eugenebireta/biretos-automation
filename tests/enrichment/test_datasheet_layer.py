"""
Tests for SS-1 Datasheet Layer Foundation.

Covers: schema, content hash, store, atomic write, ingestion, views, migration, concurrency.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.datasheet_layer.schema import (  # noqa: E402
    DatasheetRecord,
    compute_content_hash,
)
from scripts.datasheet_layer.store import (  # noqa: E402
    write_version,
    read_version,
    read_latest,
    list_all_pns,
    _atomic_write,
    _load_index,
)
from scripts.datasheet_layer.ingestion import (  # noqa: E402
    ingest_from_find_datasheet,
    ingest_from_evidence,
)
from scripts.datasheet_layer.views import (  # noqa: E402
    get_latest_datasheet,
    get_datasheet_by_version,
    get_specs,
    get_version_history,
    list_datasheets,
    get_from_legacy_evidence,
)
from scripts.datasheet_layer.migrate import migrate_all  # noqa: E402


def _make_record(pn="TEST-001", version=1, content_hash="abc123", **kwargs):
    """Helper to create a DatasheetRecord with sensible defaults."""
    defaults = dict(
        pn=pn,
        brand="TestBrand",
        version=version,
        trace_id="test_trace",
        source_id="https://example.com/test.pdf",
        source_tier="manufacturer",
        content_hash=content_hash,
        ingested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return DatasheetRecord(**defaults)


def _make_record_dict(pn="TEST-001", version=1, content_hash="abc123", **kwargs):
    """Helper to create a record dict for store operations."""
    r = _make_record(pn=pn, version=version, content_hash=content_hash, **kwargs)
    return r.model_dump_json_safe()


# =============================================================================
# TestDatasheetRecord
# =============================================================================

class TestDatasheetRecord:
    def test_create_valid_record(self):
        r = _make_record()
        assert r.pn == "TEST-001"
        assert r.brand == "TestBrand"
        assert r.version == 1
        assert r.schema_version == 1
        assert r.idempotency_key == "TEST-001:abc123"

    def test_auto_idempotency_key(self):
        r = _make_record(content_hash="deadbeef")
        assert r.idempotency_key == "TEST-001:deadbeef"

    def test_explicit_idempotency_key(self):
        r = _make_record(idempotency_key="custom_key")
        assert r.idempotency_key == "custom_key"

    def test_model_dump_json_safe(self):
        r = _make_record()
        d = r.model_dump_json_safe()
        assert isinstance(d, dict)
        assert isinstance(d["ingested_at"], str)
        # Should be ISO format
        datetime.fromisoformat(d["ingested_at"])

    def test_version_validation(self):
        import pytest
        with pytest.raises(Exception):
            _make_record(version=0)

    def test_empty_pn_rejected(self):
        import pytest
        with pytest.raises(ValueError, match="pn must not be empty"):
            _make_record(pn="")

    def test_empty_content_hash_rejected(self):
        import pytest
        with pytest.raises(ValueError, match="content_hash must not be empty"):
            _make_record(content_hash="")

    def test_defaults(self):
        r = _make_record()
        assert r.pn_confirmed is False
        assert r.num_pages == 0
        assert r.specs == {}
        assert r.text_excerpt == ""
        assert r.supersedes is None


# =============================================================================
# TestContentHash
# =============================================================================

class TestContentHash:
    def test_deterministic(self):
        h1 = compute_content_hash(b"hello world")
        h2 = compute_content_hash(b"hello world")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_different_content(self):
        h1 = compute_content_hash(b"hello")
        h2 = compute_content_hash(b"world")
        assert h1 != h2


# =============================================================================
# TestStore
# =============================================================================

class TestStore:
    def test_write_and_read(self, tmp_path):
        rec = _make_record_dict()
        write_version(tmp_path, rec, trace_id="test")
        result = read_version(tmp_path, "TEST-001", 1)
        assert result is not None
        assert result["pn"] == "TEST-001"
        assert result["version"] == 1

    def test_read_latest(self, tmp_path):
        write_version(tmp_path, _make_record_dict(version=1, content_hash="aaa"), trace_id="test")
        write_version(tmp_path, _make_record_dict(version=2, content_hash="bbb"), trace_id="test")
        result = read_latest(tmp_path, "TEST-001")
        assert result is not None
        assert result["version"] == 2

    def test_list_all_pns(self, tmp_path):
        write_version(tmp_path, _make_record_dict(pn="PN-A", content_hash="a1"), trace_id="test")
        write_version(tmp_path, _make_record_dict(pn="PN-B", content_hash="b1"), trace_id="test")
        pns = list_all_pns(tmp_path)
        assert pns == ["PN-A", "PN-B"]

    def test_dedup_raises(self, tmp_path):
        import pytest
        rec = _make_record_dict()
        write_version(tmp_path, rec, trace_id="test")
        with pytest.raises(ValueError, match="Duplicate"):
            write_version(tmp_path, rec, trace_id="test")

    def test_read_nonexistent(self, tmp_path):
        assert read_version(tmp_path, "NOPE", 1) is None

    def test_read_latest_empty(self, tmp_path):
        assert read_latest(tmp_path, "NOPE") is None

    def test_index_updated(self, tmp_path):
        write_version(tmp_path, _make_record_dict(), trace_id="test")
        index = _load_index(tmp_path)
        assert "TEST-001" in index
        assert index["TEST-001"]["latest_version"] == 1


# =============================================================================
# TestAtomicWrite
# =============================================================================

class TestAtomicWrite:
    def test_create_file(self, tmp_path):
        target = tmp_path / "test.json"
        _atomic_write(target, '{"key": "value"}')
        assert target.exists()
        assert json.loads(target.read_text()) == {"key": "value"}

    def test_overwrite_file(self, tmp_path):
        target = tmp_path / "test.json"
        _atomic_write(target, '{"v": 1}')
        _atomic_write(target, '{"v": 2}')
        assert json.loads(target.read_text()) == {"v": 2}


# =============================================================================
# TestIngestion
# =============================================================================

class TestIngestion:
    def test_ingest_found(self, tmp_path):
        result = ingest_from_find_datasheet(
            pn="ING-001",
            brand="TestBrand",
            find_result={
                "datasheet_status": "found",
                "pdf_url": "https://example.com/ds.pdf",
                "pdf_source_tier": "manufacturer",
            },
            pdf_bytes=b"fake pdf content",
            trace_id="test",
            base_dir=tmp_path,
        )
        assert result is not None
        assert result.pn == "ING-001"
        assert result.version == 1
        assert result.content_hash != "no_content"

    def test_ingest_not_found(self, tmp_path):
        result = ingest_from_find_datasheet(
            pn="ING-002",
            brand="TestBrand",
            find_result={"datasheet_status": "not_found"},
            trace_id="test",
            base_dir=tmp_path,
        )
        assert result is None

    def test_ingest_dedup(self, tmp_path):
        kwargs = dict(
            pn="ING-003",
            brand="TestBrand",
            find_result={
                "datasheet_status": "found",
                "pdf_url": "https://example.com/ds.pdf",
                "pdf_source_tier": "manufacturer",
            },
            pdf_bytes=b"same content",
            trace_id="test",
            base_dir=tmp_path,
        )
        r1 = ingest_from_find_datasheet(**kwargs)
        r2 = ingest_from_find_datasheet(**kwargs)
        assert r1 is not None
        assert r2 is None  # dedup

    def test_ingest_new_version(self, tmp_path):
        base = dict(
            pn="ING-004",
            brand="TestBrand",
            find_result={
                "datasheet_status": "found",
                "pdf_url": "https://example.com/ds.pdf",
                "pdf_source_tier": "manufacturer",
            },
            trace_id="test",
            base_dir=tmp_path,
        )
        r1 = ingest_from_find_datasheet(**base, pdf_bytes=b"version 1")
        r2 = ingest_from_find_datasheet(**base, pdf_bytes=b"version 2")
        assert r1 is not None
        assert r2 is not None
        # C1 fix: returned record must have correct version, not placeholder
        assert r1.version == 1
        assert r2.version == 2
        assert r2.supersedes == 1
        # Verify stored data matches
        stored_v1 = read_version(tmp_path, "ING-004", 1)
        stored_v2 = read_version(tmp_path, "ING-004", 2)
        assert stored_v1 is not None
        assert stored_v2 is not None
        assert stored_v2["supersedes"] == 1

    def test_ingest_from_evidence(self, tmp_path):
        # Create a local PDF file so content hash can be computed
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"fake evidence pdf")
        evidence = {
            "entity_id": "EV-001",
            "brand": "EvidenceBrand",
            "datasheet": {
                "datasheet_status": "found",
                "pdf_url": "https://example.com/ev.pdf",
                "pdf_source_tier": "distributor",
                "pdf_local_path": str(pdf_path),
            },
        }
        result = ingest_from_evidence(evidence, trace_id="test", base_dir=tmp_path)
        assert result is not None
        assert result.pn == "EV-001"

    def test_ingest_from_evidence_skip(self, tmp_path):
        evidence = {
            "entity_id": "EV-002",
            "datasheet": {"datasheet_status": "not_found"},
        }
        result = ingest_from_evidence(evidence, trace_id="test", base_dir=tmp_path)
        assert result is None


# =============================================================================
# TestViews
# =============================================================================

class TestViews:
    def _setup_store(self, tmp_path):
        """Write two versions for testing."""
        ingest_from_find_datasheet(
            pn="VIEW-001", brand="ViewBrand",
            find_result={
                "datasheet_status": "found",
                "pdf_url": "https://example.com/v1.pdf",
                "pdf_source_tier": "manufacturer",
                "pdf_specs": {"voltage": "24V"},
            },
            pdf_bytes=b"pdf v1",
            trace_id="test",
            base_dir=tmp_path,
        )
        ingest_from_find_datasheet(
            pn="VIEW-001", brand="ViewBrand",
            find_result={
                "datasheet_status": "found",
                "pdf_url": "https://example.com/v2.pdf",
                "pdf_source_tier": "manufacturer",
                "pdf_specs": {"voltage": "24V", "current": "2A"},
            },
            pdf_bytes=b"pdf v2",
            trace_id="test",
            base_dir=tmp_path,
        )

    def test_get_latest(self, tmp_path):
        self._setup_store(tmp_path)
        result = get_latest_datasheet("VIEW-001", base_dir=tmp_path)
        assert result is not None
        assert result["version"] == 2

    def test_get_by_version(self, tmp_path):
        self._setup_store(tmp_path)
        result = get_datasheet_by_version("VIEW-001", 1, base_dir=tmp_path)
        assert result is not None
        assert result["version"] == 1

    def test_get_specs(self, tmp_path):
        self._setup_store(tmp_path)
        specs = get_specs("VIEW-001", base_dir=tmp_path)
        assert "voltage" in specs
        assert "current" in specs

    def test_get_specs_missing(self, tmp_path):
        specs = get_specs("NOPE", base_dir=tmp_path)
        assert specs == {}

    def test_version_history(self, tmp_path):
        self._setup_store(tmp_path)
        history = get_version_history("VIEW-001", base_dir=tmp_path)
        assert len(history) == 2
        assert history[0]["version"] == 1
        assert history[1]["version"] == 2
        assert history[1]["supersedes"] == 1

    def test_list_datasheets(self, tmp_path):
        self._setup_store(tmp_path)
        pns = list_datasheets(base_dir=tmp_path)
        assert "VIEW-001" in pns

    def test_legacy_evidence(self):
        evidence = {
            "datasheet": {
                "datasheet_status": "found",
                "pdf_url": "https://example.com/legacy.pdf",
            }
        }
        result = get_from_legacy_evidence(evidence)
        assert result is not None
        assert result["pdf_url"] == "https://example.com/legacy.pdf"

    def test_legacy_evidence_skip(self):
        evidence = {"datasheet": {"datasheet_status": "not_found"}}
        result = get_from_legacy_evidence(evidence)
        assert result is None


# =============================================================================
# TestMigrate
# =============================================================================

class TestMigrate:
    def test_migrate_basic(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        ds_dir = tmp_path / "datasheets"

        # Create a real PDF file for content hash (W7: no sentinel values)
        pdf_file = tmp_path / "mig_test.pdf"
        pdf_file.write_bytes(b"migrate test pdf content")

        evidence = {
            "entity_id": "MIG-001",
            "brand": "MigBrand",
            "datasheet": {
                "datasheet_status": "found",
                "pdf_url": "https://example.com/mig.pdf",
                "pdf_source_tier": "manufacturer",
                "pdf_local_path": str(pdf_file),
            },
        }
        (evidence_dir / "evidence_001.json").write_text(
            json.dumps(evidence), encoding="utf-8"
        )

        stats = migrate_all(evidence_dir=evidence_dir, base_dir=ds_dir)
        assert stats["scanned"] == 1
        assert stats["found"] == 1
        assert stats["ingested"] == 1
        assert stats["errors"] == 0

    def test_migrate_idempotent(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        ds_dir = tmp_path / "datasheets"

        # Create a real PDF file for content hash (W7: no sentinel values)
        pdf_file = tmp_path / "mig_test2.pdf"
        pdf_file.write_bytes(b"migrate idempotent pdf")

        evidence = {
            "entity_id": "MIG-002",
            "brand": "MigBrand",
            "datasheet": {
                "datasheet_status": "found",
                "pdf_url": "https://example.com/mig2.pdf",
                "pdf_source_tier": "manufacturer",
                "pdf_local_path": str(pdf_file),
            },
        }
        (evidence_dir / "evidence_002.json").write_text(
            json.dumps(evidence), encoding="utf-8"
        )

        stats1 = migrate_all(evidence_dir=evidence_dir, base_dir=ds_dir)
        stats2 = migrate_all(evidence_dir=evidence_dir, base_dir=ds_dir)
        assert stats1["ingested"] == 1
        assert stats2["ingested"] == 0
        assert stats2["dedup_skipped"] == 1

    def test_migrate_dry_run_with_pdf(self, tmp_path):
        """Dry run with pdf_local_path counts as ingested."""
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        ds_dir = tmp_path / "datasheets"

        pdf_file = tmp_path / "dry_run.pdf"
        pdf_file.write_bytes(b"dry run pdf")

        evidence = {
            "entity_id": "MIG-003",
            "brand": "MigBrand",
            "datasheet": {
                "datasheet_status": "found",
                "pdf_url": "https://example.com/mig3.pdf",
                "pdf_source_tier": "manufacturer",
                "pdf_local_path": str(pdf_file),
            },
        }
        (evidence_dir / "evidence_003.json").write_text(
            json.dumps(evidence), encoding="utf-8"
        )

        stats = migrate_all(evidence_dir=evidence_dir, base_dir=ds_dir, dry_run=True)
        assert stats["ingested"] == 1
        assert stats["dedup_skipped"] == 0
        assert stats["errors"] == 0
        # Verify nothing was actually written
        assert not ds_dir.exists() or not list(ds_dir.glob("*/v*.json"))

    def test_migrate_dry_run_no_pdf_skips(self, tmp_path):
        """Dry run without pdf_local_path counts as skipped (mirrors real behavior)."""
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        ds_dir = tmp_path / "datasheets"

        evidence = {
            "entity_id": "MIG-004",
            "brand": "MigBrand",
            "datasheet": {
                "datasheet_status": "found",
                "pdf_url": "https://example.com/mig4.pdf",
                "pdf_source_tier": "manufacturer",
            },
        }
        (evidence_dir / "evidence_004.json").write_text(
            json.dumps(evidence), encoding="utf-8"
        )

        stats = migrate_all(evidence_dir=evidence_dir, base_dir=ds_dir, dry_run=True)
        assert stats["ingested"] == 0
        assert stats["no_content"] == 1  # no pdf = cannot compute hash

    def test_migrate_no_evidence_dir(self, tmp_path):
        stats = migrate_all(
            evidence_dir=tmp_path / "nonexistent",
            base_dir=tmp_path / "datasheets",
        )
        assert stats["scanned"] == 0


# =============================================================================
# TestConcurrency
# =============================================================================

class TestConcurrency:
    def test_concurrent_writes_different_pns(self, tmp_path):
        """Concurrent writes to different PNs should not interfere."""
        errors = []

        def write_pn(pn, hash_val):
            try:
                ingest_from_find_datasheet(
                    pn=pn,
                    brand="ConcBrand",
                    find_result={
                        "datasheet_status": "found",
                        "pdf_url": f"https://example.com/{pn}.pdf",
                        "pdf_source_tier": "manufacturer",
                    },
                    pdf_bytes=hash_val.encode(),
                    trace_id="conc_test",
                    base_dir=tmp_path,
                )
            except Exception as exc:
                errors.append(str(exc))

        threads = [
            threading.Thread(target=write_pn, args=(f"CONC-{i:03d}", f"content_{i}"))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Errors during concurrent writes: {errors}"
        pns = list_all_pns(tmp_path)
        assert len(pns) == 5


# =============================================================================
# TestErrorPaths
# =============================================================================

class TestErrorPaths:
    def test_lock_timeout_raises(self, tmp_path):
        """Lock timeout must raise TimeoutError, not proceed unlocked.

        Lock file is touched with recent mtime so stale-lock detection
        does NOT remove it (stale threshold is 60s).
        """
        import pytest
        from scripts.datasheet_layer.store import _file_lock

        # Create a fresh lock file — recent mtime means NOT stale
        lock_path = tmp_path / ".datasheet_store.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        import os
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)

        with pytest.raises(TimeoutError, match="lock acquisition timed out"):
            with _file_lock(tmp_path, timeout=0.2, trace_id="test_timeout"):
                pass  # should never reach here
        # Clean up
        lock_path.unlink(missing_ok=True)

    def test_stale_lock_auto_removed(self, tmp_path):
        """Lock file older than threshold must be auto-removed."""
        import os
        from scripts.datasheet_layer.store import _file_lock

        lock_path = tmp_path / ".datasheet_store.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("stale")
        # Backdate mtime to 120s ago
        old_time = os.path.getmtime(str(lock_path)) - 120
        os.utime(str(lock_path), (old_time, old_time))

        # Should acquire lock despite existing file (stale removal)
        with _file_lock(tmp_path, timeout=1.0, trace_id="test_stale"):
            pass  # success = stale lock was removed

    def test_index_load_error_raises(self, tmp_path):
        """Corrupt index.json must raise, not silently return empty dict."""
        import pytest
        from scripts.datasheet_layer.store import _load_index

        idx_path = tmp_path / "index.json"
        idx_path.write_text("NOT VALID JSON {{{", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            _load_index(tmp_path, trace_id="test_corrupt")

    def test_write_version_returns_stored_dict(self, tmp_path):
        """write_version must return the actual stored record_dict."""
        rec = _make_record_dict(content_hash="ret_test")
        _, version, stored = write_version(tmp_path, rec, trace_id="test")
        assert version == 1
        assert stored["pn"] == "TEST-001"
        assert stored["version"] == 1

    def test_auto_version_returns_correct_dict(self, tmp_path):
        """auto_version must return dict with assigned version, not placeholder."""
        rec = _make_record_dict(version=1, content_hash="auto_v1")
        _, v1, d1 = write_version(
            tmp_path, rec, trace_id="test", auto_version=True,
        )
        assert v1 == 1
        assert d1["version"] == 1

        rec2 = _make_record_dict(version=1, content_hash="auto_v2")
        _, v2, d2 = write_version(
            tmp_path, rec2, trace_id="test", auto_version=True,
        )
        assert v2 == 2
        assert d2["version"] == 2
        assert d2["supersedes"] == 1
