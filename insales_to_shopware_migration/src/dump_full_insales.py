from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from clients import InsalesClient, InsalesConfig


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
BACKUP_ROOT = ROOT / "backup_insales"


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handler:
        return json.load(handler)


def ensure_output_folder(base_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target = base_dir / timestamp
    target.mkdir(parents=True, exist_ok=True)
    return target


def save_json(target_dir: Path, name: str, data: Any) -> None:
    filepath = target_dir / f"{name}.json"
    with filepath.open("w", encoding="utf-8") as handler:
        json.dump(data, handler, ensure_ascii=False, indent=2)
    count = len(data) if isinstance(data, list) else 1
    print(f"[OK] saved {name}: {count} records -> {filepath}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Полный бэкап данных Insales.")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--output", type=Path, default=BACKUP_ROOT)
    parser.add_argument("--per-page", type=int, default=250)
    args = parser.parse_args()

    config = load_config(args.config)
    output_dir = ensure_output_folder(args.output)
    print(f"=== Backup folder: {output_dir} ===")

    insales_cfg = InsalesConfig(
        host=config["insales"]["host"],
        api_key=config["insales"]["api_key"],
        api_password=config["insales"]["api_password"],
    )
    client = InsalesClient(insales_cfg)

    endpoints: Dict[str, str] = {
        "products": "/products",
        "collections": "/collections",
        "properties": "/properties",
        "option_names": "/option_names",
        "clients": "/clients",
        "orders": "/orders",
        "pages": "/pages",
        "blogs": "/blogs",
        "price_kinds": "/price_kinds",
        "domains": "/domains",
        "payment_gateways": "/payment_gateways",
        "delivery_variants": "/delivery_variants",
        "discounts": "/discounts",
    }

    backups: Dict[str, Any] = {}
    for name, endpoint in endpoints.items():
        print(f"Downloading {name}...")
        data = client.fetch_all(endpoint, per_page=args.per_page)
        backups[name] = data
        save_json(output_dir, name, data)

    # отдельная выгрузка статей блогов
    blogs: List[Dict[str, Any]] = backups.get("blogs") or []
    all_articles: List[Dict[str, Any]] = []
    if blogs:
        print("Downloading blog articles...")
        for blog in blogs:
            blog_id = blog.get("id")
            if not blog_id:
                continue
            title = blog.get("title", "")
            print(f"  Blog {blog_id} {title}:")
            articles = client.fetch_all(f"/blogs/{blog_id}/articles", per_page=args.per_page)
            all_articles.extend(articles)
        save_json(output_dir, "articles", all_articles)

    print("\n=== Backup completed successfully ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())











