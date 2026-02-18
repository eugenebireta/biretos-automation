"""
Переимпорт 10 товаров с применением исправленной логики категорий.
Режим UPDATE, применяются только categories.
"""
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent))

from clients import ShopwareClient, ShopwareConfig
from category_utils import get_category_chain, is_leaf_category
from import_utils import ROOT, load_json

REPORTS_DIR = ROOT / "_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Список SKU для переимпорта
SKU_LIST = [
    "500944170",
    "500944178",
    "500944207",
    "500944220",
    "500944223",
    "500944234",
    "500944237",
    "500944238",
    "500944241",
    "500944256",
]

FULL_IMPORT_SCRIPT = ROOT / "src" / "full_import.py"
VERIFY_SCRIPT = ROOT / "src" / "verify_product_state.py"


def get_category_info(client: ShopwareClient, product_id: str) -> Dict[str, Any]:
    """
    Получает информацию о категориях товара КАНОНИЧЕСКИ через Shopware API.
    
    # DO NOT PARSE STDOUT FOR CATEGORIES
    # Категории получаются ТОЛЬКО через Shopware API: GET /api/product/{id}?associations[categories]=true
    """
    try:
        category_ids = []
        
        # КАНОНИЧЕСКИЙ СПОСОБ: GET /api/product/{id}?associations[categories]={}
        # Используем тот же метод, что и verify_product_state.py
        try:
            response = client._request(
                "GET",
                f"/api/product/{product_id}",
                params={"associations[categories]": "{}"}
            )
            
            if isinstance(response, dict):
                product_data = response.get("data", {})
                included_list = response.get("included", [])
                
                # Пробуем через relationships (канонический способ, как в verify_product_state.py)
                relationships = product_data.get("relationships", {})
                if isinstance(relationships, dict):
                    categories_rel = relationships.get("categories", {})
                    if isinstance(categories_rel, dict):
                        categories_data = categories_rel.get("data", [])
                        if isinstance(categories_data, list):
                            for cat_ref in categories_data:
                                if isinstance(cat_ref, dict):
                                    cat_id = cat_ref.get("id")
                                    if cat_id:
                                        category_ids.append(cat_id)
                
                # Если не нашли через relationships, пробуем через included
                if not category_ids:
                    for item in included_list:
                        if isinstance(item, dict) and item.get("type") == "category":
                            cat_id = item.get("id")
                            if cat_id:
                                category_ids.append(cat_id)
                
                # Если все еще не нашли, пробуем через GET с associations (более надежный способ)
                if not category_ids:
                    try:
                        product_with_cats = client._request("GET", f"/api/product/{product_id}?associations[categories]=")
                        if isinstance(product_with_cats, dict):
                            prod_data = product_with_cats.get("data", {})
                            prod_rels = prod_data.get("relationships", {})
                            if isinstance(prod_rels, dict):
                                cats_rel = prod_rels.get("categories", {})
                                if isinstance(cats_rel, dict):
                                    cats_data = cats_rel.get("data", [])
                                    for cat_ref in cats_data:
                                        if isinstance(cat_ref, dict):
                                            cat_id = cat_ref.get("id")
                                            if cat_id:
                                                category_ids.append(cat_id)
                    except Exception:
                        pass
        except Exception as e:
            # Если не удалось, возвращаем ошибку
            return {"error": f"Failed to get categories: {str(e)}"}
        
        # Определяем leaf категорию и depth
        # КАНОНИЧЕСКАЯ ПРОВЕРКА: последний элемент должен быть leaf
        leaf_category_id = None
        leaf_category_name = None
        depth = 0
        full_chain = []
        
        if category_ids:
            # Проверяем последний элемент - он должен быть leaf
            last_cat_id = category_ids[-1]
            if is_leaf_category(client, last_cat_id):
                leaf_category_id = last_cat_id
                # Получаем полную цепочку для определения depth
                full_chain = get_category_chain(client, last_cat_id)
                if full_chain:
                    depth = len(full_chain)
                    # Получаем имя leaf категории
                    try:
                        cat_response = client._request("GET", f"/api/category/{leaf_category_id}")
                        if isinstance(cat_response, dict):
                            cat_data = cat_response.get("data", {})
                            cat_attrs = cat_data.get("attributes", {})
                            leaf_category_name = cat_attrs.get("name") or cat_data.get("name", "")
                    except Exception:
                        pass
            else:
                # Последний элемент не leaf - ищем leaf среди всех категорий
                for cat_id in category_ids:
                    if is_leaf_category(client, cat_id):
                        chain = get_category_chain(client, cat_id)
                        if chain:
                            chain_depth = len(chain)
                            if chain_depth > depth:
                                depth = chain_depth
                                leaf_category_id = cat_id
                                full_chain = chain
                                # Получаем имя leaf категории
                                try:
                                    cat_response = client._request("GET", f"/api/category/{cat_id}")
                                    if isinstance(cat_response, dict):
                                        cat_data = cat_response.get("data", {})
                                        cat_attrs = cat_data.get("attributes", {})
                                        leaf_category_name = cat_attrs.get("name") or cat_data.get("name", "")
                                except Exception:
                                    pass
        
        # Формируем path для отображения
        chain_path = []
        if full_chain:
            for cat_id in full_chain:
                try:
                    cat_response = client._request("GET", f"/api/category/{cat_id}")
                    if isinstance(cat_response, dict):
                        cat_data = cat_response.get("data", {})
                        cat_attrs = cat_data.get("attributes", {})
                        cat_name = cat_attrs.get("name") or cat_data.get("name", "")
                        chain_path.append(f"{cat_name} ({cat_id[:8]})")
                except Exception:
                    chain_path.append(f"Category {cat_id[:8]}")
        
        return {
            "category_count": len(category_ids),
            "category_ids": category_ids,
            "leaf_category_id": leaf_category_id,
            "leaf_category_name": leaf_category_name,
            "depth": depth,
            "full_chain": full_chain,
            "chain_path": " > ".join(chain_path) if chain_path else "N/A",
            # КАНОНИЧЕСКАЯ ПРОВЕРКА: categories.length >= 2 и последний элемент = leaf
            "is_valid": len(category_ids) >= 2 and leaf_category_id is not None and category_ids[-1] == leaf_category_id
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    print("=" * 80)
    print("ПЕРЕИМПОРТ 10 ТОВАРОВ С ИСПРАВЛЕННОЙ ЛОГИКОЙ КАТЕГОРИЙ")
    print("=" * 80)
    print()
    print("Режим: UPDATE (только categories)")
    print(f"SKU: {', '.join(SKU_LIST)}")
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
    
    results = []
    
    # ШАГ 1: Переимпорт товаров
    print("=" * 80)
    print("ШАГ 1: ПЕРЕИМПОРТ ТОВАРОВ")
    print("=" * 80)
    print()
    
    for i, sku in enumerate(SKU_LIST, 1):
        print(f"[{i}/{len(SKU_LIST)}] Импорт SKU: {sku}...", end=" ", flush=True)
        
        try:
            result = subprocess.run(
                [sys.executable, str(FULL_IMPORT_SCRIPT), "--single-sku", sku, "--source", "snapshot"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120
            )
            
            if result.returncode == 0:
                print("[OK]")
                results.append({
                    "sku": sku,
                    "import_status": "OK",
                    "import_error": None
                })
            else:
                print(f"[FAIL] (code: {result.returncode})")
                error_msg = result.stderr[:100] if result.stderr else "Unknown error"
                results.append({
                    "sku": sku,
                    "import_status": "FAIL",
                    "import_error": error_msg
                })
        except Exception as e:
            print(f"[ERROR]: {str(e)[:40]}")
            results.append({
                "sku": sku,
                "import_status": "ERROR",
                "import_error": str(e)
            })
        
        # Небольшая задержка между импортами
        if i < len(SKU_LIST):
            time.sleep(1)
    
    print()
    
    # ШАГ 2: Валидация категорий КАНОНИЧЕСКИ через Shopware API
    # DO NOT PARSE STDOUT FOR CATEGORIES
    # Категории получаются ТОЛЬКО через Shopware API: GET /api/product/{id}?associations[categories]=true
    print("=" * 80)
    print("ШАГ 2: ВАЛИДАЦИЯ КАТЕГОРИЙ (КАНОНИЧЕСКИ)")
    print("=" * 80)
    print()
    print("Задержка 5 секунд для применения изменений в Shopware API...")
    time.sleep(5)
    print()
    
    for i, result in enumerate(results, 1):
        sku = result["sku"]
        print(f"[{i}/{len(results)}] Проверка SKU: {sku}...", end=" ", flush=True)
        
        # Находим product_id по SKU
        try:
            product_search = client._request(
                "POST",
                "/api/search/product",
                json={
                    "filter": [
                        {"field": "productNumber", "type": "equals", "value": sku}
                    ],
                    "limit": 1,
                    "includes": {"product": ["id"]},
                }
            )
            
            product_id = None
            if isinstance(product_search, dict) and "data" in product_search:
                products = product_search.get("data", [])
                if products:
                    product_id = products[0].get("id")
            
            if not product_id:
                print("[ERROR: Product not found]")
                result["validation_status"] = "ERROR"
                result["validation_error"] = "Product not found"
                continue
            
            # Получаем информацию о категориях КАНОНИЧЕСКИ через Shopware API
            category_info = get_category_info(client, product_id)
            
            if "error" in category_info:
                print(f"[ERROR: {category_info['error'][:30]}]")
                result["validation_status"] = "ERROR"
                result["validation_error"] = category_info["error"]
            else:
                result["category_count"] = category_info["category_count"]
                result["depth"] = category_info["depth"]
                result["leaf_category_id"] = category_info["leaf_category_id"]
                result["leaf_category_name"] = category_info["leaf_category_name"]
                result["chain_path"] = category_info["chain_path"]
                result["full_chain"] = category_info["full_chain"]
                result["is_valid"] = category_info["is_valid"]
                
                status = "OK" if category_info["is_valid"] else "FAIL"
                print(f"[{status}] categories={category_info['category_count']}, depth={category_info['depth']}, leaf={category_info['leaf_category_id'][:8] if category_info['leaf_category_id'] else 'N/A'}")
                result["validation_status"] = status
        except Exception as e:
            print(f"[ERROR: {str(e)[:30]}]")
            result["validation_status"] = "ERROR"
            result["validation_error"] = str(e)
    
    print()
    
    # ШАГ 3: Запуск verify_product_state.py для каждого товара
    print("=" * 80)
    print("ШАГ 3: ПРОВЕРКА ЧЕРЕЗ verify_product_state.py")
    print("=" * 80)
    print()
    
    for i, result in enumerate(results, 1):
        sku = result["sku"]
        print(f"[{i}/{len(results)}] Проверка SKU: {sku}...", end=" ", flush=True)
        
        try:
            verify_result = subprocess.run(
                [sys.executable, str(VERIFY_SCRIPT), sku],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60
            )
            
            if verify_result.returncode == 0:
                output = verify_result.stdout
                # Парсим результат verify_product_state.py
                result["verify_output"] = output
                
                # Извлекаем статус Categories из вывода
                if "Categories" in output:
                    if "OK" in output.split("Categories")[1].split("\n")[0]:
                        result["verify_categories"] = "OK"
                    else:
                        result["verify_categories"] = "FAIL"
                else:
                    result["verify_categories"] = "UNKNOWN"
                
                print("[OK]")
            else:
                print(f"[FAIL] (code: {verify_result.returncode})")
                result["verify_categories"] = "ERROR"
        except Exception as e:
            print(f"[ERROR: {str(e)[:30]}]")
            result["verify_categories"] = "ERROR"
    
    print()
    
    # Формируем отчёт
    print("=" * 80)
    print("ФОРМИРОВАНИЕ ОТЧЁТА")
    print("=" * 80)
    print()
    
    report_path = REPORTS_DIR / "reimport_10_categories.md"
    
    valid_count = sum(1 for r in results if r.get("is_valid") is True)
    success_count = sum(1 for r in results if r.get("import_status") == "OK" and r.get("is_valid") is True)
    
    with report_path.open("w", encoding="utf-8") as f:
        f.write("# Переимпорт 10 товаров с исправленной логикой категорий\n\n")
        f.write(f"**Дата:** {Path(__file__).stat().st_mtime}\n\n")
        f.write("## Результаты\n\n")
        f.write(f"- **Успешно импортировано:** {sum(1 for r in results if r.get('import_status') == 'OK')}/{len(results)}\n")
        f.write(f"- **Валидных категорий:** {valid_count}/{len(results)}\n")
        f.write(f"- **Успешно (импорт + валидация):** {success_count}/{len(results)}\n\n")
        
        f.write("## Таблица результатов\n\n")
        f.write("| SKU | Import | Categories | Depth | Leaf UUID | Status |\n")
        f.write("|-----|--------|------------|-------|-----------|--------|\n")
        
        for result in results:
            sku = result["sku"]
            import_status = result.get("import_status", "UNKNOWN")
            category_count = result.get("category_count", 0)
            depth = result.get("depth", 0)
            leaf_id = result.get("leaf_category_id", "N/A")
            if leaf_id and leaf_id != "N/A":
                leaf_id = leaf_id[:8]
            is_valid = result.get("is_valid", False)
            status = "[OK]" if is_valid else "[FAIL]"
            
            f.write(f"| {sku} | {import_status} | {category_count} | {depth} | {leaf_id} | {status} |\n")
        
        f.write("\n## Детальная информация\n\n")
        
        for i, result in enumerate(results, 1):
            sku = result["sku"]
            f.write(f"### {i}. SKU: {sku}\n\n")
            f.write(f"- **Import Status:** {result.get('import_status', 'UNKNOWN')}\n")
            if result.get("import_error"):
                f.write(f"- **Import Error:** {result['import_error']}\n")
            f.write(f"- **Validation Status:** {result.get('validation_status', 'UNKNOWN')}\n")
            f.write(f"- **Category Count:** {result.get('category_count', 0)}\n")
            f.write(f"- **Depth:** {result.get('depth', 0)}\n")
            f.write(f"- **Leaf Category ID:** {result.get('leaf_category_id', 'N/A')}\n")
            f.write(f"- **Leaf Category Name:** {result.get('leaf_category_name', 'N/A')}\n")
            f.write(f"- **Chain Path:** {result.get('chain_path', 'N/A')}\n")
            f.write(f"- **Is Valid:** {'Yes' if result.get('is_valid') else 'No'}\n")
            f.write(f"- **Verify Categories:** {result.get('verify_categories', 'UNKNOWN')}\n")
            f.write("\n")
        
        f.write("## Критерий успеха\n\n")
        f.write(f"- **Требуется:** 10/10 товаров с categories > 0, depth >= 2, последний = leaf\n")
        f.write(f"- **Фактически:** {success_count}/10 товаров\n")
        f.write(f"- **Вердикт:** {'GO' if success_count == 10 else 'NO-GO'}\n")
    
    print(f"[OK] Отчёт сохранен: {report_path}")
    print()
    
    # Итоговая статистика
    print("=" * 80)
    print("ИТОГИ")
    print("=" * 80)
    print(f"Успешно импортировано: {sum(1 for r in results if r.get('import_status') == 'OK')}/{len(results)}")
    print(f"Валидных категорий: {valid_count}/{len(results)}")
    print(f"Успешно (импорт + валидация): {success_count}/{len(results)}")
    print()
    
    if success_count == 10:
        print("[OK] GO: Все товары успешно переимпортированы с корректными категориями")
    else:
        print(f"[FAIL] NO-GO: Требуется исправление ({10 - success_count} товаров)")
    
    print()
    print(f"Отчёт: {report_path}")
    
    return 0 if success_count == 10 else 1


if __name__ == "__main__":
    sys.exit(main())

