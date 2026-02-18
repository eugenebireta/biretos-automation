from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from canon_registry import CanonRegistry
from clients import ShopwareClient, ShopwareConfig
from import_steps import ProductImportState, STEP_ORDER
from import_steps import categories, manufacturer, media, prices, skeleton, verify, visibilities
from normalize_entities import EntityNormalizer

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = ROOT / "insales_snapshot" / "products.ndjson"
CATEGORY_TREE_PATH = ROOT / "insales_snapshot" / "categories_with_paths.json"
MIGRATION_MAP_PATH = ROOT / "migration_map.json"
REPORTS_DIR = ROOT / "_reports"

STEPS = [
    skeleton,
    manufacturer,
    categories,
    media,
    prices,
    visibilities,
    verify,
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic Kalashnikov-grade РёРјРїРѕСЂС‚ РёР· snapshot РІ Shopware 6")
    parser.add_argument("--config", default=str(ROOT / "config.json"))
    parser.add_argument("--batch", choices=["5", "10", "all"], default="5")
    parser.add_argument("--skus", type=str, default="")
    parser.add_argument("--reset", action="store_true", help="Р’С‹РїРѕР»РЅРёС‚СЊ reset РїРµСЂРµРґ РёРјРїРѕСЂС‚РѕРј")
    parser.add_argument("--normalize", action="store_true", help="Р—Р°РїСѓСЃС‚РёС‚СЊ normalize_entities РїРµСЂРµРґ РёРјРїРѕСЂС‚РѕРј")
    parser.add_argument("--apply", action="store_true", help="РџСЂРёРјРµРЅРёС‚СЊ РёР·РјРµРЅРµРЅРёСЏ (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="РџСЂРёРЅСѓРґРёС‚РµР»СЊРЅРѕ dry-run")
    return parser.parse_args()


def load_config(config_path: str) -> Dict[str, str]:
    with open(config_path, "r", encoding="utf-8") as handler:
        raw = json.load(handler)
    return raw["shopware"]


def build_client(config: Dict[str, str]) -> ShopwareClient:
    return ShopwareClient(
        ShopwareConfig(
            url=config["url"],
            access_key_id=config["access_key_id"],
            secret_access_key=config["secret_access_key"],
        )
    )


def ensure_files_exist() -> None:
    for path in [SNAPSHOT_PATH, CATEGORY_TREE_PATH, MIGRATION_MAP_PATH]:
        if not path.exists():
            raise FileNotFoundError(f"РќРµ РЅР°Р№РґРµРЅ РѕР±СЏР·Р°С‚РµР»СЊРЅС‹Р№ С„Р°Р№Р»: {path}")


def load_snapshot_products() -> Dict[str, Dict]:
    products: Dict[str, Dict] = {}
    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as handler:
        for line in handler:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            variants = data.get("variants") or []
            variant = variants[0] if variants else {}
            sku = str(variant.get("sku") or data.get("sku") or data.get("id") or "").strip()
            if not sku:
                continue
            products[sku] = data
    return products


def select_skus(all_skus: List[str], args: argparse.Namespace) -> List[str]:
    if args.skus:
        requested = [sku.strip() for sku in args.skus.split(",") if sku.strip()]
        return [sku for sku in requested if sku in all_skus]

    if args.batch == "all":
        return all_skus
    count = int(args.batch)
    return all_skus[:count]


def load_category_parents() -> Dict[str, Optional[str]]:
    with open(CATEGORY_TREE_PATH, "r", encoding="utf-8") as handler:
        data = json.load(handler)
    parents: Dict[str, Optional[str]] = {}
    for item in data:
        parents[str(item["id"])] = str(item.get("parent_id")) if item.get("parent_id") else None
    return parents


def load_category_map() -> Dict[str, str]:
    with open(MIGRATION_MAP_PATH, "r", encoding="utf-8") as handler:
        data = json.load(handler)
    return {str(key): value for key, value in data.get("categories", {}).items()}


def maybe_run_reset(args: argparse.Namespace, dry_run: bool) -> None:
    if not args.reset:
        return
    if dry_run:
        print("[RESET] Dry-run: reset_shopware_for_test.py РїСЂРѕРїСѓС‰РµРЅ")
        return
    script = ROOT / "src" / "reset_shopware_for_test.py"
    cmd = [sys.executable, str(script)]
    if args.apply:
        cmd.append("--apply")
    subprocess.run(cmd, check=True)


def maybe_run_normalize(
    args: argparse.Namespace,
    client: ShopwareClient,
    registry: CanonRegistry,
    dry_run: bool,
) -> None:
    if not args.normalize:
        return
    normalizer = EntityNormalizer(client, registry, dry_run)
    normalizer.normalize_manufacturers()
    normalizer.normalize_rules()


def build_base_context(
    client: ShopwareClient,
    dry_run: bool,
) -> Dict[str, Any]:
    tax_id = client.get_standard_tax_id()
    currency_id = client.get_currency_id("RUB")
    sales_channel_id = client.get_storefront_sales_channel_id()
    media_folder_id = client.get_product_media_folder_id()
    return {
        "dry_run": dry_run,
        "tax_id": tax_id,
        "currency_id": currency_id,
        "sales_channel_id": sales_channel_id,
        "media_folder_id": media_folder_id,
    }


def run_steps(
    client: ShopwareClient,
    registry: CanonRegistry,
    product: Dict[str, Any],
    base_context: Dict[str, Any],
    category_map: Dict[str, str],
    category_parents: Dict[str, Optional[str]],
    sku: str,
) -> ProductImportState:
    variant = (product.get("variants") or [{}])[0]
    context = dict(base_context)
    context["variant"] = variant
    context["category_map"] = category_map
    context["category_parents"] = category_parents

    state = ProductImportState(sku=sku)
    for step in STEPS:
        state = step.run(client, registry, product, state, context)
    return state


def write_reports(states: List[ProductImportState], label: str, dry_run: bool) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS_DIR / f"pipeline_batch_{label}_details.json"
    md_path = REPORTS_DIR / f"pipeline_batch_{label}_summary.md"

    payload = []
    for state in states:
        payload.append(
            {
                "sku": state.sku,
                "product_id": state.product_id,
                "steps": {name: state.steps[name].value for name in STEP_ORDER},
                "errors": state.errors,
                "diagnostics": state.diagnostics,
            }
        )

    with open(json_path, "w", encoding="utf-8") as handler:
        json.dump({"dry_run": dry_run, "items": payload}, handler, ensure_ascii=False, indent=2)

    success_count = sum(1 for state in states if state.is_successful())
    lines = [
        f"# Pipeline batch {label}",
        f"- Dry run: {'yes' if dry_run else 'no'}",
        f"- Items: {len(states)}",
        f"- Fully successful: {success_count}",
    ]
    for state in states:
        status_line = ", ".join(f"{step}:{state.steps[step].value}" for step in STEP_ORDER)
        lines.append(f"* {state.sku} :: {status_line}")
        if state.errors:
            lines.append(f"  - errors: {state.errors}")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    dry_run = True
    if args.apply:
        dry_run = False
    elif args.dry_run:
        dry_run = True

    ensure_files_exist()
    config = load_config(args.config)
    client = build_client(config)
    registry = CanonRegistry(client)

    maybe_run_reset(args, dry_run)
    maybe_run_normalize(args, client, registry, dry_run)

    all_products = load_snapshot_products()
    sorted_skus = sorted(all_products.keys())
    selected_skus = select_skus(sorted_skus, args)

    category_map = load_category_map()
    category_parents = load_category_parents()
    base_context = build_base_context(client, dry_run)

    states: List[ProductImportState] = []
    for sku in selected_skus:
        product = all_products[sku]
        state = run_steps(
            client,
            registry,
            product,
            base_context,
            category_map,
            category_parents,
            sku,
        )
        states.append(state)

    label = args.batch if not args.skus else "custom"
    write_reports(states, label, dry_run)


if __name__ == "__main__":
    main()
