"""
test_download_documents.py — Deterministic tests for download_documents.py.
No real HTTP calls, no file system side effects outside tmp_path.
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import download_documents as dd


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_dirs(tmp_path):
    orig_results = dd.RESULTS_DIR
    orig_evidence = dd.EVIDENCE_DIR
    orig_docs = dd.DOCS_DIR

    dd.RESULTS_DIR = tmp_path / "research_results"
    dd.EVIDENCE_DIR = tmp_path / "evidence"
    dd.DOCS_DIR = tmp_path / "documents"
    dd.RESULTS_DIR.mkdir()
    dd.EVIDENCE_DIR.mkdir()

    yield tmp_path

    dd.RESULTS_DIR = orig_results
    dd.EVIDENCE_DIR = orig_evidence
    dd.DOCS_DIR = orig_docs


def _write_result(pn: str, documents: list[dict] | None = None, **kwargs):
    pn_safe = dd._safe_filename(pn)
    fr = {"identity_confirmed": True, "title_ru": f"Product {pn}"}
    if documents is not None:
        fr["documents"] = documents
    data = {"entity_id": pn, "final_recommendation": fr, **kwargs}
    (dd.RESULTS_DIR / f"result_{pn_safe}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def _write_evidence(pn: str, **extra):
    pn_safe = dd._safe_filename(pn)
    data = {"pn": pn, "brand": "Honeywell", **extra}
    (dd.EVIDENCE_DIR / f"evidence_{pn_safe}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# _safe_filename
# ---------------------------------------------------------------------------

class TestSafeFilename:
    def test_slashes_replaced(self):
        assert "/" not in dd._safe_filename("129464N/U")
        assert dd._safe_filename("129464N/U") == "129464N_U"

    def test_normal_pn_unchanged(self):
        assert dd._safe_filename("V5011R1000") == "V5011R1000"

    def test_dots_preserved(self):
        assert dd._safe_filename("010130.10") == "010130.10"


# ---------------------------------------------------------------------------
# _guess_extension
# ---------------------------------------------------------------------------

class TestGuessExtension:
    def test_pdf_url(self):
        assert dd._guess_extension("https://example.com/doc.pdf") == ".pdf"

    def test_png_url(self):
        assert dd._guess_extension("https://example.com/image.png") == ".png"

    def test_jpg_url(self):
        assert dd._guess_extension("https://example.com/photo.jpg") == ".jpg"

    def test_content_type_pdf(self):
        assert dd._guess_extension("https://example.com/file", "application/pdf") == ".pdf"

    def test_default_is_pdf(self):
        assert dd._guess_extension("https://example.com/unknown") == ".pdf"


# ---------------------------------------------------------------------------
# collect_doc_urls
# ---------------------------------------------------------------------------

class TestCollectDocUrls:
    def test_from_documents_list(self):
        result = {
            "final_recommendation": {
                "documents": [
                    {"url": "https://example.com/ds.pdf", "doc_type": "Datasheet", "language": "en"},
                    {"url": "https://example.com/manual.pdf", "doc_type": "Installation Manual", "language": "de"},
                ]
            }
        }
        docs = dd.collect_doc_urls(result)
        assert len(docs) == 2
        assert docs[0]["doc_type"] == "Datasheet"
        assert docs[1]["doc_type"] == "Installation Manual"

    def test_deduplication(self):
        result = {
            "final_recommendation": {
                "documents": [
                    {"url": "https://example.com/ds.pdf", "doc_type": "Datasheet"},
                    {"url": "https://example.com/ds.pdf", "doc_type": "Datasheet"},
                ]
            }
        }
        docs = dd.collect_doc_urls(result)
        assert len(docs) == 1

    def test_from_datasheet_url_field(self):
        result = {
            "final_recommendation": {
                "datasheet_url": "https://example.com/spec.pdf"
            }
        }
        docs = dd.collect_doc_urls(result)
        assert len(docs) == 1
        assert docs[0]["doc_type"] == "Datasheet"

    def test_invalid_url_skipped(self):
        result = {
            "final_recommendation": {
                "documents": [
                    {"url": "Not found", "doc_type": "Datasheet"},
                    {"url": "https://example.com/real.pdf", "doc_type": "Datasheet"},
                ]
            }
        }
        docs = dd.collect_doc_urls(result)
        assert len(docs) == 1

    def test_empty_result(self):
        assert dd.collect_doc_urls({}) == []
        assert dd.collect_doc_urls({"final_recommendation": {}}) == []


# ---------------------------------------------------------------------------
# download_file (mocked)
# ---------------------------------------------------------------------------

class TestDownloadFile:
    def test_invalid_url_skipped(self, tmp_path):
        result = dd.download_file("not-a-url", tmp_path / "out")
        assert result["status"] == "skip"

    def test_404_returns_not_found(self, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("download_documents.requests.get", return_value=mock_resp):
            result = dd.download_file("https://example.com/doc.pdf", tmp_path / "out")
        assert result["status"] == "not_found"

    def test_403_returns_blocked(self, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        with patch("download_documents.requests.get", return_value=mock_resp):
            result = dd.download_file("https://example.com/doc.pdf", tmp_path / "out")
        assert result["status"] == "blocked"

    def test_small_file_skipped(self, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/pdf"}
        mock_resp.iter_content = lambda chunk_size: [b"tiny"]
        with patch("download_documents.requests.get", return_value=mock_resp):
            result = dd.download_file("https://example.com/doc.pdf", tmp_path / "out")
        assert result["status"] == "skip"
        assert "small" in result["reason"]

    def test_successful_download(self, tmp_path):
        fake_pdf = b"%PDF-1.4 " + b"X" * 10000
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/pdf"}
        mock_resp.iter_content = lambda chunk_size: [fake_pdf]
        with patch("download_documents.requests.get", return_value=mock_resp):
            result = dd.download_file(
                "https://example.com/doc.pdf",
                tmp_path / "doc"
            )
        assert result["status"] == "downloaded"
        assert result["size_bytes"] == len(fake_pdf)
        assert (tmp_path / "doc.pdf").exists()


# ---------------------------------------------------------------------------
# process_one
# ---------------------------------------------------------------------------

class TestProcessOne:
    def test_no_result_returns_no_result(self):
        status = dd.process_one("NONEXISTENT")
        assert status["action"] == "no_result"

    def test_no_docs_returns_no_docs(self):
        _write_result("ABC123")
        _write_evidence("ABC123")
        status = dd.process_one("ABC123")
        assert status["action"] == "no_docs"

    def test_dry_run_does_not_download(self):
        _write_result("V5011", documents=[
            {"url": "https://example.com/ds.pdf", "doc_type": "Datasheet"}
        ])
        _write_evidence("V5011")
        with patch("download_documents.download_file") as mock_dl:
            status = dd.process_one("V5011", dry_run=True)
        mock_dl.assert_not_called()
        assert any(d["status"] == "dry_run" for d in status["docs"])

    def test_downloaded_doc_written_to_evidence(self, tmp_path):
        fake_pdf = b"%PDF-1.4 " + b"X" * 10000
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/pdf"}
        mock_resp.iter_content = lambda chunk_size: [fake_pdf]

        _write_result("V5011", documents=[
            {"url": "https://example.com/ds.pdf", "doc_type": "Datasheet", "language": "en"}
        ])
        _write_evidence("V5011")

        with patch("download_documents.requests.get", return_value=mock_resp):
            status = dd.process_one("V5011")

        assert status["action"] == "processed"
        ev = json.loads((dd.EVIDENCE_DIR / "evidence_V5011.json").read_text("utf-8"))
        assert len(ev.get("documents", [])) == 1
        assert ev["documents"][0]["doc_type"] == "Datasheet"
        assert ev["documents"][0]["status"] == "downloaded"

    def test_already_downloaded_not_duplicated(self, tmp_path):
        _write_result("V5011", documents=[
            {"url": "https://example.com/ds.pdf", "doc_type": "Datasheet"}
        ])
        _write_evidence("V5011", **{
            "documents": [{"url": "https://example.com/ds.pdf", "doc_type": "Datasheet", "status": "downloaded"}]
        })
        with patch("download_documents.download_file") as mock_dl:
            status = dd.process_one("V5011")
        mock_dl.assert_not_called()


# ---------------------------------------------------------------------------
# run (batch)
# ---------------------------------------------------------------------------

class TestRunBatch:
    def test_empty_results_dir(self):
        stats = dd.run()
        assert stats["total_pns"] == 0

    def test_pn_filter(self):
        _write_result("A1")
        _write_result("B2")
        _write_evidence("A1")
        _write_evidence("B2")
        stats = dd.run(pn_filter="A1")
        assert stats["total_pns"] == 1

    def test_limit(self):
        for pn in ("A1", "B2", "C3"):
            _write_result(pn)
            _write_evidence(pn)
        stats = dd.run(limit=2)
        assert stats["total_pns"] == 2

    def test_dry_run_flag(self):
        _write_result("X1", documents=[
            {"url": "https://example.com/ds.pdf", "doc_type": "Datasheet"}
        ])
        _write_evidence("X1")
        stats = dd.run(dry_run=True)
        assert stats["dry_run"] is True
