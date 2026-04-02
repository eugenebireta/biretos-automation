"""pdf_persistence.py — PDF download and persistent local storage.

Downloads PDFs found during enrichment, deduplicates by SHA-256 hash,
saves to /data/pdfs/{brand}/{pn}_{hash8}.pdf, returns metadata dict
for inclusion in evidence_bundle.json.

Phase A: pdf_pn_presence and pdf_exact_vs_family are set to None/"unclear"
— full OCR analysis is Phase B.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_DEFAULT_PDF_ROOT = Path(__file__).parent.parent / "data" / "pdfs"
_DOWNLOAD_TIMEOUT = 20  # seconds
_PDF_CONTENT_TYPES = {"application/pdf", "application/octet-stream"}


def download_pdf(
    url: str,
    brand: str,
    pn_primary: str,
    pdf_root: Path = _DEFAULT_PDF_ROOT,
    session=None,
) -> dict:
    """Download PDF, deduplicate by SHA-256, return metadata dict.

    Args:
        url:        Direct URL to PDF file.
        brand:      Brand slug for directory naming (e.g. "Honeywell").
        pn_primary: Primary PN for filename (e.g. "00020211").
        pdf_root:   Root directory for PDF storage.
        session:    Optional requests.Session (created if None).

    Returns dict with keys:
        pdf_path, pdf_source_url, pdf_source_domain, pdf_hash,
        pdf_pn_presence, pdf_exact_vs_family, pdf_revision,
        pdf_downloaded_at, pdf_already_existed.

    On download failure: returns empty metadata (pdf_path=None).
    """
    import requests  # deferred import — not needed in tests

    session = session or requests.Session()
    domain = _extract_domain(url)
    brand_slug = _slugify(brand)
    pn_slug = _slugify(pn_primary)

    pdf_dir = pdf_root / brand_slug
    try:
        pdf_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("Cannot create PDF dir %s: %s", pdf_dir, exc)
        return _empty_pdf_meta(url, domain)

    try:
        resp = session.get(
            url,
            timeout=_DOWNLOAD_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"},
            stream=True,
        )
        resp.raise_for_status()
        content = resp.content
    except Exception as exc:
        logger.warning("PDF download failed %s: %s", url, exc)
        return _empty_pdf_meta(url, domain)

    if not content:
        logger.warning("PDF empty response: %s", url)
        return _empty_pdf_meta(url, domain)

    sha256 = hashlib.sha256(content).hexdigest()
    hash8 = sha256[:8]
    pdf_path = pdf_dir / f"{pn_slug}_{hash8}.pdf"
    already_existed = pdf_path.exists()

    if not already_existed:
        pdf_path.write_bytes(content)
        logger.info("PDF saved: %s (%d bytes)", pdf_path, len(content))
    else:
        logger.debug("PDF already exists: %s", pdf_path)

    return {
        "pdf_path": str(pdf_path),
        "pdf_source_url": url,
        "pdf_source_domain": domain,
        "pdf_hash": f"sha256:{sha256}",
        "pdf_pn_presence": None,        # Phase B: OCR check
        "pdf_exact_vs_family": "unclear",  # Phase B: determined by OCR
        "pdf_revision": "unknown",
        "pdf_downloaded_at": datetime.now(timezone.utc).isoformat(),
        "pdf_already_existed": already_existed,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host.split(":")[0]


def _slugify(s: str) -> str:
    """Lowercase alphanumeric slug for filenames."""
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "unknown"


def _empty_pdf_meta(url: str, domain: str) -> dict:
    return {
        "pdf_path": None,
        "pdf_source_url": url,
        "pdf_source_domain": domain,
        "pdf_hash": None,
        "pdf_pn_presence": None,
        "pdf_exact_vs_family": "unclear",
        "pdf_revision": "unknown",
        "pdf_downloaded_at": datetime.now(timezone.utc).isoformat(),
        "pdf_already_existed": False,
    }
