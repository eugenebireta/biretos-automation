"""
Восстановление Marketplace цен (price2 из InSales) в Shopware 6
через rule-based pricing (product.prices).

ВАЖНО:
- Обновляет ТОЛЬКО поле product.prices
- НЕ трогает product.price (базовая цена)
- Валидирует, что базовая цена не изменилась
"""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = ROOT / "insales_snapshot" / "products.ndjson"
CONFIG_PATH = ROOT / "config.json"
REPORT_PATH = ROOT / "reports" / "marketplace_prices_restore_preview.md"

# Константы
MARKETPLACE_RULE_NAME = "Marketplace Price"
BATCH_SIZE = 50


def load_insales_products() -> List[Dict[str, Any]]:
    """Загружает товары из snapshot InSales"""
    products = []
    if not SNAPSHOT_PATH.exists():
        print(f"ERROR: Snapshot не найден: {SNAPSHOT_PATH}")
        return products
    
    print(f"Загрузка товаров из {SNAPSHOT_PATH}...")
    with SNAPSHOT_PATH.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                product = json.loads(line)
                products.append(product)
            except json.JSONDecodeError as e:
                print(f"WARNING: Ошибка парсинга строки {line_num}: {e}")
                continue
    
    print(f"Загружено {len(products)} товаров из snapshot InSales")
    return products


def extract_price2_products(products: List[Dict[str, Any]]) -> List[Tuple[str, float, str]]:
    """
    Извлекает товары с price2 (Marketplace цена).
    
    Returns:
        Список кортежей: (product_number, price2, product_name)
    """
    result = []
    for product in products:
        variants = product.get("variants", [])
        if not variants:
            continue
        
        variant = variants[0]
        product_number = variant.get("sku")
        price2 = variant.get("price2")
        product_name = product.get("title", "Unknown")
        
        # Работаем ТОЛЬКО с товарами, где price2 != null
        if product_number and price2 is not None:
            try:
                price2_float = float(price2)
                if price2_float > 0:
                    result.append((product_number, price2_float, product_name))
            except (ValueError, TypeError):
                continue
    
    print(f"Найдено {len(result)} товаров с price2 (Marketplace цена)")
    return result


def get_or_create_price_rule(client: ShopwareClient, dry_run: bool = True) -> Optional[str]:
    """
    Получает существующее Price Rule или создает новое.
    
    Args:
        client: ShopwareClient
        dry_run: Если True, только проверяет существование, не создает
        
    Returns:
        ruleId или None
    """
    # Проверяем существование
    existing_rule_id = client.find_price_rule_by_name(MARKETPLACE_RULE_NAME)
    if existing_rule_id:
        print(f"OK: Найдено существующее Price Rule '{MARKETPLACE_RULE_NAME}': {existing_rule_id}")
        return existing_rule_id
    
    if dry_run:
        print(f"WARNING: В dry-run режиме: Price Rule '{MARKETPLACE_RULE_NAME}' будет создан при --apply")
        return None
    
    # Создаем новое правило
    print(f"Создание Price Rule '{MARKETPLACE_RULE_NAME}'...")
    try:
        rule_id = client.create_price_rule(
            name=MARKETPLACE_RULE_NAME,
            description="Price rule for Marketplace channel (from InSales price2)",
            priority=100
        )
        print(f"OK: Создано Price Rule '{MARKETPLACE_RULE_NAME}': {rule_id}")
        return rule_id
    except Exception as e:
        print(f"ERROR: Не удалось создать Price Rule: {e}")
        return None


def get_base_price(client: ShopwareClient, product_id: str) -> Optional[float]:
    """
    Получает базовую цену товара (product.price[0].gross).
    
    Args:
        client: ShopwareClient
        product_id: ID товара
        
    Returns:
        Базовая цена или None
    """
    try:
        response = client._request("GET", f"/api/product/{product_id}")
        product_data = response.get("data", {}) if isinstance(response, dict) else {}
        base_prices = product_data.get("price", [])
        if base_prices and len(base_prices) > 0:
            return float(base_prices[0].get("gross", 0))
    except Exception as e:
        print(f"WARNING: Ошибка получения базовой цены для товара {product_id}: {e}")
    return None


def validate_base_price_unchanged(
    client: ShopwareClient,
    product_id: str,
    original_base_price: float
) -> bool:
    """
    Валидирует, что базовая цена не изменилась после обновления.
    
    Args:
        client: ShopwareClient
        product_id: ID товара
        original_base_price: Исходная базовая цена
        
    Returns:
        True если цена не изменилась, False иначе
    """
    time.sleep(0.2)  # Небольшая задержка для применения изменений
    current_base_price = get_base_price(client, product_id)
    
    if current_base_price is None:
        print(f"WARNING: Не удалось получить базовую цену для валидации (product_id: {product_id})")
        return False
    
    if abs(current_base_price - original_base_price) > 0.01:  # Допуск для float
        print(f"ERROR: Базовая цена изменилась! Было: {original_base_price}, Стало: {current_base_price}")
        return False
    
    return True


def update_product_prices(
    client: ShopwareClient,
    product_id: str,
    price2: float,
    rule_id: str,
    currency_id: str,
    dry_run: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    Обновляет product.prices для товара (Marketplace цена).
    
    Args:
        client: ShopwareClient
        product_id: ID товара
        price2: Marketplace цена из InSales
        rule_id: ID Price Rule
        currency_id: ID валюты
        dry_run: Если True, только симулирует обновление
        
    Returns:
        (success, error_message)
    """
    # Получаем текущую базовую цену для валидации
    original_base_price = get_base_price(client, product_id)
    if original_base_price is None:
        return False, "Не удалось получить базовую цену"
    
    # Формируем payload ТОЛЬКО с полем prices
    payload = {
        "prices": [
            {
                "ruleId": rule_id,
                "price": [
                    {
                        "currencyId": currency_id,
                        "gross": float(price2),
                        "net": float(price2),
                        "linked": False
                    }
                ]
            }
        ]
    }
    
    if dry_run:
        # В dry-run режиме только проверяем структуру
        return True, None
    
    try:
        # ВАЖНО: PATCH только поле prices, НЕ price
        client._request("PATCH", f"/api/product/{product_id}", json=payload)
        
        # Валидация: проверяем, что базовая цена не изменилась
        if not validate_base_price_unchanged(client, product_id, original_base_price):
            return False, "Базовая цена изменилась после обновления"
        
        return True, None
    except Exception as e:
        return False, str(e)


def process_batch(
    client: ShopwareClient,
    batch: List[Tuple[str, float, str]],
    rule_id: Optional[str],
    currency_id: str,
    dry_run: bool = True
) -> Dict[str, Any]:
    """
    Обрабатывает batch товаров.
    
    Returns:
        Статистика обработки
    """
    stats = {
        "success": 0,
        "not_found": 0,
        "errors": 0,
        "error_details": []
    }
    
    for product_number, price2, product_name in batch:
        # Находим товар в Shopware через улучшенный метод с валидацией productNumber
        product_id = client.find_product_by_number(product_number)
        if not product_id:
            stats["not_found"] += 1
            stats["error_details"].append({
                "product_number": product_number,
                "product_name": product_name,
                "error": "Товар не найден в Shopware по productNumber"
            })
            continue
        
        # Обновляем цены
        if rule_id:
            success, error_msg = update_product_prices(
                client, product_id, price2, rule_id, currency_id, dry_run
            )
            if success:
                stats["success"] += 1
            else:
                stats["errors"] += 1
                stats["error_details"].append({
                    "product_number": product_number,
                    "product_name": product_name,
                    "error": error_msg or "Unknown error"
                })
        else:
            # В dry-run режиме без rule_id просто считаем как success
            stats["success"] += 1
    
    return stats


def generate_dry_run_report(
    products: List[Tuple[str, float, str]],
    rule_id: Optional[str],
    currency_id: str,
    total_products: int
) -> None:
    """Генерирует отчет для dry-run режима"""
    REPORT_PATH.parent.mkdir(exist_ok=True)
    
    report_lines = [
        "# Предпросмотр восстановления Marketplace цен",
        "",
        "**Режим:** DRY-RUN (изменения не применены)",
        "",
        f"**Дата:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Параметры",
        "",
        f"- **Price Rule:** {MARKETPLACE_RULE_NAME}",
        f"- **Rule ID:** {rule_id or 'Будет создан при --apply'}",
        f"- **Currency ID:** {currency_id}",
        f"- **Всего товаров с price2:** {total_products}",
        "",
        "## Товары для обновления",
        "",
        "| Product Number | Название | Marketplace цена (price2) |",
        "|----------------|----------|---------------------------|",
    ]
    
    # Показываем первые 100 товаров
    for product_number, price2, product_name in products[:100]:
        report_lines.append(
            f"| {product_number} | {product_name[:50]} | {price2:.2f} |"
        )
    
    if len(products) > 100:
        report_lines.append(f"\n*... и еще {len(products) - 100} товаров*")
    
    report_lines.extend([
        "",
        "## Структура обновления",
        "",
        "Для каждого товара будет выполнен PATCH запрос:",
        "",
        "```json",
        "{",
        '  "prices": [',
        "    {",
        f'      "ruleId": "{rule_id or "<rule_id>"}",',
        '      "price": [',
        "        {",
        f'          "currencyId": "{currency_id}",',
        '          "gross": <price2>,',
        '          "net": <price2>,',
        '          "linked": false',
        "        }",
        "      ]",
        "    }",
        "  ]",
        "}",
        "```",
        "",
        "**ВАЖНО:**",
        "- Обновляется ТОЛЬКО поле `prices`",
        "- Поле `price` (базовая цена) НЕ изменяется",
        "- После обновления выполняется валидация базовой цены",
        "",
        "## Следующие шаги",
        "",
        "Для применения изменений запустите скрипт с флагом `--apply`:",
        "",
        "```bash",
        "python restore_marketplace_prices.py --apply",
        "```",
        "",
        "---",
        "",
        "*Отчет сгенерирован автоматически в dry-run режиме.*",
    ])
    
    report_content = "\n".join(report_lines)
    REPORT_PATH.write_text(report_content, encoding="utf-8")
    print(f"OK: Отчет сохранен: {REPORT_PATH}")


def main():
    parser = argparse.ArgumentParser(
        description="Восстановление Marketplace цен (price2) в Shopware 6"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Применить изменения (по умолчанию: dry-run)"
    )
    args = parser.parse_args()
    
    dry_run = not args.apply
    
    print("=" * 80)
    print("ВОССТАНОВЛЕНИЕ MARKETPLACE ЦЕН В SHOPWARE 6")
    print("=" * 80)
    print(f"Режим: {'DRY-RUN' if dry_run else 'APPLY'}")
    print()
    
    # Загружаем конфигурацию
    if not CONFIG_PATH.exists():
        print(f"ERROR: Конфигурация не найдена: {CONFIG_PATH}")
        return 1
    
    with CONFIG_PATH.open() as f:
        config = json.load(f)
    
    sw_config = config["shopware"]
    client = ShopwareClient(
        ShopwareConfig(
            sw_config["url"],
            sw_config["access_key_id"],
            sw_config["secret_access_key"]
        )
    )
    
    # Загружаем товары из snapshot
    insales_products = load_insales_products()
    if not insales_products:
        print("ERROR: Не удалось загрузить товары из snapshot")
        return 1
    
    # Извлекаем товары с price2
    price2_products = extract_price2_products(insales_products)
    if not price2_products:
        print("INFO: Не найдено товаров с price2 для восстановления")
        return 0
    
    # Получаем или создаем Price Rule
    rule_id = get_or_create_price_rule(client, dry_run=dry_run)
    if not rule_id and not dry_run:
        print("ERROR: Не удалось получить или создать Price Rule")
        return 1
    
    # Получаем валюту
    currency_id = client.get_sales_channel_currency_id()
    if not currency_id:
        currency_id = client.get_currency_id("RUB")
    if not currency_id:
        print("ERROR: Не удалось определить валюту")
        return 1
    
    print(f"OK: Используется валюта: {currency_id}")
    print()
    
    # В dry-run режиме генерируем отчет
    if dry_run:
        generate_dry_run_report(price2_products, rule_id, currency_id, len(price2_products))
        print("\n" + "=" * 80)
        print("DRY-RUN ЗАВЕРШЕН")
        print("=" * 80)
        print(f"Найдено {len(price2_products)} товаров для обновления")
        print(f"Отчет сохранен: {REPORT_PATH}")
        print("\nДля применения изменений запустите: python restore_marketplace_prices.py --apply")
        return 0
    
    # Реальное применение изменений
    print(f"Начинаем обновление {len(price2_products)} товаров...")
    print(f"Batch size: {BATCH_SIZE}")
    print()
    
    total_stats = {
        "success": 0,
        "not_found": 0,
        "errors": 0,
        "error_details": []
    }
    
    # Обрабатываем batch'ами
    for batch_start in range(0, len(price2_products), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(price2_products))
        batch = price2_products[batch_start:batch_end]
        
        print(f"Обработка batch {batch_start // BATCH_SIZE + 1}: товары {batch_start + 1}-{batch_end}...")
        
        batch_stats = process_batch(
            client, batch, rule_id, currency_id, dry_run=False
        )
        
        # Суммируем статистику
        total_stats["success"] += batch_stats["success"]
        total_stats["not_found"] += batch_stats["not_found"]
        total_stats["errors"] += batch_stats["errors"]
        total_stats["error_details"].extend(batch_stats["error_details"])
        
        print(f"  OK: Успешно: {batch_stats['success']}, Не найдено: {batch_stats['not_found']}, Ошибки: {batch_stats['errors']}")
        
        # Небольшая задержка между batch'ами
        if batch_end < len(price2_products):
            time.sleep(0.5)
    
    # Итоговая статистика
    print()
    print("=" * 80)
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 80)
    print(f"Всего товаров: {len(price2_products)}")
    print(f"OK: Успешно обновлено: {total_stats['success']}")
    print(f"WARNING: Не найдено в Shopware: {total_stats['not_found']}")
    print(f"ERROR: Ошибки: {total_stats['errors']}")
    
    if total_stats["error_details"]:
        print("\nДетали ошибок (первые 10):")
        for error in total_stats["error_details"][:10]:
            print(f"  - {error['product_number']}: {error['error']}")
        if len(total_stats["error_details"]) > 10:
            print(f"  ... и еще {len(total_stats['error_details']) - 10} ошибок")
    
    print("=" * 80)
    
    return 0 if total_stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

