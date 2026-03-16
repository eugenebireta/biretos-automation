import json
from typing import List, Optional, Tuple

from .bootstrap import get_raw_env
from .errors import ConfigValidationError
from .schema import Config, CRITICAL_ENV, DEFAULT_ALLOWED_USER_IDS


def _is_missing(value: Optional[str]) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _parse_int(name: str, value: Optional[str], default: Optional[int], invalid: List[str]) -> Optional[int]:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        invalid.append(f"{name}: expected int")
        return default


def _parse_float(name: str, value: Optional[str], default: Optional[float], invalid: List[str]) -> Optional[float]:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        invalid.append(f"{name}: expected float")
        return default


def _parse_bool(value: Optional[str], default: Optional[bool]) -> Optional[bool]:
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "y", "on")


def _parse_allowed_user_ids(value: Optional[str]) -> Tuple[int, ...]:
    if value is None or value.strip() == "":
        return DEFAULT_ALLOWED_USER_IDS
    parsed: List[int] = []
    for uid_str in value.split(","):
        uid_str = uid_str.strip()
        if not uid_str:
            continue
        try:
            parsed.append(int(uid_str))
        except ValueError:
            continue
    return tuple(parsed) if parsed else DEFAULT_ALLOWED_USER_IDS


def validate_config() -> Config:
    raw = get_raw_env()
    missing: List[str] = []
    invalid: List[str] = []

    for name in CRITICAL_ENV:
        if _is_missing(raw.get(name)):
            missing.append(name)

    if missing:
        raise ConfigValidationError(missing=sorted(missing), invalid=invalid)

    allowed_user_ids = _parse_allowed_user_ids(raw.get("ALLOWED_USER_IDS"))
    cdek_from_location_code = _parse_int(
        "CDEK_FROM_LOCATION_CODE", raw.get("CDEK_FROM_LOCATION_CODE"), 270, invalid
    )

    postgres_port = _parse_int("POSTGRES_PORT", raw.get("POSTGRES_PORT"), 5432, invalid)
    ru_worker_poll_interval = _parse_int(
        "RU_WORKER_POLL_INTERVAL", raw.get("RU_WORKER_POLL_INTERVAL"), 5, invalid
    )
    processed_ttl_seconds = _parse_int(
        "PROCESSED_TTL_SECONDS", raw.get("PROCESSED_TTL_SECONDS"), 86400, invalid
    )
    redis_port = _parse_int("REDIS_PORT", raw.get("REDIS_PORT"), 6379, invalid)
    redis_db = _parse_int("REDIS_DB", raw.get("REDIS_DB"), 0, invalid)
    max_retries = _parse_int("MAX_RETRIES", raw.get("MAX_RETRIES"), 8, invalid)
    worker_count = _parse_int("WORKER_COUNT", raw.get("WORKER_COUNT"), 2, invalid)
    poll_interval = _parse_int("POLL_INTERVAL", raw.get("POLL_INTERVAL"), 5, invalid)
    alert_poll_interval = _parse_int(
        "ALERT_POLL_INTERVAL", raw.get("ALERT_POLL_INTERVAL"), 300, invalid
    )
    alert_telegram_chat_id = _parse_int(
        "ALERT_TELEGRAM_CHAT_ID", raw.get("ALERT_TELEGRAM_CHAT_ID"), None, invalid
    )
    alert_chat_id_critical = _parse_int(
        "ALERT_CHAT_ID_CRITICAL", raw.get("ALERT_CHAT_ID_CRITICAL"), None, invalid
    )
    alert_chat_id_warning = _parse_int(
        "ALERT_CHAT_ID_WARNING", raw.get("ALERT_CHAT_ID_WARNING"), None, invalid
    )
    alert_min_severity_raw = (raw.get("ALERT_MIN_SEVERITY") or "WARNING").strip().upper()
    if alert_min_severity_raw not in {"INFO", "WARNING", "CRITICAL"}:
        invalid.append("ALERT_MIN_SEVERITY: expected INFO, WARNING, or CRITICAL")
        alert_min_severity_raw = "WARNING"
    llm_timeout_seconds = _parse_int(
        "LLM_TIMEOUT_SECONDS", raw.get("LLM_TIMEOUT_SECONDS"), 30, invalid
    )
    max_input_size_bytes = _parse_int(
        "MAX_INPUT_SIZE_BYTES", raw.get("MAX_INPUT_SIZE_BYTES"), 102400, invalid
    )
    rounding_tolerance = _parse_int(
        "ROUNDING_TOLERANCE", raw.get("ROUNDING_TOLERANCE"), 1, invalid
    )

    retry_base_delay_seconds = _parse_float(
        "RETRY_BASE_DELAY_SECONDS", raw.get("RETRY_BASE_DELAY_SECONDS"), 1.0, invalid
    )
    retry_max_delay_seconds = _parse_float(
        "RETRY_MAX_DELAY_SECONDS", raw.get("RETRY_MAX_DELAY_SECONDS"), 60.0, invalid
    )
    n8n_timeout_seconds = _parse_float(
        "N8N_TIMEOUT_SECONDS", raw.get("N8N_TIMEOUT_SECONDS"), 15.0, invalid
    )
    max_price_deviation = _parse_float(
        "MAX_PRICE_DEVIATION", raw.get("MAX_PRICE_DEVIATION"), 0.15, invalid
    )
    canary_sample_rate = _parse_float(
        "CANARY_SAMPLE_RATE", raw.get("CANARY_SAMPLE_RATE"), 0.05, invalid
    )
    execution_mode_raw = (raw.get("EXECUTION_MODE") or "LIVE").strip().upper()
    if execution_mode_raw not in {"LIVE", "REPLAY"}:
        invalid.append("EXECUTION_MODE: expected LIVE or REPLAY")
        execution_mode_raw = "LIVE"

    expected_tax_rates = raw.get("EXPECTED_TAX_RATES") or "{}"
    try:
        json.loads(expected_tax_rates)
    except Exception:
        invalid.append("EXPECTED_TAX_RATES: expected valid JSON")
        expected_tax_rates = "{}"

    if max_input_size_bytes is not None and max_input_size_bytes <= 0:
        invalid.append("MAX_INPUT_SIZE_BYTES: expected > 0")
    if rounding_tolerance is not None and rounding_tolerance < 0:
        invalid.append("ROUNDING_TOLERANCE: expected >= 0")
    if max_price_deviation is not None and not (0 <= max_price_deviation <= 1):
        invalid.append("MAX_PRICE_DEVIATION: expected between 0 and 1")
    if canary_sample_rate is not None and not (0 <= canary_sample_rate <= 1):
        invalid.append("CANARY_SAMPLE_RATE: expected between 0 and 1")
    shopware_url = raw.get("SHOPWARE_URL") or ""
    shopware_client_id = raw.get("SHOPWARE_CLIENT_ID") or ""
    shopware_client_secret = raw.get("SHOPWARE_CLIENT_SECRET") or ""
    shopware_timeout_seconds = _parse_int(
        "SHOPWARE_TIMEOUT_SECONDS",
        raw.get("SHOPWARE_TIMEOUT_SECONDS"),
        10,
        invalid,
    )
    shopware_enable_dry_run = _parse_bool(
        raw.get("SHOPWARE_ENABLE_DRY_RUN"),
        False,
    )

    if invalid:
        raise ConfigValidationError(missing=missing, invalid=sorted(invalid))

    return Config(
        telegram_bot_token=raw.get("TELEGRAM_BOT_TOKEN") or "",
        telegram_webhook_secret=raw.get("TELEGRAM_WEBHOOK_SECRET") or "",
        tbank_api_token=raw.get("TBANK_API_TOKEN") or "",
        tbank_api_base=raw.get("TBANK_API_BASE") or "",
        cdek_client_id=raw.get("CDEK_CLIENT_ID") or "",
        cdek_client_secret=raw.get("CDEK_CLIENT_SECRET") or "",
        postgres_password=raw.get("POSTGRES_PASSWORD") or "",
        allowed_user_ids=allowed_user_ids,
        cdek_from_location_code=cdek_from_location_code or 270,
        tbank_api_url=raw.get("TBANK_API_URL"),
        tbank_invoice_status_path=raw.get("TBANK_INVOICE_STATUS_PATH"),
        tbank_invoices_list_path=raw.get("TBANK_INVOICES_LIST_PATH"),
        cdek_api_base=raw.get("CDEK_API_BASE"),
        cdek_sender_company=raw.get("CDEK_SENDER_COMPANY"),
        cdek_sender_phone=raw.get("CDEK_SENDER_PHONE"),
        cdek_sender_address=raw.get("CDEK_SENDER_ADDRESS"),
        cdek_oauth_path=raw.get("CDEK_OAUTH_PATH"),
        cdek_orders_path=raw.get("CDEK_ORDERS_PATH"),
        worker_script_path=raw.get("WORKER_SCRIPT_PATH"),
        state_prefix=raw.get("STATE_PREFIX"),
        action_mode=raw.get("ACTION_MODE"),
        windmill_url=raw.get("WINDMILL_URL"),
        windmill_token=raw.get("WINDMILL_TOKEN"),
        webhook_url=raw.get("WEBHOOK_URL"),
        webhook_service_url=raw.get("WEBHOOK_SERVICE_URL") or "http://localhost:8001",
        postgres_host=raw.get("POSTGRES_HOST") or "localhost",
        postgres_port=postgres_port,
        postgres_db=raw.get("POSTGRES_DB") or "biretos_automation",
        postgres_user=raw.get("POSTGRES_USER") or "biretos_user",
        ru_worker_poll_interval=ru_worker_poll_interval,
        llm_enabled_default=_parse_bool(raw.get("LLM_ENABLED_DEFAULT"), False),
        selftest_invoices=_parse_bool(raw.get("SELFTEST_INVOICES"), False),
        simulate_callback_query=_parse_bool(raw.get("SIMULATE_CALLBACK_QUERY"), False),
        insales_shop=raw.get("INSALES_SHOP") or "bireta.myinsales.ru",
        insales_api_user=raw.get("INSALES_API_USER"),
        insales_api_password=raw.get("INSALES_API_PASSWORD"),
        dry_run_external_apis=_parse_bool(raw.get("DRY_RUN_EXTERNAL_APIS"), False),
        log_level=raw.get("LOG_LEVEL") or "INFO",
        redis_host=raw.get("REDIS_HOST") or "biretos-redis",
        redis_port=redis_port,
        redis_db=redis_db,
        redis_password=raw.get("REDIS_PASSWORD"),
        redis_queue_key=raw.get("REDIS_QUEUE_KEY") or "telegram:updates",
        redis_processed_prefix=raw.get("REDIS_PROCESSED_PREFIX") or "telegram:processed:",
        processed_ttl_seconds=processed_ttl_seconds,
        n8n_webhook_url=raw.get("N8N_WEBHOOK_URL"),
        max_retries=max_retries,
        retry_base_delay_seconds=retry_base_delay_seconds,
        retry_max_delay_seconds=retry_max_delay_seconds,
        worker_count=worker_count,
        n8n_timeout_seconds=n8n_timeout_seconds,
        telegram_secret_token=raw.get("TELEGRAM_SECRET_TOKEN"),
        ru_base_url=raw.get("RU_BASE_URL") or "https://n8n.biretos.ae",
        poll_interval=poll_interval,
        alert_poll_interval=alert_poll_interval,
        alert_telegram_chat_id=alert_telegram_chat_id,
        alert_chat_id_critical=alert_chat_id_critical,
        alert_chat_id_warning=alert_chat_id_warning,
        alert_min_severity=alert_min_severity_raw,
        worker_id=raw.get("WORKER_ID") or "local-pc-worker",
        usa_llm_base_url=raw.get("USA_LLM_BASE_URL") or "https://usa-llm-gateway.example.com",
        usa_llm_api_key=raw.get("USA_LLM_API_KEY"),
        llm_timeout_seconds=llm_timeout_seconds,
        cdek_api_url=raw.get("CDEK_API_URL") or "https://api.cdek.ru/v2/orders",
        cdek_api_token=raw.get("CDEK_API_TOKEN"),
        test_invoice_id=raw.get("TEST_INVOICE_ID"),
        telegram_webhook_url=raw.get("TELEGRAM_WEBHOOK_URL"),
        shopware_url=shopware_url,
        shopware_client_id=shopware_client_id,
        shopware_client_secret=shopware_client_secret,
        shopware_timeout_seconds=shopware_timeout_seconds,
        shopware_enable_dry_run=shopware_enable_dry_run,
        execution_mode=execution_mode_raw,
        csg_enabled=_parse_bool(raw.get("CSG_ENABLED"), False) or False,
        max_input_size_bytes=max_input_size_bytes or 102400,
        max_price_deviation=max_price_deviation if max_price_deviation is not None else 0.15,
        rounding_tolerance=rounding_tolerance if rounding_tolerance is not None else 1,
        expected_tax_rates=expected_tax_rates,
        canary_sample_rate=canary_sample_rate if canary_sample_rate is not None else 0.05,
        canary_hash_algo_id=raw.get("CANARY_HASH_ALGO_ID") or "sha256_mod",
        gate_chain_version=raw.get("GATE_CHAIN_VERSION") or "v3",
        replay_tbank_api_token=raw.get("REPLAY_TBANK_API_TOKEN") or "",
        replay_cdek_api_token=raw.get("REPLAY_CDEK_API_TOKEN") or "",
        replay_insales_api_user=raw.get("REPLAY_INSALES_API_USER") or "",
        replay_insales_api_password=raw.get("REPLAY_INSALES_API_PASSWORD") or "",
    )


def format_config_error(error: ConfigValidationError) -> str:
    lines = [
        "FATAL CONFIG ERROR",
        "==================",
    ]
    if error.missing:
        lines.append("Missing CRITICAL ENV variables:")
        for name in error.missing:
            lines.append(f"  - {name}")
    if error.invalid:
        if error.missing:
            lines.append("")
        lines.append("Invalid ENV variables:")
        for item in error.invalid:
            lines.append(f"  - {item}")
    lines.append("")
    lines.append("Exit code: 1")
    return "\n".join(lines)
