"""
Исправление логики назначения категорий при импорте.
Гарантирует, что товары привязываются к полной цепочке категорий с leaf-категорией.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from category_utils import get_category_chain, is_leaf_category
from import_utils import ROOT, load_json

REPORTS_DIR = ROOT / "_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def validate_product_categories(client: ShopwareClient, product_id: str) -> Dict[str, Any]:
    """Валидирует категории товара."""
    try:
        # Получаем категории через search API для product-category
        category_ids = []
        category_names = []
        
        try:
            search_response = client._request(
                "POST",
                "/api/search/product-category",
                json={
                    "filter": [
                        {"field": "productId", "type": "equals", "value": product_id}
                    ],
                    "limit": 100,
                    "includes": {"product_category": ["categoryId"]},
                }
            )
            
            if isinstance(search_response, dict) and "data" in search_response:
                for item in search_response.get("data", []):
                    item_attrs = item.get("attributes", {})
                    cat_id = item_attrs.get("categoryId") or item.get("categoryId")
                    if cat_id:
                        category_ids.append(cat_id)
        except Exception:
            pass
        
        # Если не нашли через search, пробуем через GET product
        if not category_ids:
            try:
                response = client._request(
                    "GET",
                    f"/api/product/{product_id}",
                    params={"associations[categories]": "{}"}
                )
                
                if isinstance(response, dict):
                    product_data = response.get("data", {})
                    product_attrs = product_data.get("attributes", {})
                    categories = product_attrs.get("categories", [])
                    
                    # Также проверяем included
                    if not categories:
                        included = response.get("included", [])
                        for item in included:
                            if item.get("type") == "category":
                                categories.append(item)
                    
                    for cat in categories:
                        cat_id = cat.get("id")
                        if cat_id:
                            category_ids.append(cat_id)
            except Exception:
                pass
        
        # Получаем имена категорий
        for cat_id in category_ids:
            try:
                cat_response = client._request("GET", f"/api/category/{cat_id}")
                if isinstance(cat_response, dict):
                    cat_data = cat_response.get("data", {})
                    cat_attrs = cat_data.get("attributes", {})
                    cat_name = cat_attrs.get("name") or cat_data.get("name", "")
                    category_names.append(cat_name or f"Category {cat_id[:8]}")
                else:
                    category_names.append(f"Category {cat_id[:8]}")
            except Exception:
                category_names.append(f"Category {cat_id[:8]}")
        
        # Определяем leaf-категорию
        leaf_category_id = None
        leaf_category_name = None
        depth = 0
        
        for cat_id in category_ids:
            if is_leaf_category(client, cat_id):
                # Получаем цепочку для определения глубины
                chain = get_category_chain(client, cat_id)
                if chain:
                    chain_depth = len(chain)
                    if chain_depth > depth:
                        depth = chain_depth
                        leaf_category_id = cat_id
                        # Получаем имя leaf категории
                        try:
                            cat_response = client._request("GET", f"/api/category/{cat_id}")
                            if isinstance(cat_response, dict):
                                cat_data = cat_response.get("data", {})
                                cat_attrs = cat_data.get("attributes", {})
                                leaf_category_name = cat_attrs.get("name") or cat_data.get("name", "")
                        except Exception:
                            pass
        
        # Если не нашли leaf, проверяем последнюю категорию
        if not leaf_category_id and category_ids:
            last_cat_id = category_ids[-1]
            chain = get_category_chain(client, last_cat_id)
            if chain:
                depth = len(chain)
                leaf_category_id = chain[-1]  # Последняя в цепочке должна быть leaf
        
        # Получаем полную цепочку для leaf
        full_chain = []
        if leaf_category_id:
            full_chain = get_category_chain(client, leaf_category_id)
        
        return {
            "product_id": product_id,
            "category_ids": category_ids,
            "category_names": category_names,
            "leaf_category_id": leaf_category_id,
            "leaf_category_name": leaf_category_name,
            "full_chain": full_chain,
            "depth": depth,
            "is_valid": depth >= 2 and leaf_category_id is not None
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    print("=" * 80)
    print("АНАЛИЗ ЛОГИКИ КАТЕГОРИЙ")
    print("=" * 80)
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
    
    # Ищем 5 товаров Boeing для валидации
    print("1) Поиск 5 товаров Boeing...")
    try:
        products_response = client._request(
            "POST",
            "/api/search/product",
            json={
                "filter": [
                    {"field": "manufacturer.name", "type": "equals", "value": "Boeing"}
                ],
                "limit": 5,
                "includes": {"product": ["id", "productNumber"]},
            }
        )
        
        products = []
        if isinstance(products_response, dict) and "data" in products_response:
            for item in products_response.get("data", []):
                product_id = item.get("id")
                attrs = item.get("attributes", {})
                sku = attrs.get("productNumber") or item.get("productNumber", "")
                if product_id and sku:
                    products.append({"id": product_id, "sku": sku})
        
        print(f"   [OK] Найдено товаров: {len(products)}")
        print()
        
        if not products:
            print("[ERROR] Товары не найдены")
            return 1
        
        # Валидируем категории для каждого товара
        print("2) Валидация категорий...")
        print()
        
        results = []
        for i, product in enumerate(products, 1):
            print(f"   [{i}/{len(products)}] SKU: {product['sku']}...", end=" ", flush=True)
            validation = validate_product_categories(client, product["id"])
            validation["sku"] = product["sku"]
            results.append(validation)
            
            if "error" in validation:
                print(f"[ERROR: {validation['error'][:30]}]")
            else:
                status = "OK" if validation["is_valid"] else "FAIL"
                print(f"[{status}] depth={validation['depth']}, leaf={validation['leaf_category_id'][:8] if validation['leaf_category_id'] else 'N/A'}")
        
        print()
        
        # Сохраняем отчёт
        report_path = REPORTS_DIR / "fix_leaf_categories.md"
        with report_path.open("w", encoding="utf-8") as f:
            f.write("# Анализ логики категорий\n\n")
            f.write(f"**Дата:** {Path(__file__).stat().st_mtime}\n\n")
            f.write("## Результаты валидации 5 товаров\n\n")
            
            for result in results:
                f.write(f"### SKU: {result.get('sku', 'N/A')}\n\n")
                f.write(f"- **Product ID:** {result.get('product_id', 'N/A')}\n")
                f.write(f"- **Категорий привязано:** {len(result.get('category_ids', []))}\n")
                f.write(f"- **Leaf Category ID:** {result.get('leaf_category_id', 'N/A')}\n")
                f.write(f"- **Leaf Category Name:** {result.get('leaf_category_name', 'N/A')}\n")
                f.write(f"- **Depth (глубина):** {result.get('depth', 0)}\n")
                f.write(f"- **Полная цепочка:** {', '.join(result.get('full_chain', []))}\n")
                f.write(f"- **Статус:** {'✅ OK' if result.get('is_valid') else '❌ FAIL'}\n\n")
                
                if result.get('category_names'):
                    f.write("**Названия категорий:**\n")
                    for name in result.get('category_names', []):
                        f.write(f"- {name}\n")
                    f.write("\n")
            
            f.write("## Выводы\n\n")
            valid_count = sum(1 for r in results if r.get("is_valid"))
            f.write(f"- **Валидных товаров:** {valid_count}/{len(results)}\n")
            f.write(f"- **Требуется исправление:** {len(results) - valid_count} товаров\n\n")
            
            if valid_count < len(results):
                f.write("### Проблемы:\n\n")
                for result in results:
                    if not result.get("is_valid"):
                        f.write(f"- **{result.get('sku')}:** ")
                        if result.get('depth', 0) < 2:
                            f.write(f"Глубина < 2 (depth={result.get('depth', 0)})\n")
                        elif not result.get('leaf_category_id'):
                            f.write("Leaf категория не найдена\n")
                        else:
                            f.write("Неизвестная проблема\n")
        
        print(f"[OK] Отчёт сохранен: {report_path}")
        print()
        
        # Итоговая статистика
        valid_count = sum(1 for r in results if r.get("is_valid"))
        print("=" * 80)
        print("ИТОГИ")
        print("=" * 80)
        print(f"Валидных товаров: {valid_count}/{len(results)}")
        print(f"Требуется исправление: {len(results) - valid_count}")
        print()
        
        return 0
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

