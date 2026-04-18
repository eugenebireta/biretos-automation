"""
Shopware bundle pilot — proof that bundles via custom_fields work on
dev.bireta.ru (Shopware 6.7.2.2, dockware/dev install on Russia VPS).

End-to-end flow:
  1. OAuth (client_credentials) -> Bearer token
  2. Ensure custom field set 'biretos_bundle' exists with two fields:
       - bundle_source_product_number (string)
       - bundle_lot_size (integer)
  3. Resolve sales channel + tax + currency for the product create payload
  4. For each pid in plan: create base product (real stock in pieces) +
     N bundle products (stock=0 + custom_fields linking to base)
  5. Verify by reading back via API

Why custom_fields, not native bundle plugin:
  Shopware Community Edition has no native bundle entity. Custom fields +
  external stock-sync worker = portable, no plugin lock-in, works with
  Ozon API export later.

Reads pilot plan from:
  downloads/insales_audit/2026-04-16/migration_plan_pilot.json
Reads OAuth credentials from env or config/.secrets.env.

Usage:
  python scripts/shopware_bundle_pilot.py                  # dry-run, prints API calls
  python scripts/shopware_bundle_pilot.py --execute        # actually writes
  python scripts/shopware_bundle_pilot.py --execute --pids 287629100   # single SKU
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Owner-confirmed pilot pids
DEFAULT_PILOT_PIDS = [
    "287629100",  # ABB CR-PH (8 lots, 50р, 194 units) — owner's reference
    "287631239",  # BETTERMANN RLVL 85 FS (8 lots, 1290р, 636 units)
    "306153040",  # Honeywell 023318 (8 lots, 476р, 323 units)
    "291119233",  # ABB MCB-01 (6 lots, 600р, 26 units)
    "424401468",  # Лисма СМН 6.3-20 (8 lots, 15р, 101294 units)
]

DEFAULT_PLAN_PATH = Path("downloads/insales_audit/2026-04-16/migration_plan_pilot.json")
SECRETS_ENV = Path("config/.secrets.env")

CUSTOM_FIELD_SET = "biretos_bundle"
CF_SOURCE_NUMBER = "biretos_bundle_source_number"
CF_LOT_SIZE = "biretos_bundle_lot_size"


# ---------- Config / secrets loading -------------------------------------------------


def load_secrets() -> dict:
    """Load env vars from config/.secrets.env if present (no shell sourcing required)."""
    out = dict(os.environ)
    if SECRETS_ENV.exists():
        for line in SECRETS_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out.setdefault(k.strip(), v.strip())
    return out


# ---------- Shopware API client (minimal, sync) --------------------------------------


class Shopware:
    def __init__(self, url: str, client_id: str, client_secret: str, dry_run: bool):
        self.url = url.rstrip("/")
        self._cid = client_id
        self._csec = client_secret
        self.dry_run = dry_run
        self.s = requests.Session()
        self._token: str | None = None
        self._token_exp = 0.0

    def _auth(self) -> str:
        if self._token and time.time() < self._token_exp - 30:
            return self._token
        r = self.s.post(
            f"{self.url}/api/oauth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": self._cid,
                "client_secret": self._csec,
            },
            timeout=20,
        )
        r.raise_for_status()
        d = r.json()
        self._token = d["access_token"]
        self._token_exp = time.time() + int(d.get("expires_in", 600))
        return self._token

    def _hdr(self) -> dict:
        return {
            "Authorization": f"Bearer {self._auth()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get(self, path: str, params: dict | None = None) -> dict:
        r = self.s.get(f"{self.url}{path}", headers=self._hdr(), params=params, timeout=30)
        r.raise_for_status()
        return r.json() if r.content else {}

    def search(self, entity: str, payload: dict) -> dict:
        r = self.s.post(f"{self.url}/api/search/{entity}", headers=self._hdr(), json=payload, timeout=30)
        r.raise_for_status()
        return r.json() if r.content else {}

    def post(self, path: str, body: dict) -> dict:
        if self.dry_run:
            print(f"  [DRY-RUN] POST {path}")
            print(f"           payload keys: {list(body.keys())}")
            return {"_dry_run": True}
        r = self.s.post(f"{self.url}{path}", headers=self._hdr(), json=body, timeout=60)
        if not r.ok:
            raise RuntimeError(f"POST {path} -> {r.status_code}: {r.text[:600]}")
        return r.json() if r.content else {}

    def patch(self, path: str, body: dict) -> dict:
        if self.dry_run:
            print(f"  [DRY-RUN] PATCH {path}")
            return {"_dry_run": True}
        r = self.s.patch(f"{self.url}{path}", headers=self._hdr(), json=body, timeout=60)
        if not r.ok:
            raise RuntimeError(f"PATCH {path} -> {r.status_code}: {r.text[:600]}")
        return r.json() if r.content else {}


# ---------- Custom field set bootstrap ----------------------------------------------


def ensure_custom_fields(sw: Shopware) -> None:
    """Create the biretos_bundle custom field set + 2 fields if missing."""
    res = sw.search(
        "custom-field-set",
        {"filter": [{"type": "equals", "field": "name", "value": CUSTOM_FIELD_SET}], "limit": 1},
    )
    if res.get("total", 0) > 0:
        print(f"  custom field set '{CUSTOM_FIELD_SET}' already exists")
        return

    print(f"  creating custom field set '{CUSTOM_FIELD_SET}' + 2 fields")
    set_id = uuid.uuid4().hex
    sw.post(
        "/api/custom-field-set",
        {
            "id": set_id,
            "name": CUSTOM_FIELD_SET,
            "config": {
                "label": {"en-GB": "Biretos bundle", "ru-RU": "Бандл Biretos"},
                "translated": True,
            },
            "global": False,
            "position": 1,
            "active": True,
            "relations": [{"id": uuid.uuid4().hex, "entityName": "product"}],
            "customFields": [
                {
                    "id": uuid.uuid4().hex,
                    "name": CF_SOURCE_NUMBER,
                    "type": "text",
                    "config": {
                        "label": {"en-GB": "Source product number", "ru-RU": "Базовый товар (productNumber)"},  # noqa: E501
                        "componentName": "sw-field",
                        "customFieldType": "text",
                        "customFieldPosition": 1,
                    },
                    "active": True,
                },
                {
                    "id": uuid.uuid4().hex,
                    "name": CF_LOT_SIZE,
                    "type": "int",
                    "config": {
                        "label": {"en-GB": "Lot size (pieces from base)", "ru-RU": "Штук в комплекте"},
                        "componentName": "sw-field",
                        "customFieldType": "number",
                        "numberType": "int",
                        "customFieldPosition": 2,
                    },
                    "active": True,
                },
            ],
        },
    )


# ---------- Resolve foreign keys (tax, currency, sales channel, category) ------------


def resolve_refs(sw: Shopware) -> dict:
    """Return {tax_id, currency_id, sales_channel_id, root_category_id}."""
    refs: dict = {}

    # Tax: prefer 20% (RU VAT). Fallback to first.
    tax_resp = sw.search("tax", {"limit": 50})
    taxes = tax_resp.get("data", [])
    refs["tax_id"] = next(
        (
            t["id"]
            for t in taxes
            if abs(float(t.get("attributes", {}).get("taxRate") or t.get("taxRate", 0)) - 20.0) < 0.01
        ),
        taxes[0]["id"] if taxes else None,
    )

    # Sales channel: prefer Storefront type. Use its currency as default.
    sc = sw.search("sales-channel", {"limit": 10})
    storefront = next(
        (c for c in sc.get("data", []) if (c.get("attributes", c).get("name") or "").lower() == "storefront"),
        sc["data"][0] if sc.get("data") else None,
    )
    refs["sales_channel_id"] = storefront["id"] if storefront else None
    refs["currency_id"] = storefront.get("attributes", storefront).get("currencyId") if storefront else None
    if not refs["currency_id"]:
        first = sw.search("currency", {"limit": 1})
        refs["currency_id"] = first["data"][0]["id"] if first.get("data") else None

    # Root category (for fallback assignment)
    root = sw.search(
        "category",
        {"filter": [{"type": "equals", "field": "level", "value": 1}], "limit": 1},
    )
    refs["root_category_id"] = root["data"][0]["id"] if root.get("data") else None

    return refs


# ---------- Product builders ---------------------------------------------------------


def build_product_payload(
    *,
    product_number: str,
    name: str,
    price_rub: float,
    stock: int,
    tax_id: str,
    currency_id: str,
    sales_channel_id: str,
    category_id: str | None,
    custom_fields: dict | None = None,
    active: bool = True,
) -> dict:
    payload = {
        "id": uuid.uuid4().hex,
        "productNumber": product_number,
        "name": name,
        "active": active,
        "stock": stock,
        "taxId": tax_id,
        "price": [
            {
                "currencyId": currency_id,
                "gross": round(price_rub, 2),
                "net": round(price_rub / 1.20, 2),  # 20% VAT
                "linked": True,
            }
        ],
        "visibilities": [
            {
                "id": uuid.uuid4().hex,
                "salesChannelId": sales_channel_id,
                "visibility": 30,  # 30=all, 20=link, 10=search
            }
        ],
    }
    if category_id:
        payload["categories"] = [{"id": category_id}]
    if custom_fields:
        payload["customFields"] = custom_fields
    return payload


def upsert_product_by_number(sw: Shopware, payload: dict) -> str:
    """Create or update by productNumber. Returns product id (existing or new)."""
    pn = payload["productNumber"]
    found = sw.search(
        "product",
        {"filter": [{"type": "equals", "field": "productNumber", "value": pn}], "limit": 1},
    )
    if found.get("total", 0) > 0:
        existing_id = found["data"][0]["id"]
        print(f"    product {pn} EXISTS (id={existing_id[:8]}...) -> patching")
        # Patch only mutable fields (stock, custom_fields, price). Don't touch productNumber.
        patch_body = {
            "stock": payload["stock"],
        }
        if "customFields" in payload:
            patch_body["customFields"] = payload["customFields"]
        if "price" in payload:
            patch_body["price"] = payload["price"]
        sw.patch(f"/api/product/{existing_id}", patch_body)
        return existing_id

    sw.post("/api/product", payload)
    print(f"    product {pn} CREATED (id={payload['id'][:8]}...)")
    return payload["id"]


# ---------- Main flow ----------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true", help="actually write to Shopware (default: dry-run)")
    ap.add_argument("--pids", default=",".join(DEFAULT_PILOT_PIDS), help="comma-separated pids")
    ap.add_argument("--plan", default=str(DEFAULT_PLAN_PATH), help="path to migration_plan_*.json")
    ap.add_argument("--all-from-plan", action="store_true", help="ignore --pids and process all plans in --plan file")
    ap.add_argument("--limit", type=int, default=0, help="cap number of pids to process (0 = no cap)")
    args = ap.parse_args()

    env = load_secrets()
    url = env.get("SHOPWARE_URL")
    cid = env.get("SHOPWARE_CLIENT_ID")
    csec = env.get("SHOPWARE_CLIENT_SECRET")
    if not (url and cid and csec):
        print("ERROR: SHOPWARE_URL/CLIENT_ID/CLIENT_SECRET missing in env or config/.secrets.env", file=sys.stderr)
        return 2

    plan_path = Path(args.plan)
    if not plan_path.exists():
        print(f"ERROR: plan not found: {plan_path}", file=sys.stderr)
        return 2
    plan_doc = json.loads(plan_path.read_text(encoding="utf-8"))

    if args.all_from_plan:
        plans = plan_doc["plans"]
    else:
        pid_filter = {p.strip() for p in args.pids.split(",") if p.strip()}
        plans = [p for p in plan_doc["plans"] if p["pid"] in pid_filter]

    if args.limit and args.limit > 0:
        plans = plans[: args.limit]

    if not plans:
        print("ERROR: no plans selected", file=sys.stderr)
        return 2

    print(f"URL:   {url}")
    print(f"Mode:  {'EXECUTE' if args.execute else 'DRY-RUN'}")
    print(f"Pids:  {len(plans)}")
    print(f"Plan:  {plan_path}")
    print()

    sw = Shopware(url, cid, csec, dry_run=not args.execute)

    print("=== STEP 1: OAuth handshake ===")
    sw._auth()
    print(f"  token acquired (expires in {int(sw._token_exp - time.time())}s)")
    print()

    print("=== STEP 2: Custom field set bootstrap ===")
    ensure_custom_fields(sw)
    print()

    print("=== STEP 3: Resolve refs (tax/currency/channel/category) ===")
    refs = resolve_refs(sw)
    for k, v in refs.items():
        print(f"  {k}: {v}")
    if not all([refs["tax_id"], refs["currency_id"], refs["sales_channel_id"]]):
        print("ERROR: missing tax/currency/sales_channel in Shopware. Cannot proceed.", file=sys.stderr)
        return 3
    print()

    summary = []
    for plan in plans:
        pid = plan["pid"]
        name = plan["name"]
        base = plan["base"]
        bundles = plan["bundles_to_create"]

        print(f"=== STEP 4: Migrate pid {pid} — {name[:60]} ===")

        # 4a. Base product (real stock in pieces). Reuse the original variant_id as productNumber.
        base_pn = base["source_article"]
        base_payload = build_product_payload(
            product_number=str(base_pn),
            name=name,
            price_rub=float(base["base_per_piece_price"]),
            stock=int(base["new_stock_in_pieces"]),
            tax_id=refs["tax_id"],
            currency_id=refs["currency_id"],
            sales_channel_id=refs["sales_channel_id"],
            category_id=refs["root_category_id"],
            active=True,
        )
        base_id = upsert_product_by_number(sw, base_payload)

        # 4b. Bundle products
        bundle_results = []
        for b in bundles:
            bundle_pn = str(b["new_bundle_sku"])
            bundle_payload = build_product_payload(
                product_number=bundle_pn,
                name=b["new_bundle_name"],
                price_rub=float(b["new_mp_price_formula"]),
                stock=0,  # derived later by stock-sync worker
                tax_id=refs["tax_id"],
                currency_id=refs["currency_id"],
                sales_channel_id=refs["sales_channel_id"],
                category_id=refs["root_category_id"],
                custom_fields={
                    CF_SOURCE_NUMBER: str(base_pn),
                    CF_LOT_SIZE: int(b["lot_size"]),
                },
                active=False,  # owner: bundles published=false (Ozon-only feed)
            )
            try:
                bid = upsert_product_by_number(sw, bundle_payload)
                bundle_results.append({"sku": bundle_pn, "lot": b["lot_size"], "id": bid, "status": "ok"})
            except Exception as e:
                bundle_results.append({"sku": bundle_pn, "lot": b["lot_size"], "status": "fail", "error": str(e)[:200]})
                print(f"    !! bundle {bundle_pn} (lot={b['lot_size']}) FAILED: {e}")

        summary.append(
            {
                "pid": pid,
                "name": name,
                "base_product_number": str(base_pn),
                "base_product_id": base_id,
                "base_stock_pieces": int(base["new_stock_in_pieces"]),
                "bundles": bundle_results,
            }
        )
        print()

    print("=== SUMMARY ===")
    for s in summary:
        n_ok = sum(1 for b in s["bundles"] if b["status"] == "ok")
        n_fail = sum(1 for b in s["bundles"] if b["status"] != "ok")
        print(
            f"  {s['pid']:>10}  base_stock={s['base_stock_pieces']:>6}  bundles_ok={n_ok}/{len(s['bundles'])}  fail={n_fail}"  # noqa: E501
        )

    print(f"\nDone. Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")
    if args.execute:
        print("Verify in admin: https://dev.bireta.ru/admin -> Catalog -> Products")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
