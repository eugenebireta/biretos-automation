"""
Очистка Shopware 6 для тестового импорта.

Выполняет:
1. Удаление всех товаров (products)
2. Удаление всех Marketplace Price rules, кроме канонической
3. Удаление всех manufacturers с product_count = 0
4. Удаление всех media, связанных с товарами

Ограничения:
- НЕ трогать категории
- НЕ трогать sales channels
- НЕ трогать taxes
- НЕ трогать rules, если они используются
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from import_utils import ROOT, load_json

REPORTS_DIR = ROOT / "_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def delete_all_products(client: ShopwareClient, dry_run: bool = True) -> Dict[str, Any]:
    """Удаляет все товары из Shopware."""
    print("=" * 80)
    print("ШАГ 1: УДАЛЕНИЕ ВСЕХ ТОВАРОВ")
    print("=" * 80)
    print()
    
    products_deleted = 0
    products_errors = 0
    
    # Получаем все товары
    print("1) Поиск всех товаров...")
    all_products = []
    page = 1
    limit = 500
    
    while True:
        try:
            response = client._request(
                "POST",
                "/api/search/product",
                json={
                    "limit": limit,
                    "page": page,
                    "includes": {"product": ["id"]},
                }
            )
            
            if isinstance(response, dict) and "data" in response:
                data = response.get("data", [])
                if data:
                    all_products.extend(data)
                    if len(data) < limit:
                        break
                    page += 1
                else:
                    break
            else:
                break
        except Exception as e:
            print(f"   [ERROR] Ошибка получения товаров: {e}")
            break
    
    total_products = len(all_products)
    print(f"   [OK] Найдено товаров: {total_products}")
    
    if total_products == 0:
        print("   [SKIP] Товары не найдены")
        return {"deleted": 0, "errors": 0}
    
    # Удаляем товары
    print("2) Удаление товаров...")
    for idx, product in enumerate(all_products, 1):
        if idx % 100 == 0:
            print(f"   [{idx}/{total_products}] Удалено товаров: {products_deleted}...")
        
        product_id = product.get("id")
        if not product_id:
            continue
        
        if not dry_run:
            try:
                client._request("DELETE", f"/api/product/{product_id}")
                products_deleted += 1
            except Exception as e:
                print(f"      [ERROR] Ошибка удаления товара {product_id}: {e}")
                products_errors += 1
        else:
            products_deleted += 1
    
    print(f"   [OK] Удалено товаров: {products_deleted}")
    if products_errors > 0:
        print(f"   [ERROR] Ошибок: {products_errors}")
    print()
    
    return {"deleted": products_deleted, "errors": products_errors}


def delete_marketplace_rules(client: ShopwareClient, dry_run: bool = True) -> Dict[str, Any]:
    """Удаляет все Marketplace Price rules, кроме канонической."""
    print("=" * 80)
    print("ШАГ 2: УДАЛЕНИЕ MARKETPLACE PRICE RULES")
    print("=" * 80)
    print()
    
    print("1) Поиск всех Marketplace Price rules...")
    
    normalized_target = client._normalize_name("Marketplace Price")
    
    try:
        response = client._request(
            "POST",
            "/api/search/rule",
            json={
                "filter": [
                    {"field": "name", "type": "contains", "value": "Marketplace Price"}
                ],
                "limit": 500,
            }
        )
        
        rules = []
        rule_ids_found = []
        if isinstance(response, dict) and "data" in response:
            for item in response.get("data", []):
                rule_id = item.get("id")
                attrs = item.get("attributes", {})
                name = attrs.get("name") or item.get("name", "")
                
                if client._normalize_name(name) == normalized_target:
                    rule_ids_found.append(rule_id)
                    rules.append({
                        "ruleId": rule_id,
                        "name": name,
                        "price_count": 0,
                    })
        
        # Подсчитываем использование каждого правила
        print("   Подсчёт использования правил...", end=" ", flush=True)
        try:
            all_prices_response = client._request(
                "POST",
                "/api/search/product-price",
                json={
                    "filter": [
                        {"field": "ruleId", "type": "equalsAny", "value": rule_ids_found}
                    ],
                    "limit": 500,
                }
            )
            
            rule_usage = {}
            if isinstance(all_prices_response, dict) and "data" in all_prices_response:
                for price_item in all_prices_response.get("data", []):
                    price_attrs = price_item.get("attributes", {})
                    rule_id = price_attrs.get("ruleId") or price_item.get("ruleId")
                    if rule_id in rule_ids_found:
                        if rule_id not in rule_usage:
                            rule_usage[rule_id] = 0
                        rule_usage[rule_id] += 1
            
            for rule in rules:
                rule_id = rule["ruleId"]
                rule["price_count"] = rule_usage.get(rule_id, 0)
            
            print(f"[OK]")
        except Exception as e:
            print(f"[WARNING: {str(e)[:30]}]")
        
        if not rules:
            print("   [SKIP] Rules не найдены")
            return {"deleted": 0, "skipped": 0}
        
        # Сортируем по price_count DESC - канонический будет первым
        rules.sort(key=lambda x: x["price_count"], reverse=True)
        
        canonical_rule_id = rules[0]["ruleId"] if rules else None
        print(f"   [OK] Найдено rules: {len(rules)}")
        if canonical_rule_id:
            print(f"   [OK] Канонический rule: {canonical_rule_id} (product-price: {rules[0]['price_count']})")
        
        # Удаляем все остальные rules
        print("2) Удаление неиспользуемых rules...")
        rules_deleted = 0
        rules_skipped = 0
        
        for rule in rules:
            rule_id = rule["ruleId"]
            price_count = rule["price_count"]
            
            # Пропускаем канонический rule
            if rule_id == canonical_rule_id:
                rules_skipped += 1
                print(f"   [SKIP] Канонический rule: {rule_id}")
                continue
            
            # Пропускаем используемые rules
            if price_count > 0:
                rules_skipped += 1
                print(f"   [SKIP] Rule {rule_id} используется ({price_count} product-price)")
                continue
            
            # Удаляем неиспользуемые rules
            if not dry_run:
                try:
                    client._request("DELETE", f"/api/rule/{rule_id}")
                    rules_deleted += 1
                    print(f"   [OK] Удалён rule: {rule_id}")
                except Exception as e:
                    print(f"   [ERROR] Ошибка удаления rule {rule_id}: {e}")
            else:
                rules_deleted += 1
                print(f"   [DRY-RUN] Будет удалён rule: {rule_id}")
        
        print(f"   [OK] Удалено rules: {rules_deleted}")
        print(f"   [OK] Пропущено rules: {rules_skipped}")
        print()
        
        return {"deleted": rules_deleted, "skipped": rules_skipped}
        
    except Exception as e:
        print(f"   [ERROR] Ошибка поиска rules: {e}")
        return {"deleted": 0, "skipped": 0}


def delete_unused_manufacturers(client: ShopwareClient, dry_run: bool = True) -> Dict[str, Any]:
    """Удаляет всех manufacturers с product_count = 0."""
    print("=" * 80)
    print("ШАГ 3: УДАЛЕНИЕ НЕИСПОЛЬЗУЕМЫХ MANUFACTURERS")
    print("=" * 80)
    print()
    
    print("1) Поиск всех manufacturers...")
    
    try:
        response = client._request(
            "POST",
            "/api/search/product-manufacturer",
            json={
                "limit": 500,
            }
        )
        
        manufacturers = []
        if isinstance(response, dict) and "data" in response:
            for item in response.get("data", []):
                manufacturer_id = item.get("id")
                attrs = item.get("attributes", {})
                name = attrs.get("name") or item.get("name", "")
                
                # Подсчитываем количество товаров
                product_count = 0
                try:
                    product_search = client._request(
                        "POST",
                        "/api/search/product",
                        json={
                            "filter": [
                                {"field": "manufacturerId", "type": "equals", "value": manufacturer_id}
                            ],
                            "limit": 1,
                            "totalCountMode": 1,
                        }
                    )
                    if isinstance(product_search, dict):
                        product_count = product_search.get("total", 0)
                except Exception:
                    pass
                
                manufacturers.append({
                    "id": manufacturer_id,
                    "name": name,
                    "product_count": product_count
                })
        
        if not manufacturers:
            print("   [SKIP] Manufacturers не найдены")
            return {"deleted": 0, "skipped": 0}
        
        print(f"   [OK] Найдено manufacturers: {len(manufacturers)}")
        
        # Удаляем manufacturers с product_count = 0
        print("2) Удаление неиспользуемых manufacturers...")
        manufacturers_deleted = 0
        manufacturers_skipped = 0
        
        for manufacturer in manufacturers:
            mfr_id = manufacturer["id"]
            product_count = manufacturer["product_count"]
            name = manufacturer["name"]
            
            if product_count > 0:
                manufacturers_skipped += 1
                continue
            
            if not dry_run:
                try:
                    client._request("DELETE", f"/api/product-manufacturer/{mfr_id}")
                    manufacturers_deleted += 1
                    print(f"   [OK] Удалён manufacturer: {mfr_id} ({name})")
                except Exception as e:
                    print(f"   [ERROR] Ошибка удаления manufacturer {mfr_id}: {e}")
            else:
                manufacturers_deleted += 1
        
        print(f"   [OK] Удалено manufacturers: {manufacturers_deleted}")
        print(f"   [OK] Пропущено manufacturers: {manufacturers_skipped}")
        print()
        
        return {"deleted": manufacturers_deleted, "skipped": manufacturers_skipped}
        
    except Exception as e:
        print(f"   [ERROR] Ошибка поиска manufacturers: {e}")
        return {"deleted": 0, "skipped": 0}


def delete_product_media(client: ShopwareClient, dry_run: bool = True) -> Dict[str, Any]:
    """Удаляет все media, связанные с товарами."""
    print("=" * 80)
    print("ШАГ 4: УДАЛЕНИЕ PRODUCT MEDIA")
    print("=" * 80)
    print()
    
    print("1) Поиск всех product media...")
    
    media_deleted = 0
    media_errors = 0
    
    try:
        # Получаем все product media
        response = client._request(
            "POST",
            "/api/search/product-media",
            json={
                "limit": 500,
            }
        )
        
        all_media = []
        if isinstance(response, dict) and "data" in response:
            all_media = response.get("data", [])
        
        total_media = len(all_media)
        print(f"   [OK] Найдено product media: {total_media}")
        
        if total_media == 0:
            print("   [SKIP] Product media не найдены")
            return {"deleted": 0, "errors": 0}
        
        # Удаляем media
        print("2) Удаление product media...")
        for idx, media_item in enumerate(all_media, 1):
            if idx % 100 == 0:
                print(f"   [{idx}/{total_media}] Удалено media: {media_deleted}...")
            
            media_id = media_item.get("id")
            if not media_id:
                continue
            
            if not dry_run:
                try:
                    client._request("DELETE", f"/api/product-media/{media_id}")
                    media_deleted += 1
                except Exception as e:
                    print(f"      [ERROR] Ошибка удаления media {media_id}: {e}")
                    media_errors += 1
            else:
                media_deleted += 1
        
        print(f"   [OK] Удалено media: {media_deleted}")
        if media_errors > 0:
            print(f"   [ERROR] Ошибок: {media_errors}")
        print()
        
        return {"deleted": media_deleted, "errors": media_errors}
        
    except Exception as e:
        print(f"   [ERROR] Ошибка поиска product media: {e}")
        return {"deleted": 0, "errors": 0}


def generate_report(
    products_stats: Dict[str, Any],
    rules_stats: Dict[str, Any],
    manufacturers_stats: Dict[str, Any],
    media_stats: Dict[str, Any],
    dry_run: bool = True
) -> str:
    """Генерирует подробный отчёт."""
    report_lines = [
        "# Отчёт об очистке Shopware 6 для тестового импорта",
        "",
        f"**Режим:** {'DRY-RUN' if dry_run else 'APPLY'}",
        f"**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 1. Удаление товаров",
        "",
        f"- **Товаров удалено:** {products_stats.get('deleted', 0)}",
        f"- **Ошибок:** {products_stats.get('errors', 0)}",
        "",
        "## 2. Удаление Marketplace Price Rules",
        "",
        f"- **Rules удалено:** {rules_stats.get('deleted', 0)}",
        f"- **Rules пропущено:** {rules_stats.get('skipped', 0)}",
        "",
        "## 3. Удаление неиспользуемых Manufacturers",
        "",
        f"- **Manufacturers удалено:** {manufacturers_stats.get('deleted', 0)}",
        f"- **Manufacturers пропущено:** {manufacturers_stats.get('skipped', 0)}",
        "",
        "## 4. Удаление Product Media",
        "",
        f"- **Media удалено:** {media_stats.get('deleted', 0)}",
        f"- **Ошибок:** {media_stats.get('errors', 0)}",
        "",
        "## Итог",
        "",
        f"**Статус:** {'DRY-RUN завершён' if dry_run else 'Очистка применена'}",
        "",
        "## Примечания",
        "",
        "- Категории не тронуты",
        "- Sales channels не тронуты",
        "- Taxes не тронуты",
        "- Используемые rules не удалены",
    ]
    
    return "\n".join(report_lines)


def main():
    parser = argparse.ArgumentParser(description="Очистка Shopware 6 для тестового импорта")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Применить изменения (по умолчанию DRY-RUN)"
    )
    args = parser.parse_args()
    
    dry_run = not args.apply
    
    if dry_run:
        print("=" * 80)
        print("РЕЖИМ: DRY-RUN (изменения не будут применены)")
        print("=" * 80)
        print()
    else:
        print("=" * 80)
        print("РЕЖИМ: APPLY (изменения будут применены)")
        print("=" * 80)
        print()
        print("ВНИМАНИЕ: Будет удалено ВСЁ содержимое Shopware!")
        print("Нажмите Ctrl+C для отмены...")
        import time
        time.sleep(3)
    
    # Инициализация клиента
    config_data = load_json(ROOT / "config.json")
    shopware_data = config_data.get("shopware", {})
    config = ShopwareConfig(
        url=shopware_data.get("url", ""),
        access_key_id=shopware_data.get("access_key_id", ""),
        secret_access_key=shopware_data.get("secret_access_key", ""),
    )
    client = ShopwareClient(config)
    
    # ШАГ 1: Удаление всех товаров
    products_stats = delete_all_products(client, dry_run=dry_run)
    
    # ШАГ 2: Удаление Marketplace Price rules
    rules_stats = delete_marketplace_rules(client, dry_run=dry_run)
    
    # ШАГ 3: Удаление неиспользуемых manufacturers
    manufacturers_stats = delete_unused_manufacturers(client, dry_run=dry_run)
    
    # ШАГ 4: Удаление product media
    media_stats = delete_product_media(client, dry_run=dry_run)
    
    # Генерация отчёта
    report_content = generate_report(
        products_stats,
        rules_stats,
        manufacturers_stats,
        media_stats,
        dry_run=dry_run
    )
    
    report_path = REPORTS_DIR / "reset_before_test.md"
    with report_path.open("w", encoding="utf-8") as f:
        f.write(report_content)
    
    print("=" * 80)
    print("ОТЧЁТ СОХРАНЁН")
    print("=" * 80)
    print(f"Путь: {report_path}")
    print()
    
    # Вывод итогов
    print("ИТОГИ:")
    print(f"  Товаров удалено: {products_stats.get('deleted', 0)}")
    print(f"  Rules удалено: {rules_stats.get('deleted', 0)}")
    print(f"  Manufacturers удалено: {manufacturers_stats.get('deleted', 0)}")
    print(f"  Media удалено: {media_stats.get('deleted', 0)}")
    print()


if __name__ == "__main__":
    main()



