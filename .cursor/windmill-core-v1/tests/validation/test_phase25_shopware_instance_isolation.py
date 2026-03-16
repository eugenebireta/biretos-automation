from __future__ import annotations

import hashlib
import hmac
import importlib
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


_ROOT = Path(__file__).resolve().parents[2]
_WORKERS = _ROOT / "workers"
for _p in (_ROOT, _WORKERS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

orch = importlib.import_module("shopware_sync_orchestrator")


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


def _import_webhook_main_isolated(config_stub: _ConfigStub, monkeypatch) -> ModuleType:
    webhook_dir = _ROOT / "webhook_service"
    if str(webhook_dir) not in sys.path:
        sys.path.insert(0, str(webhook_dir))

    import config as config_pkg

    monkeypatch.setattr(config_pkg, "get_config", lambda: config_stub, raising=True)
    module_name = "_validation_shopware_webhook_main_isolation"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, webhook_dir / "main.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to import webhook_service/main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_orchestrator_requires_instance_specific_credentials(monkeypatch):
    monkeypatch.setattr(
        orch,
        "get_config",
        lambda: type(
            "Cfg",
            (),
            {
                "shopware_timeout_seconds": 10,
                "shopware_enable_dry_run": True,
                "shopware_url": "",
                "shopware_client_id": "",
                "shopware_client_secret": "",
            },
        )(),
        raising=True,
    )
    monkeypatch.delenv("SHOPWARE_RU_URL", raising=False)
    monkeypatch.delenv("SHOPWARE_RU_CLIENT_ID", raising=False)
    monkeypatch.delenv("SHOPWARE_RU_CLIENT_SECRET", raising=False)

    with pytest.raises(RuntimeError):
        orch._instance_config("ru")


def test_orchestrator_separates_ru_and_int_credentials(monkeypatch):
    monkeypatch.setattr(
        orch,
        "get_config",
        lambda: type(
            "Cfg",
            (),
            {"shopware_timeout_seconds": 10, "shopware_enable_dry_run": True},
        )(),
        raising=True,
    )
    monkeypatch.setenv("SHOPWARE_RU_URL", "https://ru.example")
    monkeypatch.setenv("SHOPWARE_RU_CLIENT_ID", "ru-id")
    monkeypatch.setenv("SHOPWARE_RU_CLIENT_SECRET", "ru-secret")
    monkeypatch.setenv("SHOPWARE_INT_URL", "https://int.example")
    monkeypatch.setenv("SHOPWARE_INT_CLIENT_ID", "int-id")
    monkeypatch.setenv("SHOPWARE_INT_CLIENT_SECRET", "int-secret")

    ru_cfg = orch._instance_config("ru")
    int_cfg = orch._instance_config("int")
    assert ru_cfg.shopware_url == "https://ru.example"
    assert int_cfg.shopware_url == "https://int.example"
    assert ru_cfg.shopware_client_id != int_cfg.shopware_client_id


def test_webhook_gateway_ignores_shared_secret_fallback(monkeypatch):
    monkeypatch.setenv("SHOPWARE_WEBHOOK_SECRET", "shared-secret")
    monkeypatch.delenv("SHOPWARE_WEBHOOK_SECRET_RU", raising=False)
    module = _import_webhook_main_isolated(_ConfigStub(), monkeypatch)

    body = b'{"event":"checkout.order.placed"}'
    signature = hmac.new(b"shared-secret", body, hashlib.sha256).hexdigest()
    assert not module._is_valid_shopware_signature("ru", body, signature)
