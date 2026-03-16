from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any


@dataclass
class _ConfigStub:
    telegram_webhook_secret: str = "telegram-secret"
    tbank_api_token: str = "tbank-secret"
    telegram_bot_token: str = "bot-token"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "biretos_automation"
    postgres_user: str = "biretos_user"
    postgres_password: str = "test"

    def __getattr__(self, _: str) -> Any:
        return None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _import_webhook_main_isolated(config_stub: _ConfigStub, monkeypatch) -> ModuleType:
    root = _project_root()
    webhook_dir = root / "webhook_service"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if str(webhook_dir) not in sys.path:
        sys.path.insert(0, str(webhook_dir))

    import config as config_pkg

    monkeypatch.setattr(config_pkg, "get_config", lambda: config_stub, raising=True)

    module_name = "_validation_shopware_webhook_main"
    sys.modules.pop(module_name, None)
    module_path = webhook_dir / "main.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to import webhook_service/main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shopware_signature_fail_closed_when_secret_missing(monkeypatch):
    monkeypatch.delenv("SHOPWARE_WEBHOOK_SECRET_RU", raising=False)
    monkeypatch.delenv("SHOPWARE_WEBHOOK_SECRET", raising=False)
    module = _import_webhook_main_isolated(_ConfigStub(), monkeypatch)
    assert not module._is_valid_shopware_signature("ru", b"{}", "abc")


def test_shopware_signature_accepts_valid_hmac(monkeypatch):
    secret = "shopware-secret"
    monkeypatch.setenv("SHOPWARE_WEBHOOK_SECRET_RU", secret)
    module = _import_webhook_main_isolated(_ConfigStub(), monkeypatch)
    payload = {"eventType": "checkout.order.placed", "orderNumber": "SW-1"}
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    assert module._is_valid_shopware_signature("ru", body, signature)


def test_extract_shopware_event_id_uses_header_first(monkeypatch):
    module = _import_webhook_main_isolated(_ConfigStub(), monkeypatch)
    event_id = module._extract_shopware_event_id(
        {"x-shopware-event-id": "evt-123"},
        {"eventId": "evt-body"},
        "checkout.order.placed",
    )
    assert event_id == "evt-123"
