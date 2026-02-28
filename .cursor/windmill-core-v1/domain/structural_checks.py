from __future__ import annotations

from typing import Any, Dict, List, Optional


TERMINAL_ORDER_STATES = ("completed", "cancelled", "failed")


def check_stock_ledger_non_negative(
    db_conn,
    *,
    trace_id: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    L3-A: Detect negative on-hand balance per product+warehouse.
    Read-only: SELECT only.
    """
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT product_id, warehouse_code, COALESCE(SUM(quantity_delta), 0) AS on_hand
            FROM stock_ledger_entries
            WHERE change_type IN ('receipt', 'return', 'adjustment', 'sale')
            GROUP BY product_id, warehouse_code
            HAVING COALESCE(SUM(quantity_delta), 0) < 0
            ORDER BY on_hand ASC
            LIMIT %s
            """,
            (int(limit),),
        )
        rows = cursor.fetchall()
        problems: List[Dict[str, Any]] = []
        for product_id, warehouse_code, on_hand in rows:
            problems.append(
                {
                    "entity_type": "stock",
                    "entity_id": f"{product_id}:{warehouse_code}",
                    "details": {
                        "product_id": str(product_id),
                        "warehouse_code": str(warehouse_code),
                        "on_hand": int(on_hand),
                    },
                }
            )
        return {
            "check_code": "L3-A",
            "severity": "CRITICAL",
            "verdict": "FAIL" if problems else "PASS",
            "problems": problems,
            "trace_id": trace_id,
        }
    finally:
        cursor.close()


def check_reservations_for_terminal_orders(
    db_conn,
    *,
    trace_id: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    L3-D: Detect active reservations for terminal orders.
    Read-only: SELECT only.
    """
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT r.id, r.order_id, r.line_item_id, o.state
            FROM reservations r
            JOIN order_ledger o ON o.order_id = r.order_id
            WHERE r.status = 'active'
              AND o.state IN %s
            ORDER BY r.updated_at DESC NULLS LAST
            LIMIT %s
            """,
            (TERMINAL_ORDER_STATES, int(limit)),
        )
        rows = cursor.fetchall()
        problems: List[Dict[str, Any]] = []
        for reservation_id, order_id, line_item_id, state in rows:
            problems.append(
                {
                    "entity_type": "reservation",
                    "entity_id": str(reservation_id),
                    "details": {
                        "reservation_id": str(reservation_id),
                        "order_id": str(order_id),
                        "line_item_id": str(line_item_id),
                        "order_state": str(state),
                    },
                }
            )
        return {
            "check_code": "L3-D",
            "severity": "MEDIUM",
            "verdict": "FAIL" if problems else "PASS",
            "problems": problems,
            "trace_id": trace_id,
        }
    finally:
        cursor.close()

