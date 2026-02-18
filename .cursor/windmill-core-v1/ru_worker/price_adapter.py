"""
Price enrichment adapter for RFQ pipeline (ADR-007).

Soft-fail behavior:
- enrichment errors are returned as structured result
- exceptions are not propagated to caller
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List


_PRICE_CTX: Dict[str, Any] | None = None
_PRICE_CHECKER_MODULE: Any | None = None


def _price_checker_root() -> Path:
    # .../biretos-automation/.cursor/windmill-core-v1/ru_worker/price_adapter.py
    # -> .../biretos-automation/price-checker
    return Path(__file__).resolve().parents[3] / "price-checker"


def _load_price_checker_module() -> Any:
    """
    Load price_checker.py safely without polluting windmill config imports.
    """
    global _PRICE_CHECKER_MODULE
    if _PRICE_CHECKER_MODULE is not None:
        return _PRICE_CHECKER_MODULE

    price_checker_dir = _price_checker_root()
    if not price_checker_dir.exists():
        raise FileNotFoundError(f"price-checker directory not found: {price_checker_dir}")

    preserved_modules: Dict[str, Any] = {}
    conflicting_names = [
        "config",
        "export",
        "aggregation",
        "models",
        "rules",
        "discovery_mode",
        "sources",
        "utils",
        "price_checker",
    ]

    for name in conflicting_names:
        if name in sys.modules:
            preserved_modules[name] = sys.modules.pop(name)

    sys.path.insert(0, str(price_checker_dir))
    try:
        module = importlib.import_module("price_checker")
    finally:
        try:
            sys.path.remove(str(price_checker_dir))
        except ValueError:
            pass
        for name, module_obj in preserved_modules.items():
            sys.modules[name] = module_obj

    _PRICE_CHECKER_MODULE = module
    return module


def get_price_ctx() -> Dict[str, Any]:
    """
    Lazy singleton initialization for PriceChecker dependencies.
    """
    global _PRICE_CTX
    if _PRICE_CTX is not None:
        return _PRICE_CTX

    price_checker = _load_price_checker_module()
    env_path = _price_checker_root() / ".env"

    config = price_checker.load_config(str(env_path))
    logger = price_checker.setup_logger(config.log_level, config.log_file)
    converter = price_checker.CurrencyConverter.from_env(
        config.currency_rates_json, config.usd_rate_rub
    )
    http_client = price_checker.HttpClient(
        timeout_sec=config.source_timeout_sec,
        max_retries=config.max_retries,
        backoff_base_sec=config.retry_backoff_base_sec,
        proxy_url=config.proxy_url,
    )
    sources, serpapi_source, _insales_source = price_checker._build_sources(
        config, logger, http_client
    )
    aggregator = price_checker.PriceAggregator(converter, config.output_currency, logger)

    _PRICE_CTX = {
        "price_checker": price_checker,
        "config": config,
        "logger": logger,
        "converter": converter,
        "http_client": http_client,
        "sources": sources,
        "serpapi_source": serpapi_source,
        "aggregator": aggregator,
    }
    return _PRICE_CTX


def enrich_prices(part_numbers: List[str]) -> Dict[str, Any]:
    """
    Enrich part numbers with pricing data from price-checker.

    Using private _process_sku — acceptable technical debt (ADR-007).
    """
    if not part_numbers:
        return {
            "price_status": "skipped",
            "price_items_total": 0,
            "price_items_found": 0,
            "price_error": None,
            "price_audit": None,
        }

    try:
        ctx = get_price_ctx()
        price_checker = ctx["price_checker"]

        audits: List[Dict[str, Any]] = []
        found_count = 0

        for sku in part_numbers:
            audit_row = price_checker._process_sku(
                sku=str(sku),
                product_name=None,
                current_price=None,
                aggregator=ctx["aggregator"],
                sources=ctx["sources"],
                serpapi_source=ctx["serpapi_source"],
                config=ctx["config"],
                converter=ctx["converter"],
                logger=ctx["logger"],
            )

            if audit_row.market_price_median is not None:
                found_count += 1

            audits.append(
                {
                    "sku": audit_row.sku,
                    "market_price_median": audit_row.market_price_median,
                    "market_price_min": audit_row.market_price_min,
                    "market_price_max": audit_row.market_price_max,
                    "currency": ctx["config"].output_currency,
                    "sources_count": audit_row.sources_count,
                    "recommendation": audit_row.recommendation,
                    "confidence": audit_row.confidence,
                    "reason": audit_row.reason,
                    "source_links": audit_row.source_links,
                }
            )

        return {
            "price_status": "success",
            "price_items_total": len(part_numbers),
            "price_items_found": found_count,
            "price_error": None,
            "price_audit": audits,
        }
    except Exception as e:
        return {
            "price_status": "error",
            "price_items_total": len(part_numbers),
            "price_items_found": 0,
            "price_error": str(e),
            "price_audit": None,
        }

