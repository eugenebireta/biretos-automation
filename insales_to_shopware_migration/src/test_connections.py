from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

from clients import (
    InsalesClient,
    InsalesClientError,
    InsalesConfig,
    ShopwareClient,
    ShopwareClientError,
    ShopwareConfig,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open("r", encoding="utf-8") as handler:
        return json.load(handler)


def check_insales(cfg: Dict[str, Any]) -> Tuple[bool, str]:
    insales_cfg = InsalesConfig(
        host=cfg["insales"]["host"],
        api_key=cfg["insales"]["api_key"],
        api_password=cfg["insales"]["api_password"],
    )
    client = InsalesClient(insales_cfg)
    try:
        count = client.get_products_count()
        return True, f"Products: {count if count is not None else 'unknown'}"
    except InsalesClientError as exc:
        return False, str(exc)


def check_shopware(cfg: Dict[str, Any]) -> Tuple[bool, str]:
    shopware_cfg = ShopwareConfig(
        url=cfg["shopware"]["url"],
        access_key_id=cfg["shopware"]["access_key_id"],
        secret_access_key=cfg["shopware"]["secret_access_key"],
    )
    client = ShopwareClient(shopware_cfg)
    try:
        data = client.list_products(limit=1)
        total = data.get("total") if isinstance(data, dict) else "unknown"
        return True, f"Products: {total}"
    except ShopwareClientError as exc:
        return False, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка подключений к Insales и Shopware.")
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help="Путь к config.json (по умолчанию insales_to_shopware_migration/config.json)",
    )
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
    except FileNotFoundError as err:
        print(f"[ERROR] {err}")
        return 1

    insales_ok, insales_msg = check_insales(cfg)
    shopware_ok, shopware_msg = check_shopware(cfg)

    print("=== Connectivity ===")
    print(f"Insales:  {'OK' if insales_ok else 'FAIL'} — {insales_msg}")
    print(f"Shopware: {'OK' if shopware_ok else 'FAIL'} — {shopware_msg}")

    return 0 if insales_ok and shopware_ok else 2


if __name__ == "__main__":
    sys.exit(main())











