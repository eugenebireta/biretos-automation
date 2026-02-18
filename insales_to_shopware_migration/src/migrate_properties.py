from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from clients import ShopwareClient, ShopwareConfig


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
STRUCTURE_PATH = ROOT / "logs" / "insales_structure.json"
MAP_PATH = ROOT / "migration_map.json"


def load_json(path: Path, *, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as handler:
        return json.load(handler)


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handler:
        json.dump(payload, handler, ensure_ascii=False, indent=2)


def build_shopware_client(cfg: Dict[str, Any]) -> ShopwareClient:
    shopware_cfg = ShopwareConfig(
        url=cfg["shopware"]["url"],
        access_key_id=cfg["shopware"]["access_key_id"],
        secret_access_key=cfg["shopware"]["secret_access_key"],
    )
    return ShopwareClient(shopware_cfg)


def migrate_properties(
    config: Dict[str, Any],
    structure: Dict[str, Any],
    mapping: Dict[str, Any],
) -> Dict[str, Any]:
    shopware_client = build_shopware_client(config)

    option_names = structure.get("option_names", [])
    properties = structure.get("properties", [])

    prop_mapping: Dict[str, str] = mapping.setdefault("properties", {})

    created_groups = 0
    reused_groups = 0

    def ensure_property_group(key: str, name: str) -> str:
        nonlocal created_groups, reused_groups
        if not name:
            name = f"Property {key}"
        if key in prop_mapping:
            return prop_mapping[key]

        existing_id = shopware_client.find_property_group_by_name(name)
        if existing_id:
            prop_mapping[key] = existing_id
            reused_groups += 1
            print(f"[SKIP] Property group '{name}' already exists -> {existing_id}")
            return existing_id

        new_id = uuid4().hex
        payload = {
            "id": new_id,
            "name": name,
            "filterable": True,
            "displayType": "text",
            "sortingType": "alphanumeric",
            "translations": {
                "ru-RU": {
                    "name": name,
                }
            },
        }
        shopware_client.create_property_group(payload)
        prop_mapping[key] = new_id
        created_groups += 1
        print(f"[OK] Property group '{name}' -> {new_id}")
        return new_id

    print("--- Migrating option names ---")
    for option in option_names:
        ensure_property_group(f"opt_{option['id']}", option.get("title") or option.get("permalink") or "")

    print("--- Migrating properties ---")
    for prop in properties:
        ensure_property_group(f"prop_{prop['id']}", prop.get("title") or prop.get("permalink") or "")

    mapping["last_updated"] = datetime.now(timezone.utc).isoformat()
    print(
        f"Property groups processed: {len(option_names) + len(properties)}. "
        f"Created: {created_groups}, reused: {reused_groups}."
    )
    return mapping


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Миграция свойств Insales -> Shopware.")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--structure", type=Path, default=STRUCTURE_PATH)
    parser.add_argument("--map", type=Path, default=MAP_PATH)
    args = parser.parse_args()

    config = load_json(args.config)
    structure = load_json(args.structure)
    mapping = load_json(
        args.map,
        default={"categories": {}, "properties": {}, "products": {}, "last_updated": None},
    )

    updated = migrate_properties(config, structure, mapping)
    save_json(args.map, updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())











