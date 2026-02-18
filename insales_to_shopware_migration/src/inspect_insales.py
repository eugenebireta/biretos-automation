from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from clients import InsalesClient, InsalesConfig


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
LOGS_DIR = ROOT / "logs"
OUTPUT_PATH = LOGS_DIR / "insales_structure.json"


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open("r", encoding="utf-8") as handler:
        return json.load(handler)


def fetch_all_collections(client: InsalesClient) -> List[Dict[str, Any]]:
    collections: List[Dict[str, Any]] = []
    page = 1
    per_page = 250
    while True:
        chunk = client.get_collections(page=page, per_page=per_page)
        if not chunk:
            break
        collections.extend(chunk)
        if len(chunk) < per_page:
            break
        page += 1
    return collections


def run_inspection(config: Dict[str, Any], sample_size: int) -> Dict[str, Any]:
    insales_cfg = InsalesConfig(
        host=config["insales"]["host"],
        api_key=config["insales"]["api_key"],
        api_password=config["insales"]["api_password"],
    )
    client = InsalesClient(insales_cfg)
    collections = fetch_all_collections(client)
    option_names = client.get_option_names()
    properties = client.get_properties()
    sample_products = client.get_products(per_page=sample_size)

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "counts": {
            "collections": len(collections),
            "option_names": len(option_names),
            "properties": len(properties),
            "sample_products": len(sample_products),
        },
        "collections": collections,
        "option_names": option_names,
        "properties": properties,
        "sample_products": sample_products,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Инспекция структуры данных Insales.")
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help="Путь к config.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="Путь для сохранения структуры (JSON)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=10,
        help="Количество товаров для выборки",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    result = run_inspection(cfg, args.sample_size)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handler:
        json.dump(result, handler, ensure_ascii=False, indent=2)

    counts = result["counts"]
    print("=== Insales Snapshot ===")
    print(f"Collections: {counts['collections']}")
    print(f"Option Names: {counts['option_names']}")
    print(f"Properties: {counts['properties']}")
    print(f"Sample products: {counts['sample_products']}")
    print(f"Saved to: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())











