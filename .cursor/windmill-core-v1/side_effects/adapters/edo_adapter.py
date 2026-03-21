"""
EDO (Electronic Document Operator) adapter. Phase 6.5 — scaffold only.

Providers: Сберкорус (sberkorus) and СБИС (sbis). Контур deferred.
All live calls are DRY_RUN=True until owner wires up live credentials.
No backoffice intents call this adapter in Phase 6.
"""

from __future__ import annotations

from uuid import uuid4
from typing import Any

import httpx

from domain.ports import (
    EDOPort,
    EDOSendRequest,
    EDOSendResponse,
    EDOStatusRequest,
    EDOStatusResponse,
)


# ---------------------------------------------------------------------------
# Сберкорус adapter (scaffold)
# ---------------------------------------------------------------------------

class SberkorpEDOAdapter(EDOPort):
    """
    Сберкорус EDO adapter.
    Live endpoint: https://edo.sberbank.ru/api/v1 (placeholder).
    All calls are dry_run until SBERKORP_EDO_API_KEY is set.
    """

    PROVIDER = "sberkorus"

    def __init__(self, *, api_url: str = "", api_key: str = "", dry_run: bool = True) -> None:
        self._api_url = api_url or "https://edo.sberbank.ru/api/v1"
        self._api_key = api_key
        self._dry_run = dry_run or not api_key

    def send_document(self, request: EDOSendRequest) -> EDOSendResponse:
        if self._dry_run:
            return EDOSendResponse(
                edo_document_id=f"SBKR-DRY-{uuid4().hex[:8].upper()}",
                provider=self.PROVIDER,
                raw_response={"dry_run": True, "document_type": request.document_type},
            )
        raise NotImplementedError("SberkorpEDOAdapter live mode not implemented yet")

    def get_document_status(self, request: EDOStatusRequest) -> EDOStatusResponse:
        if self._dry_run:
            return EDOStatusResponse(
                edo_document_id=request.edo_document_id,
                provider=self.PROVIDER,
                provider_status="dry_run_pending",
                raw_response={"dry_run": True},
            )
        raise NotImplementedError("SberkorpEDOAdapter live mode not implemented yet")


# ---------------------------------------------------------------------------
# СБИС adapter (scaffold)
# ---------------------------------------------------------------------------

class SBISEDOAdapter(EDOPort):
    """
    СБИС (Tensor) EDO adapter.
    Live endpoint: https://online.sbis.ru/service/ (placeholder).
    All calls are dry_run until SBIS_EDO_API_KEY is set.
    """

    PROVIDER = "sbis"

    def __init__(self, *, api_url: str = "", api_key: str = "", dry_run: bool = True) -> None:
        self._api_url = api_url or "https://online.sbis.ru/service/"
        self._api_key = api_key
        self._dry_run = dry_run or not api_key

    def send_document(self, request: EDOSendRequest) -> EDOSendResponse:
        if self._dry_run:
            return EDOSendResponse(
                edo_document_id=f"SBIS-DRY-{uuid4().hex[:8].upper()}",
                provider=self.PROVIDER,
                raw_response={"dry_run": True, "document_type": request.document_type},
            )
        raise NotImplementedError("SBISEDOAdapter live mode not implemented yet")

    def get_document_status(self, request: EDOStatusRequest) -> EDOStatusResponse:
        if self._dry_run:
            return EDOStatusResponse(
                edo_document_id=request.edo_document_id,
                provider=self.PROVIDER,
                provider_status="dry_run_pending",
                raw_response={"dry_run": True},
            )
        raise NotImplementedError("SBISEDOAdapter live mode not implemented yet")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, type] = {
    "sberkorus": SberkorpEDOAdapter,
    "sbis":      SBISEDOAdapter,
}


def get_edo_adapter(
    *,
    provider: str,
    api_url: str = "",
    api_key: str = "",
    dry_run: bool = True,
) -> EDOPort:
    """
    Returns an EDO adapter for the given provider.
    All adapters default to dry_run=True until live credentials are configured.
    """
    cls = _PROVIDERS.get(provider.lower())
    if cls is None:
        raise ValueError(
            f"Unknown EDO provider '{provider}'. Supported: {sorted(_PROVIDERS)}"
        )
    return cls(api_url=api_url, api_key=api_key, dry_run=dry_run)
