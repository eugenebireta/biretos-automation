"""
Нормализация системы Shopware 6: Manufacturers и Marketplace Price Rules.
Приведение к каноническому состоянию без создания новых сущностей.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from import_utils import ROOT, load_json

REPORTS_DIR = ROOT / "_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def find_canonical_manufacturer(client: ShopwareClient) -> Optional[Dict[str, Any]]:
    """Находит канонический Manufacturer 'Boeing' (с максимальным количеством товаров)."""
    print("=" * 80)
    print("ШАГ 1: НОРМАЛИЗАЦИЯ MANUFACTURER (Boeing)")
    print("=" * 80)
    print()
    
    print("1) Поиск всех manufacturers с именем 'Boeing'...")
    
    normalized_target = client._normalize_name("Boeing")
    
    try:
        response = client._request(
            "POST",
            "/api/search/product-manufacturer",
            json={
                "filter": [
                    {"field": "name", "type": "contains", "value": "Boeing"}
                ],
                "limit": 500,
            }
        )
        
        manufacturers = []
        if isinstance(response, dict) and "data" in response:
            for item in response.get("data", []):
                manufacturer_id = item.get("id")
                attrs = item.get("attributes", {})
                name = attrs.get("name") or item.get("name", "")
                
                if client._normalize_name(name) == normalized_target:
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
            print("   [ERROR] Manufacturers не найдены")
            return None
        
        # Сортируем по product_count DESC
        manufacturers.sort(key=lambda x: x["product_count"], reverse=True)
        
        canonical = manufacturers[0]
        print(f"   [OK] Найдено manufacturers: {len(manufacturers)}")
        print(f"   [OK] Канонический: {canonical['id']} (товаров: {canonical['product_count']})")
        print()
        
        return {
            "canonical": canonical,
            "all": manufacturers
        }
        
    except Exception as e:
        print(f"   [ERROR] Ошибка поиска manufacturers: {e}")
        return None


def normalize_manufacturers(client: ShopwareClient, data: Dict[str, Any]) -> Dict[str, Any]:
    """Нормализует manufacturers: перепривязывает товары и удаляет дубли."""
    canonical = data["canonical"]
    all_manufacturers = data["all"]
    
    canonical_id = canonical["id"]
    
    print("2) Перепривязка товаров к каноническому manufacturer...")
    
    # Собираем все manufacturerId для перепривязки
    manufacturers_to_fix = [m for m in all_manufacturers if m["id"] != canonical_id]
    non_canonical_ids = [m["id"] for m in manufacturers_to_fix]
    
    total_products_rebound = 0
    manufacturers_deleted = 0
    
    # Ищем все товары Boeing (независимо от manufacturerId)
    print("   Поиск всех товаров Boeing...", end=" ", flush=True)
    try:
        products_response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [
                    {"field": "manufacturer.name", "type": "equals", "value": "Boeing"}
                ],
                "limit": 500,
                "includes": {"product": ["id", "manufacturerId"]},
            }
        )
        
        products_to_fix = []
        if isinstance(products_response, dict) and "data" in products_response:
            for product_item in products_response.get("data", []):
                product_id = product_item.get("id")
                attrs = product_item.get("attributes", {})
                mfr_id = attrs.get("manufacturerId") or product_item.get("manufacturerId")
                
                if product_id and mfr_id and mfr_id in non_canonical_ids:
                    products_to_fix.append((product_id, mfr_id))
        
        print(f"[OK] Найдено товаров для перепривязки: {len(products_to_fix)}")
        
        # Перепривязываем товары
        for product_id, old_mfr_id in products_to_fix:
            try:
                client._request(
                    "PATCH",
                    f"/api/product/{product_id}",
                    json={
                        "manufacturerId": canonical_id
                    }
                )
                total_products_rebound += 1
            except Exception as e:
                print(f"   [WARNING] Ошибка перепривязки товара {product_id}: {e}")
        
        print(f"   [OK] Перепривязано товаров: {total_products_rebound}")
        
    except Exception as e:
        print(f"[ERROR: {str(e)[:30]}]")
    
    print()
    print(f"   [OK] Всего перепривязано товаров: {total_products_rebound}")
    print()
    
    print("3) Удаление дублей manufacturers (только с product_count == 0)...")
    
    for mfr in manufacturers_to_fix:
        mfr_id = mfr["id"]
        mfr_count = mfr["product_count"]
        
        if mfr_count == 0:
            try:
                client._request("DELETE", f"/api/product-manufacturer/{mfr_id}")
                manufacturers_deleted += 1
                print(f"   [OK] Удален manufacturer {mfr_id}")
            except Exception as e:
                print(f"   [WARNING] Ошибка удаления manufacturer {mfr_id}: {e}")
    
    print()
    print(f"   [OK] Удалено manufacturers: {manufacturers_deleted}")
    print()
    
    return {
        "canonical_id": canonical_id,
        "canonical_name": canonical["name"],
        "total_manufacturers": len(all_manufacturers),
        "products_rebound": total_products_rebound,
        "manufacturers_deleted": manufacturers_deleted
    }


def find_canonical_marketplace_rule(client: ShopwareClient) -> Optional[Dict[str, Any]]:
    """Находит каноническое правило 'Marketplace Price' (с максимальным количеством product-price)."""
    print("=" * 80)
    print("ШАГ 2: НОРМАЛИЗАЦИЯ MARKETPLACE PRICE RULE")
    print("=" * 80)
    print()
    
    print("1) Поиск всех rules с именем 'Marketplace Price'...")
    
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
                        "price_count": 0,  # Будет подсчитано ниже
                        "unique_products": 0
                    })
        
        # Подсчитываем использование каждого правила через поиск всех product-price
        print("   Подсчёт использования правил...", end=" ", flush=True)
        try:
            # Ищем все product-price с любым из найденных ruleId
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
            
            # Подсчитываем использование каждого ruleId
            rule_usage = {}
            if isinstance(all_prices_response, dict) and "data" in all_prices_response:
                for price_item in all_prices_response.get("data", []):
                    price_attrs = price_item.get("attributes", {})
                    rule_id = price_attrs.get("ruleId") or price_item.get("ruleId")
                    if rule_id in rule_ids_found:
                        if rule_id not in rule_usage:
                            rule_usage[rule_id] = 0
                        rule_usage[rule_id] += 1
            
            # Обновляем price_count для каждого правила
            for rule in rules:
                rule_id = rule["ruleId"]
                rule["price_count"] = rule_usage.get(rule_id, 0)
            
            print(f"[OK]")
        except Exception as e:
            print(f"[WARNING: {str(e)[:30]}]")
        
        if not rules:
            print("   [ERROR] Rules не найдены")
            return None
        
        # Сортируем по price_count DESC
        rules.sort(key=lambda x: x["price_count"], reverse=True)
        
        canonical = rules[0]
        print(f"   [OK] Найдено rules: {len(rules)}")
        print(f"   [OK] Каноническое: {canonical['ruleId']} (product-price: {canonical['price_count']})")
        print()
        
        return {
            "canonical": canonical,
            "all": rules
        }
        
    except Exception as e:
        print(f"   [ERROR] Ошибка поиска rules: {e}")
        return None


def normalize_marketplace_rules(client: ShopwareClient, data: Dict[str, Any]) -> Dict[str, Any]:
    """Нормализует Marketplace Price Rules: перепривязывает product-price и удаляет дубли."""
    canonical = data["canonical"]
    all_rules = data["all"]
    
    canonical_rule_id = canonical["ruleId"]
    
    print("2) Перепривязка product-price к каноническому правилу...")
    
    # Собираем все ruleId для перепривязки
    rules_to_fix = [r for r in all_rules if r["ruleId"] != canonical_rule_id]
    
    total_prices_rebound = 0
    rules_deleted = 0
    
    for rule in rules_to_fix:
        rule_id = rule["ruleId"]
        rule_price_count = rule["price_count"]
        
        if rule_price_count == 0:
            # Пропускаем - удалим позже
            continue
        
        print(f"   Перепривязка product-price от rule {rule_id} ({rule_price_count} записей)...", end=" ", flush=True)
        
        # Получаем все product-price этого правила
        try:
            prices_response = client._request(
                "POST",
                "/api/search/product-price",
                json={
                    "filter": [
                        {"field": "ruleId", "type": "equals", "value": rule_id}
                    ],
                    "limit": 500,
                    "associations": {
                        "price": {}
                    }
                }
            )
            
            prices_rebound = 0
            if isinstance(prices_response, dict) and "data" in prices_response:
                for price_item in prices_response.get("data", []):
                    price_id = price_item.get("id")
                    if not price_id:
                        continue
                    
                    # Пробуем получить данные из search response
                    price_attrs = price_item.get("attributes", {})
                    product_id = price_attrs.get("productId") or price_item.get("productId")
                    quantity_start = price_attrs.get("quantityStart") or price_item.get("quantityStart", 1)
                    
                    # Получаем price из associations или attributes
                    price_data = None
                    if "price" in price_item:
                        price_data = price_item["price"]
                    elif "price" in price_attrs:
                        price_data = price_attrs["price"]
                    elif "associations" in price_item and "price" in price_item["associations"]:
                        price_assoc = price_item["associations"]["price"]
                        if isinstance(price_assoc, dict) and "data" in price_assoc:
                            price_data = price_assoc["data"]
                        elif isinstance(price_assoc, list):
                            price_data = price_assoc
                    
                    # Если price_data не найден, пробуем GET (может не работать)
                    if not price_data:
                        try:
                            price_detail = client._request("GET", f"/api/product-price/{price_id}")
                            if isinstance(price_detail, dict):
                                price_detail_data = price_detail.get("data", {})
                                price_detail_attrs = price_detail_data.get("attributes", {})
                                price_data = price_detail_attrs.get("price") or price_detail_data.get("price", [])
                        except Exception:
                            # GET не работает - пропускаем эту запись
                            continue
                    
                    if not product_id or not price_data or not isinstance(price_data, list) or len(price_data) == 0:
                        continue
                    
                    price_obj = price_data[0]
                    currency_id = price_obj.get("currencyId")
                    gross = price_obj.get("gross")
                    net = price_obj.get("net")
                    linked = price_obj.get("linked", False)
                    
                    if currency_id and gross is not None:
                        try:
                            # Пробуем PATCH для обновления ruleId
                            try:
                                patch_payload = {
                                    "ruleId": canonical_rule_id
                                }
                                client._request("PATCH", f"/api/product-price/{price_id}", json=patch_payload)
                                prices_rebound += 1
                            except Exception as patch_e:
                                # Если PATCH не работает, пробуем DELETE+CREATE
                                try:
                                    # DELETE старую запись
                                    client._request("DELETE", f"/api/product-price/{price_id}")
                                    
                                    # CREATE новую с canonicalRuleId
                                    new_price_payload = {
                                        "productId": product_id,
                                        "ruleId": canonical_rule_id,
                                        "quantityStart": quantity_start,
                                        "price": [{
                                            "currencyId": currency_id,
                                            "gross": gross,
                                            "net": net,
                                            "linked": linked
                                        }]
                                    }
                                    client._request("POST", "/api/product-price", json=new_price_payload)
                                    prices_rebound += 1
                                except Exception as del_e:
                                    print(f"[ERROR: {str(del_e)[:30]}]", end=" ", flush=True)
                        except Exception as e:
                            print(f"[ERROR: {str(e)[:30]}]", end=" ", flush=True)
            
            total_prices_rebound += prices_rebound
            print(f"[OK] Перепривязано: {prices_rebound}")
            
        except Exception as e:
            print(f"[ERROR: {str(e)[:30]}]")
    
    print()
    print(f"   [OK] Всего перепривязано product-price: {total_prices_rebound}")
    print()
    
    print("3) Удаление дублей rules (только неиспользуемые)...")
    
    # Проверяем еще раз перед удалением - возможно, после перепривязки некоторые стали неиспользуемыми
    for rule in rules_to_fix:
        rule_id = rule["ruleId"]
        
        # Проверяем актуальное использование
        try:
            price_check = client._request(
                "POST",
                "/api/search/product-price",
                json={
                    "filter": [
                        {"field": "ruleId", "type": "equals", "value": rule_id}
                    ],
                    "limit": 1,
                    "totalCountMode": 1,
                }
            )
            actual_count = 0
            if isinstance(price_check, dict):
                actual_count = price_check.get("total", 0)
            
            if actual_count == 0:
                try:
                    client._request("DELETE", f"/api/rule/{rule_id}")
                    rules_deleted += 1
                    print(f"   [OK] Удалено правило {rule_id}")
                except Exception as e:
                    error_msg = str(e)
                    if "409" in error_msg or "DELETE_RESTRICTED" in error_msg:
                        # Правило все еще используется - это нормально после перепривязки
                        pass
                    else:
                        print(f"   [WARNING] Ошибка удаления правила {rule_id}: {e}")
        except Exception as e:
            print(f"   [WARNING] Ошибка проверки правила {rule_id}: {e}")
    
    print()
    print(f"   [OK] Удалено rules: {rules_deleted}")
    print()
    
    return {
        "canonical_rule_id": canonical_rule_id,
        "canonical_rule_name": canonical["name"],
        "total_rules": len(all_rules),
        "prices_rebound": total_prices_rebound,
        "rules_deleted": rules_deleted
    }


def validate_normalization(client: ShopwareClient) -> Dict[str, Any]:
    """Валидирует результат нормализации."""
    print("=" * 80)
    print("ШАГ 3: ВАЛИДАЦИЯ НОРМАЛИЗАЦИИ")
    print("=" * 80)
    print()
    
    results = {
        "manufacturers_count": 0,
        "rules_count": 0,
        "products_sample": []
    }
    
    print("1) Проверка manufacturers 'Boeing'...")
    try:
        normalized_target = client._normalize_name("Boeing")
        response = client._request(
            "POST",
            "/api/search/product-manufacturer",
            json={
                "filter": [
                    {"field": "name", "type": "contains", "value": "Boeing"}
                ],
                "limit": 500,
            }
        )
        if isinstance(response, dict) and "data" in response:
            manufacturers = []
            for item in response.get("data", []):
                attrs = item.get("attributes", {})
                name = attrs.get("name") or item.get("name", "")
                if client._normalize_name(name) == normalized_target:
                    manufacturers.append(item.get("id"))
            results["manufacturers_count"] = len(manufacturers)
            print(f"   [OK] Manufacturers 'Boeing': {len(manufacturers)}")
    except Exception as e:
        print(f"   [ERROR] {e}")
    
    print()
    
    print("2) Проверка rules 'Marketplace Price'...")
    try:
        normalized_target = client._normalize_name("Marketplace Price")
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
        if isinstance(response, dict) and "data" in response:
            rules = []
            for item in response.get("data", []):
                attrs = item.get("attributes", {})
                name = attrs.get("name") or item.get("name", "")
                if client._normalize_name(name) == normalized_target:
                    rules.append(item.get("id"))
            results["rules_count"] = len(rules)
            print(f"   [OK] Rules 'Marketplace Price': {len(rules)}")
    except Exception as e:
        print(f"   [ERROR] {e}")
    
    print()
    
    print("3) Проверка sample товаров (20)...")
    try:
        # Ищем товары Boeing
        products_response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [
                    {"field": "manufacturer.name", "type": "equals", "value": "Boeing"}
                ],
                "limit": 20,
                "includes": {"product": ["id", "productNumber", "manufacturerId"]},
            }
        )
        
        if isinstance(products_response, dict) and "data" in products_response:
            manufacturer_ids = set()
            rule_ids = set()
            
            for product_item in products_response.get("data", []):
                product_id = product_item.get("id")
                attrs = product_item.get("attributes", {})
                sku = attrs.get("productNumber") or product_item.get("productNumber", "")
                mfr_id = attrs.get("manufacturerId") or product_item.get("manufacturerId", "")
                
                manufacturer_ids.add(mfr_id)
                
                # Получаем marketplace price ruleId
                try:
                    price_search = client._request(
                        "POST",
                        "/api/search/product-price",
                        json={
                            "filter": [
                                {"field": "productId", "type": "equals", "value": product_id}
                            ],
                            "limit": 100,
                        }
                    )
                    if isinstance(price_search, dict) and "data" in price_search:
                        for price_item in price_search.get("data", []):
                            price_attrs = price_item.get("attributes", {})
                            rule_id = price_attrs.get("ruleId") or price_item.get("ruleId")
                            if rule_id:
                                # Проверяем, является ли это Marketplace Price
                                try:
                                    rule_response = client._request("GET", f"/api/rule/{rule_id}")
                                    if isinstance(rule_response, dict):
                                        rule_data = rule_response.get("data", {})
                                        rule_attrs = rule_data.get("attributes", {})
                                        rule_name = rule_attrs.get("name") or rule_data.get("name", "")
                                        if client._normalize_name(rule_name) == client._normalize_name("Marketplace Price"):
                                            rule_ids.add(rule_id)
                                except Exception:
                                    pass
                except Exception:
                    pass
                
                results["products_sample"].append({
                    "sku": sku,
                    "manufacturerId": mfr_id
                })
            
            print(f"   [OK] Проверено товаров: {len(results['products_sample'])}")
            print(f"   [OK] Уникальных manufacturerId: {len(manufacturer_ids)}")
            print(f"   [OK] Уникальных marketplace ruleId: {len(rule_ids)}")
            
            results["unique_manufacturer_ids"] = len(manufacturer_ids)
            results["unique_rule_ids"] = len(rule_ids)
            results["manufacturer_ids"] = list(manufacturer_ids)
            results["rule_ids"] = list(rule_ids)
    
    except Exception as e:
        print(f"   [ERROR] {e}")
    
    print()
    
    return results


def save_report_manufacturer(result: Dict[str, Any]):
    """Сохраняет отчёт по нормализации manufacturers."""
    file_path = REPORTS_DIR / "normalize_manufacturer.md"
    
    with file_path.open("w", encoding="utf-8") as f:
        f.write("# Нормализация Manufacturers: Boeing\n\n")
        f.write(f"**Дата:** {Path(__file__).stat().st_mtime}\n\n")
        f.write("## Результаты нормализации\n\n")
        f.write(f"- **Канонический Manufacturer ID:** {result['canonical_id']}\n")
        f.write(f"- **Канонический Manufacturer Name:** {result['canonical_name']}\n")
        f.write(f"- **Всего найдено manufacturers:** {result['total_manufacturers']}\n")
        f.write(f"- **Перепривязано товаров:** {result['products_rebound']}\n")
        f.write(f"- **Удалено manufacturers:** {result['manufacturers_deleted']}\n\n")
        f.write("## Статус\n\n")
        if result['total_manufacturers'] - result['manufacturers_deleted'] == 1:
            f.write("✅ **УСПЕХ:** Остался ровно 1 manufacturer 'Boeing'\n")
        else:
            f.write(f"⚠️ **ВНИМАНИЕ:** Осталось {result['total_manufacturers'] - result['manufacturers_deleted']} manufacturers\n")
    
    print(f"[OK] Отчёт сохранен: {file_path}")


def save_report_marketplace_rule(result: Dict[str, Any]):
    """Сохраняет отчёт по нормализации Marketplace Price Rules."""
    file_path = REPORTS_DIR / "normalize_marketplace_rule.md"
    
    with file_path.open("w", encoding="utf-8") as f:
        f.write("# Нормализация Marketplace Price Rules\n\n")
        f.write(f"**Дата:** {Path(__file__).stat().st_mtime}\n\n")
        f.write("## Результаты нормализации\n\n")
        f.write(f"- **Каноническое Rule ID:** {result['canonical_rule_id']}\n")
        f.write(f"- **Каноническое Rule Name:** {result['canonical_rule_name']}\n")
        f.write(f"- **Всего найдено rules:** {result['total_rules']}\n")
        f.write(f"- **Перепривязано product-price:** {result['prices_rebound']}\n")
        f.write(f"- **Удалено rules:** {result['rules_deleted']}\n\n")
        f.write("## Статус\n\n")
        if result['total_rules'] - result['rules_deleted'] == 1:
            f.write("✅ **УСПЕХ:** Осталось ровно 1 правило 'Marketplace Price'\n")
        else:
            f.write(f"⚠️ **ВНИМАНИЕ:** Осталось {result['total_rules'] - result['rules_deleted']} правил\n")
    
    print(f"[OK] Отчёт сохранен: {file_path}")


def save_report_validation(validation: Dict[str, Any]):
    """Сохраняет отчёт по валидации."""
    file_path = REPORTS_DIR / "normalize_validation.md"
    
    with file_path.open("w", encoding="utf-8") as f:
        f.write("# Валидация нормализации\n\n")
        f.write(f"**Дата:** {Path(__file__).stat().st_mtime}\n\n")
        f.write("## Результаты проверки\n\n")
        f.write(f"- **Manufacturers 'Boeing':** {validation['manufacturers_count']}\n")
        f.write(f"- **Rules 'Marketplace Price':** {validation['rules_count']}\n")
        f.write(f"- **Проверено товаров:** {len(validation['products_sample'])}\n")
        f.write(f"- **Уникальных manufacturerId:** {validation.get('unique_manufacturer_ids', 'N/A')}\n")
        f.write(f"- **Уникальных marketplace ruleId:** {validation.get('unique_rule_ids', 'N/A')}\n\n")
        
        f.write("## Статус\n\n")
        if validation['manufacturers_count'] == 1:
            f.write("✅ Manufacturers: OK (ровно 1)\n")
        else:
            f.write(f"❌ Manufacturers: FAIL ({validation['manufacturers_count']} вместо 1)\n")
        
        f.write("\n")
        
        if validation['rules_count'] == 1:
            f.write("✅ Rules: OK (ровно 1)\n")
        else:
            f.write(f"❌ Rules: FAIL ({validation['rules_count']} вместо 1)\n")
        
        f.write("\n")
        
        if validation.get('unique_manufacturer_ids') == 1:
            f.write("✅ Sample товаров: manufacturerId одинаковый\n")
        else:
            f.write(f"❌ Sample товаров: manufacturerId разный ({validation.get('unique_manufacturer_ids', 'N/A')})\n")
        
        f.write("\n")
        
        if validation.get('unique_rule_ids') == 1:
            f.write("✅ Sample товаров: marketplace ruleId одинаковый\n")
        else:
            f.write(f"❌ Sample товаров: marketplace ruleId разный ({validation.get('unique_rule_ids', 'N/A')})\n")
        
        f.write("\n## Детальная информация\n\n")
        f.write("### Manufacturer IDs в sample:\n\n")
        for mfr_id in validation.get('manufacturer_ids', []):
            f.write(f"- {mfr_id}\n")
        
        f.write("\n### Marketplace Rule IDs в sample:\n\n")
        for rule_id in validation.get('rule_ids', []):
            f.write(f"- {rule_id}\n")
    
    print(f"[OK] Отчёт сохранен: {file_path}")


def main():
    print("=" * 80)
    print("НОРМАЛИЗАЦИЯ СИСТЕМЫ SHOPWARE 6")
    print("=" * 80)
    print()
    print("Режим: НОРМАЛИЗАЦИЯ (перепривязка существующих сущностей)")
    print()
    
    # Загружаем конфигурацию
    config_data = load_json(ROOT / "config.json")
    shopware_data = config_data.get("shopware", {})
    config = ShopwareConfig(
        url=shopware_data.get("url", ""),
        access_key_id=shopware_data.get("access_key_id", ""),
        secret_access_key=shopware_data.get("secret_access_key", ""),
    )
    client = ShopwareClient(config)
    
    # ШАГ 1: Manufacturers
    manufacturer_data = find_canonical_manufacturer(client)
    if manufacturer_data:
        manufacturer_result = normalize_manufacturers(client, manufacturer_data)
        save_report_manufacturer(manufacturer_result)
    else:
        print("[ERROR] Не удалось найти manufacturers, пропускаем нормализацию")
        manufacturer_result = None
    
    print()
    
    # ШАГ 2: Marketplace Price Rules
    rule_data = find_canonical_marketplace_rule(client)
    if rule_data:
        rule_result = normalize_marketplace_rules(client, rule_data)
        save_report_marketplace_rule(rule_result)
    else:
        print("[ERROR] Не удалось найти rules, пропускаем нормализацию")
        rule_result = None
    
    print()
    
    # ШАГ 3: Валидация
    validation_result = validate_normalization(client)
    save_report_validation(validation_result)
    
    print()
    print("=" * 80)
    print("НОРМАЛИЗАЦИЯ ЗАВЕРШЕНА")
    print("=" * 80)
    print()
    print("Отчёты сохранены в:")
    print(f"  - {REPORTS_DIR / 'normalize_manufacturer.md'}")
    print(f"  - {REPORTS_DIR / 'normalize_marketplace_rule.md'}")
    print(f"  - {REPORTS_DIR / 'normalize_validation.md'}")
    print()
    
    # Итоговый статус
    if validation_result.get("manufacturers_count") == 1 and validation_result.get("rules_count") == 1:
        print("[OK] УСПЕХ: Система нормализована")
    else:
        print("[WARNING] ВНИМАНИЕ: Требуется дополнительная проверка")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

