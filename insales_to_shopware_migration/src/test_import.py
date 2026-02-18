from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Добавляем текущую директорию в sys.path для импорта модулей
sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig, ShopwareClientError
from import_utils import ROOT, build_payload, load_json, save_json


DEFAULT_CONFIG = ROOT / "config.json"
DEFAULT_MAP = ROOT / "migration_map.json"
DEFAULT_CSV = ROOT / "output" / "products_import.csv"


def parse_csv(path: Path, limit: int) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handler:
        reader = csv.DictReader(handler)
        for row in reader:
            rows.append(row)
            if len(rows) >= limit:
                break
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Импорт 5 тестовых товаров в Shopware.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--map", dest="map_path", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    config = load_json(args.config)
    mapping = load_json(
        args.map_path,
        default={"categories": {}, "properties": {}, "products": {}},
    )
    option_map = mapping.setdefault("property_options", {})

    rows = parse_csv(args.csv, args.limit)
    if not rows:
        print("CSV пуст, нечего импортировать.")
        return 1

    shop_cfg = ShopwareConfig(
        url=config["shopware"]["url"],
        access_key_id=config["shopware"]["access_key_id"],
        secret_access_key=config["shopware"]["secret_access_key"],
    )
    client = ShopwareClient(shop_cfg)

    # Получаем системную валюту для отладки
    system_currency_id = client.get_system_currency_id()
    print(f"DEBUG: System Currency ID: {system_currency_id}")
    
    payloads = [
        build_payload(row, shopware_client=client, option_map=option_map) for row in rows
    ]

    # Отладочный вывод первого payload
    if payloads:
        import json
        print("DEBUG: First payload price:")
        print(json.dumps(payloads[0].get('price', []), indent=2, ensure_ascii=False))

    # Используем прямой POST вместо Sync API
    created = 0
    updated = 0
    errors = []
    
    for payload in payloads:
        try:
            # Прямой POST запрос для создания продукта
            response = client._request("POST", "/api/product", json=payload)
            created += 1
            print(f"OK: Создан товар: {payload['productNumber']}")
        except ShopwareClientError as exc:
            error_msg = f"Ошибка для товара {payload['productNumber']}: {exc}"
            print(f"ERROR: {error_msg}")
            errors.append(error_msg)
            # Не прерываем выполнение, продолжаем с другими товарами
    
    if errors and created == 0:
        # Если все товары не удалось создать, выбрасываем ошибку
        raise RuntimeError(f"Не удалось создать ни одного товара. Ошибки: {'; '.join(errors)}")
    
    if errors:
        print(f"\nПредупреждение: {len(errors)} товаров не удалось создать из {len(payloads)}")
    save_json(args.map_path, mapping)

    message = (
        f"Импортированы товары: {[row['productNumber'] for row in rows]} "
        f"(создано: {created}, обновлено: {updated})"
    )
    print(message)
    result_path = ROOT.parent / "_scratchpad" / "test_import_result.json"
    result_path.write_text(
        json.dumps({"created": created, "updated": updated, "products": [row["productNumber"] for row in rows]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

