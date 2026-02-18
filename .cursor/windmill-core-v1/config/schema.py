from dataclasses import dataclass
from typing import Optional, Tuple

CRITICAL_ENV = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
    "TBANK_API_TOKEN",
    "TBANK_API_BASE",
    "CDEK_CLIENT_ID",
    "CDEK_CLIENT_SECRET",
    "POSTGRES_PASSWORD",
)

DEFAULT_ALLOWED_USER_IDS: Tuple[int, ...] = (123456789, 987654321, 186497598)

ENV_NAMES = (
    "ALLOWED_USER_IDS",
    "ACTION_MODE",
    "CDEK_API_BASE",
    "CDEK_API_TOKEN",
    "CDEK_API_URL",
    "CDEK_CLIENT_ID",
    "CDEK_CLIENT_SECRET",
    "CDEK_FROM_LOCATION_CODE",
    "CDEK_ORDERS_PATH",
    "CDEK_OAUTH_PATH",
    "CDEK_SENDER_ADDRESS",
    "CDEK_SENDER_COMPANY",
    "CDEK_SENDER_PHONE",
    "DRY_RUN_EXTERNAL_APIS",
    "INSALES_API_PASSWORD",
    "INSALES_API_USER",
    "INSALES_SHOP",
    "LLM_ENABLED_DEFAULT",
    "LLM_TIMEOUT_SECONDS",
    "LOG_LEVEL",
    "MAX_RETRIES",
    "MAX_INPUT_SIZE_BYTES",
    "MAX_PRICE_DEVIATION",
    "N8N_TIMEOUT_SECONDS",
    "N8N_WEBHOOK_URL",
    "EXPECTED_TAX_RATES",
    "EXECUTION_MODE",
    "CSG_ENABLED",
    "CANARY_SAMPLE_RATE",
    "CANARY_HASH_ALGO_ID",
    "GATE_CHAIN_VERSION",
    "REPLAY_CDEK_API_TOKEN",
    "REPLAY_INSALES_API_PASSWORD",
    "REPLAY_INSALES_API_USER",
    "REPLAY_TBANK_API_TOKEN",
    "ROUNDING_TOLERANCE",
    "POLL_INTERVAL",
    "POSTGRES_DB",
    "POSTGRES_HOST",
    "POSTGRES_PASSWORD",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "PROCESSED_TTL_SECONDS",
    "REDIS_DB",
    "REDIS_HOST",
    "REDIS_PASSWORD",
    "REDIS_PORT",
    "REDIS_PROCESSED_PREFIX",
    "REDIS_QUEUE_KEY",
    "RETRY_BASE_DELAY_SECONDS",
    "RETRY_MAX_DELAY_SECONDS",
    "RU_BASE_URL",
    "RU_WORKER_POLL_INTERVAL",
    "SELFTEST_INVOICES",
    "SIMULATE_CALLBACK_QUERY",
    "SHOPWARE_CLIENT_ID",
    "SHOPWARE_CLIENT_SECRET",
    "SHOPWARE_ENABLE_DRY_RUN",
    "SHOPWARE_TIMEOUT_SECONDS",
    "SHOPWARE_URL",
    "STATE_PREFIX",
    "TBANK_API_BASE",
    "TBANK_API_TOKEN",
    "TBANK_API_URL",
    "TBANK_INVOICE_STATUS_PATH",
    "TBANK_INVOICES_LIST_PATH",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_SECRET_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
    "TELEGRAM_WEBHOOK_URL",
    "TEST_INVOICE_ID",
    "USA_LLM_API_KEY",
    "USA_LLM_BASE_URL",
    "WEBHOOK_URL",
    "WEBHOOK_SERVICE_URL",
    "WINDMILL_TOKEN",
    "WINDMILL_URL",
    "WORKER_COUNT",
    "WORKER_ID",
    "WORKER_SCRIPT_PATH",
)


@dataclass(frozen=True)
class Config:
    # Critical
    telegram_bot_token: str
    telegram_webhook_secret: str
    tbank_api_token: str
    tbank_api_base: str
    cdek_client_id: str
    cdek_client_secret: str
    postgres_password: str

    # Optional / defaults
    allowed_user_ids: Tuple[int, ...]
    cdek_from_location_code: int

    # Optional raw values
    tbank_api_url: Optional[str]
    tbank_invoice_status_path: Optional[str]
    tbank_invoices_list_path: Optional[str]
    cdek_api_base: Optional[str]
    cdek_sender_company: Optional[str]
    cdek_sender_phone: Optional[str]
    cdek_sender_address: Optional[str]
    cdek_oauth_path: Optional[str]
    cdek_orders_path: Optional[str]
    worker_script_path: Optional[str]
    state_prefix: Optional[str]
    action_mode: Optional[str]
    windmill_url: Optional[str]
    windmill_token: Optional[str]
    webhook_url: Optional[str]
    webhook_service_url: Optional[str]
    postgres_host: Optional[str]
    postgres_port: Optional[int]
    postgres_db: Optional[str]
    postgres_user: Optional[str]
    ru_worker_poll_interval: Optional[int]
    llm_enabled_default: Optional[bool]
    selftest_invoices: Optional[bool]
    simulate_callback_query: Optional[bool]
    insales_shop: Optional[str]
    insales_api_user: Optional[str]
    insales_api_password: Optional[str]
    dry_run_external_apis: Optional[bool]
    log_level: Optional[str]
    redis_host: Optional[str]
    redis_port: Optional[int]
    redis_db: Optional[int]
    redis_password: Optional[str]
    redis_queue_key: Optional[str]
    redis_processed_prefix: Optional[str]
    processed_ttl_seconds: Optional[int]
    n8n_webhook_url: Optional[str]
    max_retries: Optional[int]
    retry_base_delay_seconds: Optional[float]
    retry_max_delay_seconds: Optional[float]
    worker_count: Optional[int]
    n8n_timeout_seconds: Optional[float]
    telegram_secret_token: Optional[str]
    ru_base_url: Optional[str]
    poll_interval: Optional[int]
    worker_id: Optional[str]
    usa_llm_base_url: Optional[str]
    usa_llm_api_key: Optional[str]
    llm_timeout_seconds: Optional[int]
    cdek_api_url: Optional[str]
    cdek_api_token: Optional[str]
    test_invoice_id: Optional[str]
    telegram_webhook_url: Optional[str]
    shopware_url: str = ""
    shopware_client_id: str = ""
    shopware_client_secret: str = ""
    shopware_timeout_seconds: int = 10
    shopware_enable_dry_run: bool = False
    execution_mode: str = "LIVE"
    csg_enabled: bool = False
    max_input_size_bytes: int = 102400
    max_price_deviation: float = 0.15
    rounding_tolerance: int = 1
    expected_tax_rates: str = "{}"
    canary_sample_rate: float = 0.05
    canary_hash_algo_id: str = "sha256_mod"
    gate_chain_version: str = "v3"
    replay_tbank_api_token: str = ""
    replay_cdek_api_token: str = ""
    replay_insales_api_user: str = ""
    replay_insales_api_password: str = ""
