#!/usr/bin/env python3
"""
RC-8 Shopware Reconciliation Sweeper (Tier-3).

Compares Core read-models vs Shopware snapshots for:
  - stock drift
  - price drift
  - order state mismatch
  - orphan order detection

Writes only to:
  - shopware_reconciliation_audit_log
  - shopware_reconciliation_alerts
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field, field_validator

CatalogFetcher = Callable[[Any, str], List[Dict[str, Any]]]
OrderFetcher = Callable[[Any, str], List[Dict[str, Any]]]


class RC8Payload(BaseModel):
    trace_id: str = Field(..., min_length=1)
    instance: str = Field(default="ru", pattern=r"^(ru|int)$")
    stock_warn_threshold: int = Field(default=5, ge=0)
    stock_critical_threshold: int = Field(default=20, ge=1)
    order_state_max_age_minutes: int = Field(default=30, ge=1)
    kill_switch_critical_limit: int = Field(default=10, ge=1)

    @field_validator("trace_id", mode="before")
    @classmethod
    def _normalize_trace_id(cls, value: Any) -> str:
        return str(value).strip()


def _log(event: str, data: Dict[str, Any]) -> None:
    print(json.dumps({"event": event, "ts": datetime.now(timezone.utc).isoformat(), **data}), flush=True)


def _default_catalog_fetcher(_db_conn: Any, _instance: str) -> List[Dict[str, Any]]:
    return []


def _default_order_fetcher(_db_conn: Any, _instance: str) -> List[Dict[str, Any]]:
    return []


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)


def _insert_audit(
    db_conn: Any,
    *,
    trace_id: str,
    instance: str,
    check_code: str,
    entity_type: str,
    entity_id: str,
    core_value: Dict[str, Any],
    external_value: Dict[str, Any],
    drift_value: Optional[float],
    severity: str,
) -> None:
    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO shopware_reconciliation_audit_log (
                trace_id, instance, check_code, entity_type, entity_id,
                core_value, external_value, drift_value, severity
            )
            VALUES (
                %s::uuid, %s, %s, %s, %s,
                %s::jsonb, %s::jsonb, %s, %s
            )
            """,
            (
                trace_id,
                instance,
                check_code,
                entity_type,
                entity_id,
                json.dumps(core_value, ensure_ascii=False),
                json.dumps(external_value, ensure_ascii=False),
                drift_value,
                severity,
            ),
        )
    finally:
        cur.close()


def _insert_alert(
    db_conn: Any,
    *,
    trace_id: str,
    instance: str,
    check_code: str,
    severity: str,
    message_text: str,
    cooldown_key: str,
) -> bool:
    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO shopware_reconciliation_alerts (
                trace_id, instance, check_code, severity, message_text, cooldown_key
            )
            VALUES (%s::uuid, %s, %s, %s, %s, %s)
            ON CONFLICT (cooldown_key) DO NOTHING
            RETURNING id
            """,
            (trace_id, instance, check_code, severity, message_text, cooldown_key),
        )
        return bool(cur.fetchone())
    finally:
        cur.close()


def _severity_from_stock_drift(drift: int, warn: int, critical: int) -> str:
    if drift >= critical:
        return "critical"
    if drift >= warn:
        return "warning"
    return "info"


def _index_by(items: Iterable[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    for item in items:
        identifier = str(item.get(key, "")).strip()
        if not identifier:
            continue
        indexed[identifier] = item
    return indexed


def run_rc8_shopware_reconciliation(
    db_conn: Any,
    payload: Dict[str, Any],
    *,
    core_catalog_fetcher: Optional[CatalogFetcher] = None,
    shopware_catalog_fetcher: Optional[CatalogFetcher] = None,
    core_order_fetcher: Optional[OrderFetcher] = None,
    shopware_order_fetcher: Optional[OrderFetcher] = None,
) -> Dict[str, Any]:
    cfg = RC8Payload.model_validate(payload)

    fetch_core_catalog = core_catalog_fetcher or _default_catalog_fetcher
    fetch_shopware_catalog = shopware_catalog_fetcher or _default_catalog_fetcher
    fetch_core_orders = core_order_fetcher or _default_order_fetcher
    fetch_shopware_orders = shopware_order_fetcher or _default_order_fetcher

    core_catalog = _index_by(fetch_core_catalog(db_conn, cfg.instance), "sku")
    shopware_catalog = _index_by(fetch_shopware_catalog(db_conn, cfg.instance), "sku")
    core_orders = _index_by(fetch_core_orders(db_conn, cfg.instance), "order_number")
    shopware_orders = _index_by(fetch_shopware_orders(db_conn, cfg.instance), "order_number")

    audit_count = 0
    alert_count = 0
    critical_count = 0

    def emit(
        *,
        check_code: str,
        entity_type: str,
        entity_id: str,
        core_value: Dict[str, Any],
        external_value: Dict[str, Any],
        drift_value: Optional[float],
        severity: str,
        message: str,
    ) -> None:
        nonlocal audit_count, alert_count, critical_count
        _insert_audit(
            db_conn=db_conn,
            trace_id=cfg.trace_id,
            instance=cfg.instance,
            check_code=check_code,
            entity_type=entity_type,
            entity_id=entity_id,
            core_value=core_value,
            external_value=external_value,
            drift_value=drift_value,
            severity=severity,
        )
        audit_count += 1

        if severity in {"warning", "critical"}:
            inserted = _insert_alert(
                db_conn=db_conn,
                trace_id=cfg.trace_id,
                instance=cfg.instance,
                check_code=check_code,
                severity=severity,
                message_text=message,
                cooldown_key=f"{cfg.instance}:{check_code}:{entity_type}:{entity_id}:{severity}",
            )
            if inserted:
                alert_count += 1
        if severity == "critical":
            critical_count += 1

    for sku in sorted(set(core_catalog.keys()) | set(shopware_catalog.keys())):
        core_item = core_catalog.get(sku)
        sw_item = shopware_catalog.get(sku)
        if core_item is None or sw_item is None:
            emit(
                check_code="RC8-CATALOG-PRESENCE",
                entity_type="sku",
                entity_id=sku,
                core_value=core_item or {},
                external_value=sw_item or {},
                drift_value=None,
                severity="warning",
                message=f"SKU presence mismatch: {sku}",
            )
            continue

        core_stock = _to_int(core_item.get("stock_quota"))
        sw_stock = _to_int(sw_item.get("stock"))
        stock_drift = abs(core_stock - sw_stock)
        severity = _severity_from_stock_drift(
            stock_drift, cfg.stock_warn_threshold, cfg.stock_critical_threshold
        )
        emit(
            check_code="RC8-STOCK-DRIFT",
            entity_type="sku",
            entity_id=sku,
            core_value={"stock_quota": core_stock},
            external_value={"stock": sw_stock},
            drift_value=float(stock_drift),
            severity=severity,
            message=f"Stock drift for {sku}: core={core_stock}, shopware={sw_stock}",
        )

        core_price = _to_int(core_item.get("price_minor"))
        sw_price = _to_int(sw_item.get("price_minor"))
        if core_price != sw_price:
            emit(
                check_code="RC8-PRICE-DRIFT",
                entity_type="sku",
                entity_id=sku,
                core_value={"price_minor": core_price},
                external_value={"price_minor": sw_price},
                drift_value=float(abs(core_price - sw_price)),
                severity="warning",
                message=f"Price drift for {sku}: core={core_price}, shopware={sw_price}",
            )

    now = datetime.now(timezone.utc)
    for order_number in sorted(set(core_orders.keys()) | set(shopware_orders.keys())):
        core_order = core_orders.get(order_number)
        sw_order = shopware_orders.get(order_number)
        if core_order is None:
            emit(
                check_code="RC8-ORPHAN-ORDER",
                entity_type="order",
                entity_id=order_number,
                core_value={},
                external_value=sw_order or {},
                drift_value=None,
                severity="critical",
                message=f"Order exists in Shopware but absent in Core: {order_number}",
            )
            continue
        if sw_order is None:
            emit(
                check_code="RC8-MISSING-EXTERNAL-ORDER",
                entity_type="order",
                entity_id=order_number,
                core_value=core_order,
                external_value={},
                drift_value=None,
                severity="warning",
                message=f"Order exists in Core but absent in Shopware: {order_number}",
            )
            continue

        core_state = str(core_order.get("state", "")).strip()
        sw_state = str(sw_order.get("state", "")).strip()
        if core_state != sw_state:
            core_dt = _to_datetime(core_order.get("updated_at"))
            sw_dt = _to_datetime(sw_order.get("updated_at"))
            age_minutes = int((now - max(core_dt, sw_dt)).total_seconds() // 60)
            severity = "critical" if age_minutes >= cfg.order_state_max_age_minutes else "warning"
            emit(
                check_code="RC8-ORDER-STATE-MISMATCH",
                entity_type="order",
                entity_id=order_number,
                core_value={"state": core_state, "updated_at": core_dt.isoformat()},
                external_value={"state": sw_state, "updated_at": sw_dt.isoformat()},
                drift_value=float(max(0, age_minutes)),
                severity=severity,
                message=(
                    f"Order state mismatch for {order_number}: core={core_state}, "
                    f"shopware={sw_state}, age={age_minutes}m"
                ),
            )

    kill_switch = critical_count >= cfg.kill_switch_critical_limit
    if kill_switch:
        _insert_alert(
            db_conn=db_conn,
            trace_id=cfg.trace_id,
            instance=cfg.instance,
            check_code="RC8-KILL-SWITCH",
            severity="critical",
            message_text="RC-8 kill switch activated: freeze catalog sync",
            cooldown_key=f"{cfg.instance}:RC8-KILL-SWITCH",
        )
        alert_count += 1

    db_conn.commit()
    _log(
        "rc8_shopware_reconciliation_done",
        {
            "trace_id": cfg.trace_id,
            "instance": cfg.instance,
            "audit_count": audit_count,
            "alert_count": alert_count,
            "critical_count": critical_count,
            "kill_switch": kill_switch,
        },
    )
    return {
        "instance": cfg.instance,
        "audit_count": audit_count,
        "alert_count": alert_count,
        "critical_count": critical_count,
        "kill_switch": kill_switch,
    }
