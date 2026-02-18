from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Dict

from starlette.requests import Request


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
    ru_worker_poll_interval: int = 1
    llm_enabled_default: bool = False

    def __getattr__(self, _: str) -> Any:
        return None


def _project_root() -> Path:
    # tests/validation/test_*.py -> windmill-core-v1/
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

    module_name = "_validation_webhook_main_tier1"
    sys.modules.pop(module_name, None)
    module_path = webhook_dir / "main.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to import webhook_service/main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
def _build_request(headers: Dict[str, str]) -> Request:
    raw_headers = [(key.lower().encode("utf-8"), value.encode("utf-8")) for key, value in headers.items()]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test",
        "headers": raw_headers,
        "query_string": b"",
        "http_version": "1.1",
        "scheme": "http",
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8000),
    }
    return Request(scope)


def test_webhook_auth_fail_closed(monkeypatch):
    module = _import_webhook_main_isolated(_ConfigStub(), monkeypatch)

    assert not module._is_valid_telegram_secret(_build_request({}))
    assert not module._is_valid_telegram_secret(
        _build_request({"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"})
    )
    assert module._is_valid_telegram_secret(
        _build_request({"X-Telegram-Bot-Api-Secret-Token": "telegram-secret"})
    )

    assert not module._is_valid_tbank_token(_build_request({}))
    assert module._is_valid_tbank_token(_build_request({"X-Api-Token": "tbank-secret"}))
    assert module._is_valid_tbank_token(_build_request({"Authorization": "Bearer tbank-secret"}))


def test_webhook_auth_fails_when_secrets_unset(monkeypatch):
    module = _import_webhook_main_isolated(
        _ConfigStub(telegram_webhook_secret="", tbank_api_token=""),
        monkeypatch,
    )

    assert not module._is_valid_telegram_secret(
        _build_request({"X-Telegram-Bot-Api-Secret-Token": "telegram-secret"})
    )
    assert not module._is_valid_tbank_token(_build_request({"Authorization": "Bearer tbank-secret"}))


def test_sweeper_uses_safe_interval_parameterization():
    source = (_project_root() / "ru_worker" / "ru_worker.py").read_text(encoding="utf-8")
    assert "updated_at < NOW() - (%s * INTERVAL '1 minute')" in source
