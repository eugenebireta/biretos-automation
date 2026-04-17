"""
Shopware bundle stock-sync worker.

For every product whose customField biretos_bundle_source_number is set:
  derived_stock = floor(base_product.stock / biretos_bundle_lot_size)
  patch bundle product's stock to derived_stock if it changed.

Run on cron (every 15 min recommended). Idempotent — only patches when
the value actually changes.

Usage:
  python scripts/shopware_bundle_stock_sync.py             # dry-run, prints diffs
  python scripts/shopware_bundle_stock_sync.py --execute   # actually patches
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

SECRETS_ENV = Path("config/.secrets.env")
CF_SOURCE_NUMBER = "biretos_bundle_source_number"
CF_LOT_SIZE = "biretos_bundle_lot_size"


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
    def __init__(self, url: str, cid: str, csec: str):
        self.url = url.rstrip("/")
        self._cid = cid
        self._csec = csec
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
        r = self.s.patch(f"{self.url}{path}", headers=self._hdr(), json=body, timeout=30)
        if not r.ok:
            raise RuntimeError(f"PATCH {path} -> {r.status_code}: {r.text[:300]}")


def fetch_all_bundles(sw: Shopware) -> list[dict]:
    """All products with biretos_bundle_source_number set."""
    out: list[dict] = []
    page = 1
    while True:
        resp = sw.search(
            "product",
            {
                "limit": 100,
                "page": page,
                "filter": [
                    {
                        "type": "not",
                        "operator": "and",
                        "queries": [{"type": "equals", "field": f"customFields.{CF_SOURCE_NUMBER}", "value": None}],
                    }
                ],
                "includes": {"product": ["id", "productNumber", "stock", "customFields"]},
            },
        )
        data = resp.get("data", [])
        if not data:
            break
        out.extend(data)
        if len(data) < 100:
            break
        page += 1
    return out


def fetch_bases_by_number(sw: Shopware, numbers: set[str]) -> dict[str, dict]:
    """Map productNumber -> {id, stock} for given source product_numbers."""
    if not numbers:
        return {}
    resp = sw.search(
        "product",
        {
            "limit": max(100, len(numbers)),
            "filter": [{"type": "equalsAny", "field": "productNumber", "value": list(numbers)}],
            "includes": {"product": ["id", "productNumber", "stock"]},
        },
    )
    out: dict[str, dict] = {}
    for p in resp.get("data", []):
        attrs = p.get("attributes", p)
        pn = attrs.get("productNumber") or p.get("productNumber")
        out[pn] = {"id": p["id"], "stock": int(attrs.get("stock") or p.get("stock") or 0)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true", help="apply patches (default: dry-run)")
    args = ap.parse_args()

    env = load_secrets()
    url = env.get("SHOPWARE_URL")
    cid = env.get("SHOPWARE_CLIENT_ID")
    csec = env.get("SHOPWARE_CLIENT_SECRET")
    if not (url and cid and csec):
        print("ERROR: SHOPWARE_URL/CLIENT_ID/CLIENT_SECRET missing", file=sys.stderr)
        return 2

    sw = Shopware(url, cid, csec)

    print(f"URL:  {url}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")
    print()

    print("Fetching bundles...")
    bundles = fetch_all_bundles(sw)
    print(f"  {len(bundles)} bundle products found")

    if not bundles:
        print("Nothing to do.")
        return 0

    # Collect source product_numbers
    source_pns: set[str] = set()
    for b in bundles:
        cf = (b.get("attributes") or b).get("customFields") or b.get("customFields") or {}
        src = cf.get(CF_SOURCE_NUMBER)
        if src:
            source_pns.add(str(src))

    print(f"Fetching {len(source_pns)} source base products...")
    bases = fetch_bases_by_number(sw, source_pns)
    print(f"  {len(bases)} base products resolved")
    missing = source_pns - bases.keys()
    if missing:
        print(f"  WARNING: {len(missing)} base product_numbers not found: {list(missing)[:5]}...")

    print()
    print(f"{'bundle_pn':>14} {'lot':>4} {'src_pn':>14} {'src_stock':>9} {'derived':>7} {'current':>7} action")
    patches = 0
    skipped = 0
    for b in bundles:
        attrs = b.get("attributes", b)
        cf = attrs.get("customFields") or b.get("customFields") or {}
        bundle_pn = attrs.get("productNumber") or b.get("productNumber")
        src_pn = str(cf.get(CF_SOURCE_NUMBER) or "")
        lot = int(cf.get(CF_LOT_SIZE) or 0)
        cur_stock = int(attrs.get("stock") or b.get("stock") or 0)

        if not src_pn or not lot or src_pn not in bases:
            print(f"{bundle_pn:>14} {lot:>4} {src_pn:>14} {'?':>9} {'?':>7} {cur_stock:>7} SKIP (no base)")
            skipped += 1
            continue

        src_stock = bases[src_pn]["stock"]
        derived = src_stock // lot if lot > 0 else 0

        if derived == cur_stock:
            print(f"{bundle_pn:>14} {lot:>4} {src_pn:>14} {src_stock:>9} {derived:>7} {cur_stock:>7} no change")
            continue

        action = "PATCH" if args.execute else "WOULD-PATCH"
        print(f"{bundle_pn:>14} {lot:>4} {src_pn:>14} {src_stock:>9} {derived:>7} {cur_stock:>7} {action}")

        if args.execute:
            try:
                sw.patch(f"/api/product/{b['id']}", {"stock": derived})
                patches += 1
            except Exception as e:
                print(f"    !! patch failed: {e}")

    print()
    print(f"Done. patches={patches} skipped={skipped} total={len(bundles)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
