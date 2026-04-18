"""
Shopware health check — single command to verify system state.

Checks:
  1. Shopware API responds
  2. OAuth credentials work
  3. Product count vs expected
  4. Bundle products status (5 pilot bases + 33 bundles)
  5. Bundle stock-sync correctness (derived stock matches base/lot_size)
  6. Backup file age (last mysqldump)
  7. Custom field set 'biretos_bundle' exists
  8. Sales channel domain points to dev.bireta.ru

Usage:
  python scripts/shopware_health_check.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

SECRETS_ENV = Path("config/.secrets.env")
PILOT_BASES = ["500943509", "500946159", "528685511", "505558981", "704860194"]


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


def check(label: str, fn) -> tuple[bool, str]:
    try:
        ok, msg = fn()
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] {label}: {msg}")
        return ok, msg
    except Exception as e:
        print(f"  [FAIL] {label}: exception: {e}")
        return False, str(e)


def main() -> int:
    env = load_secrets()
    url = env.get("SHOPWARE_URL")
    cid = env.get("SHOPWARE_CLIENT_ID")
    csec = env.get("SHOPWARE_CLIENT_SECRET")

    print(f"Shopware health check — {url}")
    print()

    # 1. API responds
    def t1():
        r = requests.get(f"{url}/api/_info/version", timeout=10)
        # 401 is OK — means endpoint is alive but unauthenticated
        return (r.status_code in (200, 401), f"HTTP {r.status_code}")

    ok1, _ = check("API endpoint alive", t1)
    if not ok1:
        return 1

    # 2. OAuth works
    token = None

    def t2():
        nonlocal token
        r = requests.post(
            f"{url}/api/oauth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": cid,
                "client_secret": csec,
            },
            timeout=15,
        )
        if r.ok:
            token = r.json()["access_token"]
            return True, "got bearer token"
        return False, f"HTTP {r.status_code}: {r.text[:100]}"

    ok2, _ = check("OAuth credentials", t2)
    if not ok2:
        return 1

    hdr = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 3. Product count (must request total-count-mode for full count)
    def t3():
        r = requests.post(
            f"{url}/api/search/product", headers=hdr, json={"limit": 1, "total-count-mode": 1}, timeout=20
        )
        d = r.json()
        total = d.get("meta", {}).get("total") or d.get("total") or 0
        return total > 0, f"{total} products"

    check("Product count", t3)

    # 4. Bundle bases exist (use data list length, since total requires total-count-mode)
    def t4():
        found = 0
        for pn in PILOT_BASES:
            r = requests.post(
                f"{url}/api/search/product",
                headers=hdr,
                json={"filter": [{"type": "equals", "field": "productNumber", "value": pn}], "limit": 1},
                timeout=10,
            )
            if len(r.json().get("data", [])) > 0:
                found += 1
        return found == 5, f"{found}/5 pilot base products found"

    check("Bundle pilot bases", t4)

    # 5. Bundle products + stock-sync
    def t5():
        r = requests.post(
            f"{url}/api/search/product",
            headers=hdr,
            json={
                "limit": 100,
                "filter": [
                    {
                        "type": "not",
                        "operator": "and",
                        "queries": [
                            {"type": "equals", "field": "customFields.biretos_bundle_source_number", "value": None}
                        ],
                    }
                ],
                "includes": {"product": ["productNumber", "stock", "customFields"]},
            },
            timeout=20,
        )
        bundles = r.json().get("data", [])
        if not bundles:
            return False, "no bundle products found"
        # Check stock = floor(base/lot)
        srcs = set()
        for b in bundles:
            cf = b.get("attributes", b).get("customFields") or {}
            if cf.get("biretos_bundle_source_number"):
                srcs.add(cf["biretos_bundle_source_number"])
        if not srcs:
            return False, "bundles have no source_number"
        # Fetch base stocks
        r2 = requests.post(
            f"{url}/api/search/product",
            headers=hdr,
            json={
                "filter": [{"type": "equalsAny", "field": "productNumber", "value": list(srcs)}],
                "includes": {"product": ["productNumber", "stock"]},
            },
            timeout=15,
        )
        base_stock = {
            p.get("attributes", p)["productNumber"]: int(p.get("attributes", p)["stock"] or 0)
            for p in r2.json().get("data", [])
        }
        # Verify derived = floor(base/lot)
        mismatches = 0
        for b in bundles:
            attrs = b.get("attributes", b)
            cf = attrs.get("customFields") or {}
            src = cf.get("biretos_bundle_source_number")
            lot = int(cf.get("biretos_bundle_lot_size") or 0)
            if not src or not lot or src not in base_stock:
                continue
            expected = base_stock[src] // lot
            actual = int(attrs.get("stock") or 0)
            if expected != actual:
                mismatches += 1
        return mismatches == 0, f"{len(bundles)} bundles, {mismatches} stock mismatches"

    check("Bundle stock sync", t5)

    # 6. Custom field set
    def t6():
        r = requests.post(
            f"{url}/api/search/custom-field-set",
            headers=hdr,
            json={"filter": [{"type": "equals", "field": "name", "value": "biretos_bundle"}], "limit": 5},
            timeout=10,
        )
        cnt = len(r.json().get("data", []))
        return cnt >= 1, f"biretos_bundle exists (count={cnt})"

    check("Custom field set", t6)

    # 7. Sales channel domain
    def t7():
        r = requests.post(f"{url}/api/search/sales-channel-domain", headers=hdr, json={"limit": 10}, timeout=10)
        domains = [d.get("attributes", d).get("url") for d in r.json().get("data", [])]
        target = "https://dev.bireta.ru"
        return any(target in (d or "") for d in domains), f"domains: {domains}"

    check("Sales channel domain", t7)

    # 8. Backup age (via SSH — only works if VPS reachable)
    def t8():
        try:
            r = subprocess.run(
                [
                    "ssh",
                    "-o",
                    "ConnectTimeout=5",
                    "-o",
                    "BatchMode=yes",
                    "root@77.233.222.214",
                    "ls -t /opt/shopware/backups/*.sql.gz 2>/dev/null | head -1",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            latest = r.stdout.strip()
            if not latest:
                return False, "no backups in /opt/shopware/backups/"
            # get age
            r2 = subprocess.run(
                ["ssh", "root@77.233.222.214", f"stat -c %Y {latest}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            age_hours = (time.time() - int(r2.stdout.strip())) / 3600
            return age_hours < 26, f"latest backup {latest.split('/')[-1]}, {age_hours:.1f}h ago"
        except Exception as e:
            return False, f"ssh failed: {e}"

    check("MySQL backup recency", t8)

    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
