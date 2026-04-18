"""
Shopware bundle order processor — close the loop on bundle stock decrement.

Polls /api/order for orders containing bundle products (productNumber that
exists in our biretos_bundle custom field set). For each line item that is a
bundle:

  1. Calculate how many base pieces were consumed:
        base_pieces_consumed = order_line.quantity * bundle.lot_size
  2. Decrement base product's stock by that amount (atomic patch)
  3. Mark this order_line as 'biretos_bundle_processed' via custom field
     to prevent double-decrement on next poll
  4. The next stock-sync run will then re-derive ALL bundle stocks from
     the new base stock

State tracking:
  - Per-order-line custom field: 'biretos_bundle_consumed_pieces' = int
    Set to the consumed value once processed. Skip if already set.
  - Conservative: only processes orders with state in (open, in_progress,
    completed). Skips cancelled.

Usage:
  # dry-run
  python scripts/shopware_bundle_order_processor.py
  # real
  python scripts/shopware_bundle_order_processor.py --execute
  # process orders since timestamp
  python scripts/shopware_bundle_order_processor.py --execute --since 2026-04-16T00:00:00

Cron (every 5 min on VPS):
  */5 * * * * cd /opt/biretos && \
      python3 scripts/shopware_bundle_order_processor.py --execute \
      >> /opt/biretos/logs/bundle_orders.log 2>&1
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

SECRETS_ENV = Path("config/.secrets.env")
CF_SOURCE_NUMBER = "biretos_bundle_source_number"
CF_LOT_SIZE = "biretos_bundle_lot_size"
CF_PROCESSED = "biretos_bundle_consumed_pieces"  # set on order_line_item to prevent double-count
PROCESSABLE_STATES = {"open", "in_progress", "completed"}


def load_secrets() -> dict:
    out = dict(os.environ)
    if SECRETS_ENV.exists():
        for line in SECRETS_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out.setdefault(k.strip(), v.strip())
    return out


class Shopware:
    def __init__(self, url: str, cid: str, csec: str, dry_run: bool):
        self.url = url.rstrip("/")
        self._cid = cid
        self._csec = csec
        self.dry_run = dry_run
        self.s = requests.Session()
        self._token: str | None = None
        self._exp = 0.0

    def _auth(self) -> str:
        if self._token and time.time() < self._exp - 30:
            return self._token
        r = self.s.post(
            f"{self.url}/api/oauth/token",
            json={"grant_type": "client_credentials", "client_id": self._cid, "client_secret": self._csec},
            timeout=20,
        )
        r.raise_for_status()
        d = r.json()
        self._token = d["access_token"]
        self._exp = time.time() + int(d.get("expires_in", 600))
        return self._token

    def _hdr(self) -> dict:
        return {
            "Authorization": f"Bearer {self._auth()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def search(self, entity: str, payload: dict) -> dict:
        r = self.s.post(f"{self.url}/api/search/{entity}", headers=self._hdr(), json=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def patch(self, path: str, body: dict) -> None:
        if self.dry_run:
            print(f"  [DRY-RUN] PATCH {path}  body={body}")
            return
        r = self.s.patch(f"{self.url}{path}", headers=self._hdr(), json=body, timeout=30)
        if not r.ok:
            raise RuntimeError(f"PATCH {path} -> {r.status_code}: {r.text[:300]}")


def fetch_orders_since(sw: Shopware, since_iso: str | None) -> list[dict]:
    """Return all orders updated since given ISO timestamp."""
    flt: list = []
    if since_iso:
        flt.append({"type": "range", "field": "updatedAt", "parameters": {"gte": since_iso}})
    payload = {
        "limit": 100,
        "filter": flt,
        "associations": {
            "lineItems": {
                "associations": {"product": {}},
            },
            "stateMachineState": {},
        },
    }
    out: list[dict] = []
    page = 1
    while True:
        payload["page"] = page
        resp = sw.search("order", payload)
        data = resp.get("data", [])
        included = {(i["type"], i["id"]): i for i in resp.get("included", [])}
        for o in data:
            o["_included"] = included
            out.append(o)
        if len(data) < 100:
            break
        page += 1
        if page > 50:
            break  # safety cap
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true", help="apply changes (default: dry-run)")
    ap.add_argument("--since", default=None, help="ISO datetime (gte updatedAt). Default: last 24h")
    args = ap.parse_args()

    env = load_secrets()
    url = env.get("SHOPWARE_URL")
    cid = env.get("SHOPWARE_CLIENT_ID")
    csec = env.get("SHOPWARE_CLIENT_SECRET")
    if not (url and cid and csec):
        print("ERROR: SHOPWARE_URL/CLIENT_ID/CLIENT_SECRET missing", file=sys.stderr)
        return 2

    if args.since is None:
        # default: last 24h
        from datetime import timedelta

        args.since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")

    sw = Shopware(url, cid, csec, dry_run=not args.execute)

    print(f"URL:   {url}")
    print(f"Mode:  {'EXECUTE' if args.execute else 'DRY-RUN'}")
    print(f"Since: {args.since}")
    print()

    print("Fetching orders...")
    orders = fetch_orders_since(sw, args.since)
    print(f"  {len(orders)} orders to inspect")

    decrements: dict[str, int] = {}  # base productNumber -> total pieces to decrement
    line_items_to_mark: list[tuple[str, int]] = []  # (line_item_id, consumed_pieces)
    skipped_processed = 0
    skipped_not_bundle = 0
    skipped_bad_state = 0

    for order in orders:
        attrs = order.get("attributes", order)
        # Resolve state name from associations
        state_name = None
        sm = attrs.get("stateMachineState") or {}
        if isinstance(sm, dict):
            state_name = (sm.get("technicalName") or "").lower()

        if state_name and state_name not in PROCESSABLE_STATES:
            skipped_bad_state += 1
            continue

        line_items = attrs.get("lineItems") or []
        for li in line_items:
            li_attrs = li if isinstance(li, dict) else {}
            li_id = li_attrs.get("id")
            qty = int(li_attrs.get("quantity") or 0)
            product = li_attrs.get("product") or {}
            cf = product.get("customFields") or {}
            src = cf.get(CF_SOURCE_NUMBER)
            lot = int(cf.get(CF_LOT_SIZE) or 0)
            if not src or not lot:
                skipped_not_bundle += 1
                continue

            # Already processed?
            li_cf = li_attrs.get("customFields") or {}
            if li_cf.get(CF_PROCESSED):
                skipped_processed += 1
                continue

            consumed = qty * lot
            decrements[src] = decrements.get(src, 0) + consumed
            line_items_to_mark.append((li_id, consumed))
            print(f"  order_line {li_id}: bundle qty={qty} × lot={lot} → consume {consumed} pieces from base {src}")

    print()
    print(
        f"Skipped: {skipped_processed} already-processed, {skipped_not_bundle} non-bundle, {skipped_bad_state} bad-state"  # noqa: E501
    )
    print(f"Decrements to apply: {len(decrements)} base products, {len(line_items_to_mark)} order lines")

    if not decrements:
        print("Nothing to decrement.")
        return 0

    # Fetch current base stocks
    base_pns = list(decrements.keys())
    base_resp = sw.search(
        "product",
        {
            "limit": 100,
            "filter": [{"type": "equalsAny", "field": "productNumber", "value": base_pns}],
            "includes": {"product": ["id", "productNumber", "stock"]},
        },
    )
    base_map = {p.get("attributes", p)["productNumber"]: p for p in base_resp.get("data", [])}

    for pn, consume in decrements.items():
        if pn not in base_map:
            print(f"  WARN: base product {pn} not found, skipping")
            continue
        b = base_map[pn]
        bid = b["id"]
        cur = int(b.get("attributes", b)["stock"] or 0)
        new = max(0, cur - consume)
        print(f"  {pn}: {cur} → {new} (consume {consume})")
        try:
            sw.patch(f"/api/product/{bid}", {"stock": new})
        except Exception as e:
            print(f"    !! patch failed: {e}")
            return 3

    # Mark line items as processed (so we don't double-count next poll)
    for li_id, consumed in line_items_to_mark:
        try:
            sw.patch(f"/api/order-line-item/{li_id}", {"customFields": {CF_PROCESSED: consumed}})
        except Exception as e:
            print(f"    !! mark order_line {li_id} failed: {e}")

    print("\nDone. patches applied. Next stock-sync run will re-derive bundle stocks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
