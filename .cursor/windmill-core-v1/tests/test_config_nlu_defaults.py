from __future__ import annotations

from config.schema import Config
from config import validator


def test_validator_defaults_match_day1_canon(monkeypatch):
    monkeypatch.setattr(
        validator,
        "get_raw_env",
        lambda: {
            "TELEGRAM_BOT_TOKEN": "bot-token",
            "TELEGRAM_WEBHOOK_SECRET": "telegram-secret",
            "TBANK_API_TOKEN": "tbank-token",
            "TBANK_API_BASE": "https://tbank.example",
            "CDEK_CLIENT_ID": "cdek-client-id",
            "CDEK_CLIENT_SECRET": "cdek-client-secret",
            "POSTGRES_PASSWORD": "postgres-password",
        },
    )

    cfg = validator.validate_config()

    assert cfg.nlu_enabled is True
    assert cfg.nlu_shadow_mode is False
    assert cfg.nlu_degradation_level == 0


def test_schema_defaults_match_day1_canon():
    assert Config.__dataclass_fields__["nlu_enabled"].default is True
    assert Config.__dataclass_fields__["nlu_shadow_mode"].default is False
