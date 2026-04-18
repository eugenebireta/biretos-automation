"""
InSales bundle migration — Stage 3: API applier (executes the dry-run plan).

Reads migration_plan_pilot.json from Stage 2 and applies it via InSales REST API:
  1. GET /admin/products/{pid}.json   -> save full snapshot to backup dir (always)
  2. For each bundle in plan:
       POST /admin/products.json with bundle:true + product_bundle_components_attributes
  3. PUT /admin/products/{pid}.json   -> update base variant stock + destroy old lot variants

Default mode is DRY-RUN: prints every API call that WOULD be made, only GETs
(for backup snapshots) actually hit the network. Pass --execute to write.

Auth: HTTP Basic with InSales API key (id + password).
  Env: INSALES_API_ID, INSALES_API_PASSWORD, INSALES_ACCOUNT
  CLI overrides env if provided.

Rate limit: InSales = 500 req / 5 min. Default throttle = 0.7s/req (~85 req/min).

Usage:
  # dry-run (safe, only GETs for backup)
  python scripts/insales_bundle_apply.py \
    --plan downloads/insales_audit/2026-04-16/migration_plan_pilot.json \
    --account myshop

  # actually apply (will prompt for confirmation)
  python scripts/insales_bundle_apply.py \
    --plan downloads/insales_audit/2026-04-16/migration_plan_pilot.json \
    --account myshop --execute

  # apply only one pid (for incremental rollout)
  python scripts/insales_bundle_apply.py --plan ... --account myshop \
    --execute --pids 287629100
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Throttle: stay under InSales rate limit (500 req / 5 min = 100 req/min)
THROTTLE_SECONDS = 0.7

# Default backup root
BACKUP_ROOT = Path("downloads/insales_backup")
LOG_PATH = Path("downloads/insales_bundle_migration_log.jsonl")


class InSalesClient:
    """Thin REST wrapper. NO retry orchestration — caller decides on errors."""

    def __init__(self, account: str, api_id: str, api_password: str, dry_run: bool):
        self.account = account
        self.base_url = f"https://{account}.myinsales.ru"
        self.auth = HTTPBasicAuth(api_id, api_password)
        self.dry_run = dry_run
        self.session = requests.Session()
        self._last_call = 0.0

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < THROTTLE_SECONDS:
            time.sleep(THROTTLE_SECONDS - elapsed)
        self._last_call = time.time()

    def get_product(self, pid: str) -> dict:
        """Always real (read-only, used for backup snapshots even in dry-run)."""
        self._throttle()
        url = f"{self.base_url}/admin/products/{pid}.json"
        r = self.session.get(url, auth=self.auth, timeout=30)
        r.raise_for_status()
        return r.json()

    def create_bundle(self, payload: dict) -> dict:
        """POST /admin/products.json with bundle:true. Skipped in dry-run."""
        url = f"{self.base_url}/admin/products.json"
        if self.dry_run:
            return {"_dry_run": True, "would_POST": url, "payload": payload}
        self._throttle()
        r = self.session.post(url, json=payload, auth=self.auth, timeout=60)
        if not r.ok:
            raise RuntimeError(f"POST {url} -> {r.status_code}: {r.text[:500]}")
        return r.json()

    def update_product(self, pid: str, payload: dict) -> dict:
        """PUT /admin/products/{pid}.json. Skipped in dry-run."""
        url = f"{self.base_url}/admin/products/{pid}.json"
        if self.dry_run:
            return {"_dry_run": True, "would_PUT": url, "payload": payload}
        self._throttle()
        r = self.session.put(url, json=payload, auth=self.auth, timeout=60)
        if not r.ok:
            raise RuntimeError(f"PUT {url} -> {r.status_code}: {r.text[:500]}")
        return r.json()


def build_bundle_payload(plan: dict, bundle: dict, source_product: dict) -> dict:
    """
    Build POST /admin/products.json body for one bundle product.

    Inherits category_id from the source product so the bundle lands in the
    same category tree on Ozon.
    """
    # Pick category_id (same as base product). InSales uses 'category_id' or
    # 'collections' depending on schema version; include both for safety.
    category_id = source_product.get("category_id")
    collections = source_product.get("collections", [])

    payload = {
        "product": {
            "title": bundle["new_bundle_name"],
            "bundle": True,
            "published": False,  # owner: bundles only on Ozon, hidden from site
            "variants_attributes": [
                {
                    "sku": bundle["new_bundle_sku"],
                    "price": bundle["new_mp_price_formula"],
                    "quantity": bundle["stock_to_initialize"],  # 0 — drained from base
                }
            ],
            "product_bundle_components_attributes": [
                {
                    "variant_id": int(bundle["consumes_from_base_variant_id"]),
                    "quantity": bundle["consumes_quantity"],
                    "free": False,
                }
            ],
        }
    }
    if category_id:
        payload["product"]["category_id"] = category_id
    if collections:
        # InSales accepts collection_ids on create; safest to map ids only
        coll_ids = [c.get("id") for c in collections if isinstance(c, dict) and c.get("id")]
        if coll_ids:
            payload["product"]["collections_ids"] = coll_ids
    return payload


def build_base_update_payload(plan: dict) -> dict:
    """
    Build PUT /admin/products/{pid}.json body to:
      - set base variant's quantity to total_units (in pieces)
      - destroy all other (lot-size) variants from the source product
    """
    base = plan["base"]
    variants_attributes = [
        {
            "id": int(base["source_variant_id"]),
            "quantity": base["new_stock_in_pieces"],
        }
    ]
    for vid in plan["variants_to_destroy_after_bundles"]:
        variants_attributes.append({"id": int(vid), "_destroy": True})

    return {
        "product": {
            "variants_attributes": variants_attributes,
        }
    }


def append_log(entry: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def apply_one_pid(client: InSalesClient, plan: dict, backup_dir: Path) -> dict:
    """
    Migrate one product. Returns {pid, status, created_bundles[], errors[]}.

    Order of ops:
      1. GET source product -> snapshot
      2. POST each bundle (collect new product/variant IDs)
      3. PUT source product (set base stock, destroy old variants)
    """
    pid = plan["pid"]
    out: dict = {
        "pid": pid,
        "name": plan["name"],
        "started_at": datetime.now().isoformat(),
        "status": "in_progress",
        "snapshot_path": None,
        "bundles_created": [],
        "base_update_response": None,
        "errors": [],
    }

    # 1. Backup snapshot (always, even in dry-run)
    print(f"\n[{pid}] {plan['name'][:60]}")
    print("  GET snapshot...", end=" ")
    try:
        snapshot = client.get_product(pid)
        snap_path = backup_dir / f"{pid}_pre_migration.json"
        snap_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        out["snapshot_path"] = str(snap_path)
        print(f"OK ({snap_path.name})")
    except Exception as e:
        print(f"FAIL: {e}")
        out["errors"].append({"step": "get_snapshot", "error": str(e)})
        out["status"] = "failed_pre_backup"
        append_log(out)
        return out

    source_product = snapshot.get("product", snapshot)

    # 2. Create bundles
    for bundle in plan["bundles_to_create"]:
        lot = bundle["lot_size"]
        print(f"  POST bundle lot={lot:>4} mp={bundle['new_mp_price_formula']}...", end=" ")
        try:
            payload = build_bundle_payload(plan, bundle, source_product)
            resp = client.create_bundle(payload)
            if resp.get("_dry_run"):
                out["bundles_created"].append({"lot_size": lot, "dry_run": True, "would_post": resp})
                print("DRY-RUN")
            else:
                product = resp.get("product", resp)
                new_pid = product.get("id")
                new_variant_id = (product.get("variants") or [{}])[0].get("id")
                out["bundles_created"].append(
                    {
                        "lot_size": lot,
                        "new_bundle_product_id": new_pid,
                        "new_bundle_variant_id": new_variant_id,
                        "old_variant_id": bundle["old_variant_id"],
                    }
                )
                print(f"OK new_pid={new_pid}")
        except Exception as e:
            print(f"FAIL: {e}")
            out["errors"].append(
                {
                    "step": f"create_bundle_lot_{lot}",
                    "error": str(e),
                }
            )
            out["status"] = "failed_partial"
            append_log(out)
            return out

    # 3. Update base product (set stock, destroy old lot variants)
    print(
        f"  PUT base product (stock={plan['base']['new_stock_in_pieces']}, destroy {len(plan['variants_to_destroy_after_bundles'])} variants)...",  # noqa: E501
        end=" ",
    )
    try:
        payload = build_base_update_payload(plan)
        resp = client.update_product(pid, payload)
        out["base_update_response"] = "DRY-RUN" if resp.get("_dry_run") else "OK"
        print(out["base_update_response"])
    except Exception as e:
        print(f"FAIL: {e}")
        out["errors"].append({"step": "update_base", "error": str(e)})
        out["status"] = "failed_post_bundles"  # CRITICAL: bundles created but base not cleaned
        append_log(out)
        return out

    out["status"] = "dry_run_ok" if client.dry_run else "completed"
    out["completed_at"] = datetime.now().isoformat()
    append_log(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan", required=True, help="Path to migration_plan_pilot.json")
    ap.add_argument(
        "--account",
        default=os.environ.get("INSALES_ACCOUNT"),
        help="InSales subdomain (e.g. 'myshop' for myshop.myinsales.ru). Env: INSALES_ACCOUNT",
    )
    ap.add_argument("--api-id", default=os.environ.get("INSALES_API_ID"), help="API key id. Env: INSALES_API_ID")
    ap.add_argument(
        "--api-password",
        default=os.environ.get("INSALES_API_PASSWORD"),
        help="API key password. Env: INSALES_API_PASSWORD",
    )
    ap.add_argument("--pids", default="", help="Comma-separated subset of pids (default: all in plan)")
    ap.add_argument(
        "--execute",
        action="store_true",
        help="Actually write to InSales. Without this flag = dry-run (only GETs for backup).",
    )
    ap.add_argument(
        "--backup-dir", default=None, help="Backup snapshot dir (default: downloads/insales_backup/<today>/)"
    )
    ap.add_argument("--yes", action="store_true", help="Skip interactive confirmation prompt before --execute")
    args = ap.parse_args()

    if not args.account or not args.api_id or not args.api_password:
        print(
            "ERROR: --account, --api-id, --api-password required (or set env INSALES_ACCOUNT/INSALES_API_ID/INSALES_API_PASSWORD)",  # noqa: E501
            file=sys.stderr,
        )
        print("\nHow to get InSales API credentials:", file=sys.stderr)
        print("  1. Log into your InSales admin", file=sys.stderr)
        print("  2. Go to: Настройки → Разработчикам → API", file=sys.stderr)
        print("  3. Create new API key with permissions: Товары (read+write)", file=sys.stderr)
        print("  4. Copy 'Идентификатор' -> --api-id", file=sys.stderr)
        print("  5. Copy 'Пароль' -> --api-password", file=sys.stderr)
        return 2

    plan_path = Path(args.plan)
    if not plan_path.exists():
        print(f"ERROR: plan not found: {plan_path}", file=sys.stderr)
        return 2
    plan_doc = json.loads(plan_path.read_text(encoding="utf-8"))
    plans = plan_doc["plans"]

    pid_filter = {p.strip() for p in args.pids.split(",") if p.strip()}
    if pid_filter:
        plans = [p for p in plans if p["pid"] in pid_filter]
    if not plans:
        print("ERROR: no plans match --pids filter", file=sys.stderr)
        return 2

    backup_dir = Path(args.backup_dir) if args.backup_dir else BACKUP_ROOT / datetime.now().strftime("%Y-%m-%d")
    backup_dir.mkdir(parents=True, exist_ok=True)

    print(f"Plan:        {plan_path}")
    print(f"Pids:        {len(plans)} ({', '.join(p['pid'] for p in plans)})")
    print(f"Account:     {args.account}.myinsales.ru")
    print(f"Backup dir:  {backup_dir.resolve()}")
    print(f"Mode:        {'EXECUTE (writes will happen)' if args.execute else 'DRY-RUN (only GET for backup)'}")
    print(f"Throttle:    {THROTTLE_SECONDS}s between requests")
    print(f"Formula:     {plan_doc['pricing_formula']}")

    if args.execute and not args.yes:
        total_bundles = sum(len(p["bundles_to_create"]) for p in plans)
        total_destroys = sum(len(p["variants_to_destroy_after_bundles"]) for p in plans)
        print("\n!! ABOUT TO WRITE TO INSALES:")
        print(f"   - Update {len(plans)} base products (set stock, destroy {total_destroys} old variants)")
        print(f"   - Create {total_bundles} new bundle products (published=false, Ozon-only)")
        ans = input("\nType 'yes' to proceed: ").strip().lower()
        if ans != "yes":
            print("Aborted.")
            return 1

    client = InSalesClient(args.account, args.api_id, args.api_password, dry_run=not args.execute)

    results = []
    for plan in plans:
        result = apply_one_pid(client, plan, backup_dir)
        results.append(result)
        if result["status"].startswith("failed"):
            print(f"\n!! Stopped on first failure (pid {plan['pid']}). See log: {LOG_PATH}")
            print(f"   Status: {result['status']}")
            print(f"   Snapshot for rollback: {result['snapshot_path']}")
            break

    print(f"\n=== Summary ({len(results)}/{len(plans)} processed) ===")
    for r in results:
        n_bundles = len(r["bundles_created"])
        print(f"  {r['pid']}  {r['status']:20s}  bundles={n_bundles}  {r['name'][:50]}")

    print(f"\nLog: {LOG_PATH.resolve()}")
    print(f"Snapshots: {backup_dir.resolve()}")
    return 0 if all(r["status"] in ("completed", "dry_run_ok") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
