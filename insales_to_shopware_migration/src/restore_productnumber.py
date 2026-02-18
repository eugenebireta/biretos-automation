"""
Массовое восстановление productNumber у товаров в Shopware
через migration_map.json и snapshot InSales.

АЛГОРИТМ:
1. Загрузить migration_map.json (products)
2. Для каждого Shopware ID:
   - проверить, что товар существует
   - если productNumber уже есть → пропустить
   - получить InSales ID из migration_map
   - найти товар в products.ndjson
   - взять variants[0].sku
   - если sku пустой → использовать InSales product.id
3. PATCH /api/product/{id} с {"productNumber": "<sku_or_id>"}
"""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
MIGRATION_MAP_PATH = ROOT / "migration_map.json"
SNAPSHOT_PATH = ROOT / "insales_snapshot" / "products.ndjson"
CONFIG_PATH = ROOT / "config.json"
REPORT_PATH = ROOT / "reports" / "productnumber_restore_preview.md"

BATCH_SIZE = 50


def load_migration_map() -> Dict[str, str]:
    """Загружает маппинг products из migration_map.json"""
    if not MIGRATION_MAP_PATH.exists():
        print(f"ERROR: migration_map.json не найден: {MIGRATION_MAP_PATH}")
        return {}
    
    with MIGRATION_MAP_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    products_map = data.get("products", {})
    print(f"Загружено {len(products_map)} товаров из migration_map")
    return products_map


def build_insales_index() -> Dict[int, Dict[str, Any]]:
    """Строит индекс товаров из snapshot по InSales ID"""
    index = {}
    
    if not SNAPSHOT_PATH.exists():
        print(f"ERROR: Snapshot не найден: {SNAPSHOT_PATH}")
        return index
    
    print(f"Индексация товаров из {SNAPSHOT_PATH}...")
    with SNAPSHOT_PATH.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                product = json.loads(line)
                insales_id = product.get("id")
                if insales_id:
                    index[int(insales_id)] = product
            except json.JSONDecodeError:
                continue
    
    print(f"Проиндексировано {len(index)} товаров из snapshot")
    return index


def get_sku_from_insales_product(product: Dict[str, Any]) -> Optional[str]:
    """
    Извлекает SKU из товара InSales.
    
    Returns:
        SKU или InSales ID (если SKU пустой)
    """
    variants = product.get("variants", [])
    if not variants:
        # Если нет вариантов, используем ID товара
        return str(product.get("id", ""))
    
    variant = variants[0]
    sku = variant.get("sku")
    
    if sku:
        sku_str = str(sku).strip()
        if sku_str:
            return sku_str
    
    # Fallback: используем InSales ID
    return str(product.get("id", ""))


def check_product_exists(client: ShopwareClient, product_id: str) -> Tuple[bool, Optional[str]]:
    """
    Проверяет существование товара и возвращает текущий productNumber.
    
    Returns:
        (exists, current_productNumber)
    """
    try:
        response = client._request("GET", f"/api/product/{product_id}")
        product_data = response.get("data", {}) if isinstance(response, dict) else {}
        
        if product_data:
            product_number = product_data.get("productNumber")
            return True, product_number
        return False, None
    except Exception as e:
        # 404 или другая ошибка
        return False, None


def update_product_number(
    client: ShopwareClient,
    product_id: str,
    product_number: str,
    dry_run: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    Обновляет productNumber товара.
    
    Returns:
        (success, error_message)
    """
    if dry_run:
        return True, None
    
    try:
        payload = {"productNumber": product_number}
        client._request("PATCH", f"/api/product/{product_id}", json=payload)
        return True, None
    except Exception as e:
        return False, str(e)


def process_batch(
    client: ShopwareClient,
    batch: List[Tuple[str, str, str]],  # (shopware_id, insales_id, product_number)
    dry_run: bool = True
) -> Dict[str, Any]:
    """Обрабатывает batch товаров"""
    stats = {
        "updated": 0,
        "skipped": 0,
        "not_found": 0,
        "errors": 0,
        "error_details": []
    }
    
    for shopware_id, insales_id, product_number in batch:
        # Проверяем существование товара
        exists, current_product_number = check_product_exists(client, shopware_id)
        
        if not exists:
            stats["not_found"] += 1
            continue
        
        # Если productNumber уже есть, пропускаем
        if current_product_number:
            stats["skipped"] += 1
            continue
        
        # Обновляем productNumber
        success, error_msg = update_product_number(
            client, shopware_id, product_number, dry_run
        )
        
        if success:
            stats["updated"] += 1
        else:
            stats["errors"] += 1
            stats["error_details"].append({
                "shopware_id": shopware_id,
                "insales_id": insales_id,
                "error": error_msg or "Unknown error"
            })
    
    return stats


def generate_dry_run_report(
    products_to_update: List[Dict[str, Any]],
    total_products: int,
    skipped_count: int
) -> None:
    """Генерирует отчет для dry-run режима"""
    REPORT_PATH.parent.mkdir(exist_ok=True)
    
    report_lines = [
        "# Предпросмотр восстановления productNumber",
        "",
        "**Режим:** DRY-RUN (изменения не применены)",
        "",
        f"**Дата:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Статистика",
        "",
        f"- **Всего товаров в migration_map:** {total_products}",
        f"- **Товаров для обновления:** {len(products_to_update)}",
        f"- **Товаров с уже заполненным productNumber:** {skipped_count}",
        "",
        "## Товары для обновления",
        "",
        "| Shopware ID | InSales ID | Новый productNumber |",
        "|-------------|------------|---------------------|",
    ]
    
    # Показываем первые 100 товаров
    for item in products_to_update[:100]:
        report_lines.append(
            f"| {item['shopware_id']} | {item['insales_id']} | {item['product_number']} |"
        )
    
    if len(products_to_update) > 100:
        report_lines.append(f"\n*... и еще {len(products_to_update) - 100} товаров*")
    
    report_lines.extend([
        "",
        "## Структура обновления",
        "",
        "Для каждого товара будет выполнен PATCH запрос:",
        "",
        "```json",
        "{",
        '  "productNumber": "<sku_or_insales_id>"',
        "}",
        "```",
        "",
        "**ВАЖНО:**",
        "- Обновляется ТОЛЬКО поле `productNumber`",
        "- Остальные поля товара НЕ изменяются",
        "",
        "## Следующие шаги",
        "",
        "Для применения изменений запустите скрипт с флагом `--apply`:",
        "",
        "```bash",
        "python restore_productnumber.py --apply",
        "```",
        "",
        "После восстановления productNumber можно запустить:",
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
        description="Восстановление productNumber у товаров в Shopware"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Применить изменения (по умолчанию: dry-run)"
    )
    args = parser.parse_args()
    
    dry_run = not args.apply
    
    print("=" * 80)
    print("ВОССТАНОВЛЕНИЕ PRODUCTNUMBER В SHOPWARE")
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
    
    # Загружаем migration_map
    products_map = load_migration_map()
    if not products_map:
        print("ERROR: Не удалось загрузить migration_map")
        return 1
    
    # Строим индекс товаров из snapshot
    insales_index = build_insales_index()
    if not insales_index:
        print("ERROR: Не удалось загрузить snapshot")
        return 1
    
    # Альтернативный подход: получаем все товары из Shopware и ищем соответствие
    print()
    print("Получение товаров из Shopware...")
    
    # Получаем товары из Shopware постранично (максимум 500 за раз)
    shopware_product_ids = []
    page = 1
    limit = 500
    
    while True:
        try:
            shopware_response = client._request(
                "POST",
                "/api/search/product",
                json={
                    "limit": limit,
                    "page": page,
                    "includes": {"product": ["id", "productNumber"]}
                }
            )
            page_data = shopware_response.get("data", [])
            if not page_data:
                break
            shopware_product_ids.extend([p.get("id") for p in page_data if p.get("id")])
            print(f"  Получено страница {page}: {len(page_data)} товаров")
            
            # Проверяем, есть ли еще страницы
            total = shopware_response.get("total", 0)
            if len(shopware_product_ids) >= total or len(page_data) < limit:
                break
            page += 1
        except Exception as e:
            print(f"ERROR: Ошибка получения товаров (страница {page}): {e}")
            break
    
    print(f"Всего получено {len(shopware_product_ids)} товаров из Shopware")
    print("Загрузка полных данных товаров...")
    
    # Загружаем полные данные для каждого товара
    shopware_products = []
    for idx, product_id in enumerate(shopware_product_ids, 1):
        if idx % 100 == 0:
            print(f"  Загружено {idx}/{len(shopware_product_ids)}...")
        try:
            response = client._request("GET", f"/api/product/{product_id}")
            product_data = response.get("data", {}) if isinstance(response, dict) else {}
            if product_data:
                shopware_products.append(product_data)
        except Exception:
            continue
    
    print(f"Загружено полных данных: {len(shopware_products)} товаров")
    
    # Формируем список товаров для обновления
    print()
    print("Формирование списка товаров для обновления...")
    
    products_to_update = []
    skipped_count = 0
    not_found_count = 0
    no_snapshot_count = 0
    no_mapping_count = 0
    
    # Создаем обратный индекс migration_map
    reverse_map = {shopware_id: int(insales_id) for insales_id, shopware_id in products_map.items()}
    
    # Создаем индекс snapshot по названию для fallback
    snapshot_by_name = {}
    for insales_id, product in insales_index.items():
        title = product.get("title", "").strip()
        if title:
            # Нормализуем название (убираем лишние пробелы, приводим к нижнему регистру)
            normalized = " ".join(title.lower().split())
            if normalized:
                if normalized not in snapshot_by_name:
                    snapshot_by_name[normalized] = []
                snapshot_by_name[normalized].append(product)
    
    # Обрабатываем товары из Shopware
    for sw_product in shopware_products:
        shopware_id = sw_product.get("id")
        current_product_number = sw_product.get("productNumber")
        
        # Если productNumber уже есть, пропускаем
        if current_product_number:
            skipped_count += 1
            continue
        
        # Метод 1: Ищем в migration_map
        insales_id = reverse_map.get(shopware_id)
        insales_product = None
        
        if insales_id:
            # Находим товар в snapshot по ID
            insales_product = insales_index.get(insales_id)
        
        # Метод 2: Fallback - поиск по названию
        if not insales_product:
            sw_name = sw_product.get("name", {})
            if isinstance(sw_name, dict):
                sw_name = sw_name.get("ru-RU") or sw_name.get("en-GB") or str(sw_name)
            else:
                sw_name = str(sw_name)
            
            if sw_name and sw_name.strip():
                normalized_name = " ".join(sw_name.lower().strip().split())
                candidates = snapshot_by_name.get(normalized_name, [])
                if candidates:
                    # Берем первый кандидат
                    insales_product = candidates[0]
                    insales_id = insales_product.get("id")
        
        if not insales_product:
            no_snapshot_count += 1
            # Для первых 5 товаров выводим детали для диагностики
            if no_snapshot_count <= 5:
                sw_name = sw_product.get("name", {})
                if isinstance(sw_name, dict):
                    sw_name = sw_name.get("ru-RU") or sw_name.get("en-GB") or str(sw_name)
                else:
                    sw_name = str(sw_name)
                print(f"  DEBUG: Товар {shopware_id} не найден в snapshot")
                print(f"    Shopware название: {sw_name[:60] if sw_name else 'N/A'}...")
            continue
        
        # Извлекаем SKU
        product_number = get_sku_from_insales_product(insales_product)
        if not product_number:
            continue
        
        products_to_update.append({
            "shopware_id": shopware_id,
            "insales_id": str(insales_id) if insales_id else "unknown",
            "product_number": product_number
        })
    
    print(f"Найдено товаров для обновления: {len(products_to_update)}")
    print(f"Пропущено (productNumber уже есть): {skipped_count}")
    print(f"Не найдено в snapshot: {no_snapshot_count}")
    print()
    
    if not products_to_update:
        print("=" * 80)
        print("ПРОБЛЕМА: Товары не найдены для обновления")
        print("=" * 80)
        print()
        print("Возможные причины:")
        print("1. Товары из Shopware не соответствуют товарам из migration_map")
        print("2. Товары были переимпортированы с другими ID")
        print("3. Товары в Shopware не имеют названий для сопоставления")
        print()
        print("РЕКОМЕНДАЦИЯ:")
        print("Проверьте, были ли товары импортированы из InSales.")
        print("Если товары были импортированы, но с другими ID,")
        print("используйте другой метод сопоставления или выполните переимпорт.")
        print()
        return 0
    
    # В dry-run режиме генерируем отчет
    if dry_run:
        generate_dry_run_report(products_to_update, len(products_map), skipped_count)
        print()
        print("=" * 80)
        print("DRY-RUN ЗАВЕРШЕН")
        print("=" * 80)
        print(f"Найдено {len(products_to_update)} товаров для обновления")
        print(f"Отчет сохранен: {REPORT_PATH}")
        print("\nДля применения изменений запустите: python restore_productnumber.py --apply")
        return 0
    
    # Реальное применение изменений
    print(f"Начинаем обновление {len(products_to_update)} товаров...")
    print(f"Batch size: {BATCH_SIZE}")
    print()
    
    total_stats = {
        "updated": 0,
        "skipped": 0,
        "not_found": 0,
        "errors": 0,
        "error_details": []
    }
    
    # Обрабатываем batch'ами
    for batch_start in range(0, len(products_to_update), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(products_to_update))
        batch = [
            (item["shopware_id"], item["insales_id"], item["product_number"])
            for item in products_to_update[batch_start:batch_end]
        ]
        
        print(f"Обработка batch {batch_start // BATCH_SIZE + 1}: товары {batch_start + 1}-{batch_end}...")
        
        batch_stats = process_batch(client, batch, dry_run=False)
        
        # Суммируем статистику
        total_stats["updated"] += batch_stats["updated"]
        total_stats["skipped"] += batch_stats["skipped"]
        total_stats["not_found"] += batch_stats["not_found"]
        total_stats["errors"] += batch_stats["errors"]
        total_stats["error_details"].extend(batch_stats["error_details"])
        
        print(f"  OK: Обновлено: {batch_stats['updated']}, Пропущено: {batch_stats['skipped']}, "
              f"Не найдено: {batch_stats['not_found']}, Ошибки: {batch_stats['errors']}")
        
        # Небольшая задержка между batch'ами
        if batch_end < len(products_to_update):
            time.sleep(0.5)
    
    # Итоговая статистика
    print()
    print("=" * 80)
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 80)
    print(f"Всего товаров в migration_map: {len(products_map)}")
    print(f"OK: Обновлено: {total_stats['updated']}")
    print(f"SKIP: Пропущено (productNumber уже есть): {total_stats['skipped'] + skipped_count}")
    print(f"ERROR: Не найдено в Shopware: {total_stats['not_found']}")
    print(f"ERROR: Ошибки обновления: {total_stats['errors']}")
    
    if total_stats["error_details"]:
        print("\nДетали ошибок (первые 10):")
        for error in total_stats["error_details"][:10]:
            print(f"  - {error['shopware_id']}: {error['error']}")
        if len(total_stats["error_details"]) > 10:
            print(f"  ... и еще {len(total_stats['error_details']) - 10} ошибок")
    
    print("=" * 80)
    
    return 0 if total_stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

