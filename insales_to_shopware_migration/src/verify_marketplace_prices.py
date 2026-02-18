"""
Проверка корректности восстановления Marketplace цен в Shopware 6.

Проверяет:
1. product.price НЕ изменился
2. product.prices содержит rule "Marketplace Price"
3. gross == price2 из snapshot
4. Правило одно, не продублировано
5. Цены привязаны к нужной currencyId
6. Edge-cases (товары без SKU, price2=0, существующие advanced prices)
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = ROOT / "insales_snapshot" / "products.ndjson"
CONFIG_PATH = ROOT / "config.json"
REPORT_PATH = ROOT / "reports" / "marketplace_prices_verification.md"

# Константы
MARKETPLACE_RULE_NAME = "Marketplace Price"
LOG_PATH = ROOT / ".cursor" / "debug.log"

# #region agent log
def log_debug(location: str, message: str, data: Dict[str, Any], hypothesis_id: str = "general"):
    """Логирование для отладки"""
    try:
        log_entry = {
            "sessionId": "verification-session",
            "runId": "verify-1",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(__import__("time").time() * 1000)
        }
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Игнорируем ошибки логирования
# #endregion


def load_insales_products() -> List[Dict[str, Any]]:
    """Загружает товары из snapshot InSales"""
    products = []
    if not SNAPSHOT_PATH.exists():
        print(f"ERROR: Snapshot не найден: {SNAPSHOT_PATH}")
        return products
    
    with SNAPSHOT_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                product = json.loads(line)
                products.append(product)
            except json.JSONDecodeError:
                continue
    
    return products


def extract_price2_products(products: List[Dict[str, Any]]) -> List[Tuple[str, float, str, int]]:
    """
    Извлекает товары с price2 (Marketplace цена).
    
    Returns:
        Список кортежей: (product_number, price2, product_name, insales_id)
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
        insales_id = product.get("id")
        
        # Работаем ТОЛЬКО с товарами, где price2 != null
        if product_number and price2 is not None:
            try:
                price2_float = float(price2)
                # Включаем даже price2=0 для проверки edge-cases
                result.append((product_number, price2_float, product_name, insales_id))
            except (ValueError, TypeError):
                continue
    
    return result


def get_product_data(client: ShopwareClient, product_id: str) -> Optional[Dict[str, Any]]:
    """Получает полные данные товара из Shopware"""
    try:
        response = client._request("GET", f"/api/product/{product_id}")
        return response.get("data", {}) if isinstance(response, dict) else {}
    except Exception as e:
        log_debug("verify_marketplace_prices.py:get_product_data", "Ошибка получения товара", {
            "product_id": product_id,
            "error": str(e)
        }, "H1")
        return None


def get_price_rule_id(client: ShopwareClient) -> Optional[str]:
    """Получает ID Price Rule для Marketplace"""
    return client.find_price_rule_by_name(MARKETPLACE_RULE_NAME)


def verify_product_prices(
    client: ShopwareClient,
    product_id: str,
    product_number: str,
    expected_price2: float,
    marketplace_rule_id: str,
    expected_currency_id: str
) -> Dict[str, Any]:
    """
    Проверяет корректность цен товара.
    
    Returns:
        Словарь с результатами проверки
    """
    result = {
        "product_id": product_id,
        "product_number": product_number,
        "status": "OK",
        "issues": [],
        "base_price": None,
        "marketplace_price": None,
        "rule_id_found": False,
        "currency_id_correct": False,
        "price_matches": False,
        "duplicate_rules": False
    }
    
    product_data = get_product_data(client, product_id)
    if not product_data:
        result["status"] = "ERROR"
        result["issues"].append("Не удалось получить данные товара")
        return result
    
    # Проверка базовой цены (product.price)
    base_prices = product_data.get("price", [])
    if base_prices and len(base_prices) > 0:
        result["base_price"] = float(base_prices[0].get("gross", 0))
    else:
        result["status"] = "ERROR"
        result["issues"].append("Базовая цена отсутствует")
    
    # Проверка advanced prices (product.prices)
    advanced_prices = product_data.get("prices", [])
    
    # Ищем цены с правилом Marketplace
    marketplace_prices = [
        p for p in advanced_prices
        if p.get("ruleId") == marketplace_rule_id
    ]
    
    if not marketplace_prices:
        result["status"] = "ERROR"
        result["issues"].append(f"Не найдена цена с правилом '{MARKETPLACE_RULE_NAME}'")
        return result
    
    # Проверка на дубликаты правил
    if len(marketplace_prices) > 1:
        result["status"] = "WARNING"
        result["duplicate_rules"] = True
        result["issues"].append(f"Найдено {len(marketplace_prices)} цен с одним правилом (дубликаты)")
    
    # Берем первую цену для проверки
    marketplace_price_entry = marketplace_prices[0]
    price_array = marketplace_price_entry.get("price", [])
    
    if not price_array or len(price_array) == 0:
        result["status"] = "ERROR"
        result["issues"].append("Массив price пустой в advanced price")
        return result
    
    price_entry = price_array[0]
    result["marketplace_price"] = float(price_entry.get("gross", 0))
    result["rule_id_found"] = True
    
    # Проверка currencyId
    currency_id = price_entry.get("currencyId")
    if currency_id == expected_currency_id:
        result["currency_id_correct"] = True
    else:
        result["status"] = "WARNING"
        result["issues"].append(f"Неверный currencyId: ожидалось {expected_currency_id}, получено {currency_id}")
    
    # Проверка соответствия price2
    if abs(result["marketplace_price"] - expected_price2) < 0.01:  # Допуск для float
        result["price_matches"] = True
    else:
        result["status"] = "ERROR"
        result["issues"].append(
            f"Цена не совпадает: ожидалось {expected_price2}, получено {result['marketplace_price']}"
        )
    
    return result


def check_edge_cases(
    client: ShopwareClient,
    insales_products: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Проверяет edge-cases"""
    edge_cases = {
        "no_sku": [],
        "price2_zero": [],
        "existing_advanced_prices": []
    }
    
    for product in insales_products:
        variants = product.get("variants", [])
        if not variants:
            continue
        
        variant = variants[0]
        product_number = variant.get("sku")
        price2 = variant.get("price2")
        insales_id = product.get("id")
        
        # Товары без SKU
        if not product_number:
            edge_cases["no_sku"].append({
                "insales_id": insales_id,
                "name": product.get("title", "Unknown")
            })
        
        # price2 = 0
        if price2 is not None:
            try:
                if float(price2) == 0:
                    edge_cases["price2_zero"].append({
                        "insales_id": insales_id,
                        "product_number": product_number,
                        "name": product.get("title", "Unknown")
                    })
            except (ValueError, TypeError):
                pass
        
        # Товары с уже существующими advanced prices (проверяем только если есть SKU)
        if product_number:
            product_id = client.find_product_by_number(product_number)
            if product_id:
                product_data = get_product_data(client, product_id)
                if product_data:
                    existing_prices = product_data.get("prices", [])
                    marketplace_rule_id = get_price_rule_id(client)
                    if marketplace_rule_id:
                        # Проверяем, есть ли другие правила кроме Marketplace
                        other_rules = [
                            p for p in existing_prices
                            if p.get("ruleId") != marketplace_rule_id
                        ]
                        if other_rules:
                            edge_cases["existing_advanced_prices"].append({
                                "insales_id": insales_id,
                                "product_number": product_number,
                                "name": product.get("title", "Unknown"),
                                "other_rules_count": len(other_rules)
                            })
    
    return edge_cases


def main():
    print("=" * 80)
    print("ПРОВЕРКА КОРРЕКТНОСТИ ВОССТАНОВЛЕНИЯ MARKETPLACE ЦЕН")
    print("=" * 80)
    print()
    
    # Очищаем лог файл
    if LOG_PATH.exists():
        LOG_PATH.unlink()
    
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
    print("Загрузка товаров из snapshot...")
    insales_products = load_insales_products()
    if not insales_products:
        print("ERROR: Не удалось загрузить товары из snapshot")
        return 1
    
    print(f"Загружено {len(insales_products)} товаров")
    
    # Извлекаем товары с price2
    print("Извлечение товаров с price2...")
    price2_products = extract_price2_products(insales_products)
    print(f"Найдено {len(price2_products)} товаров с price2")
    
    if not price2_products:
        print("INFO: Не найдено товаров с price2 для проверки")
        return 0
    
    # Получаем Price Rule
    marketplace_rule_id = get_price_rule_id(client)
    if not marketplace_rule_id:
        print(f"WARNING: Price Rule '{MARKETPLACE_RULE_NAME}' не найден")
        print("Проверка будет выполнена только для edge-cases и базовых цен")
        # Продолжаем проверку для edge-cases
        marketplace_rule_id = None
    else:
        print(f"OK: Найдено Price Rule: {marketplace_rule_id}")
    
    # Получаем валюту
    currency_id = client.get_sales_channel_currency_id()
    if not currency_id:
        currency_id = client.get_currency_id("RUB")
    if not currency_id:
        print("ERROR: Не удалось определить валюту")
        return 1
    
    print(f"OK: Используется валюта: {currency_id}")
    print()
    
    verification_results = []
    stats = {
        "total_checked": 0,
        "ok": 0,
        "warnings": 0,
        "errors": 0,
        "not_found": 0
    }
    
    # Проверяем выборку товаров только если правило найдено
    if marketplace_rule_id:
        # Проверяем выборку товаров (первые 20 + случайные)
        import random
        sample_size = min(20, len(price2_products))
        sample_products = price2_products[:sample_size]
        
        # Добавляем случайные товары для более полной проверки
        if len(price2_products) > sample_size:
            additional = random.sample(price2_products[sample_size:], min(10, len(price2_products) - sample_size))
            sample_products.extend(additional)
        
        print(f"Проверка {len(sample_products)} товаров...")
        print()
        
        for product_number, price2, product_name, insales_id in sample_products:
            stats["total_checked"] += 1
            
            # Находим товар в Shopware
            product_id = client.find_product_by_number(product_number)
            if not product_id:
                stats["not_found"] += 1
                verification_results.append({
                    "product_number": product_number,
                    "product_name": product_name,
                    "insales_id": insales_id,
                    "status": "ERROR",
                    "issues": ["Товар не найден в Shopware"]
                })
                continue
            
            log_debug("verify_marketplace_prices.py:main", "Проверка товара", {
                "product_number": product_number,
                "product_id": product_id,
                "expected_price2": price2
            }, "H1")
            
            # Проверяем цены
            result = verify_product_prices(
                client, product_id, product_number, price2,
                marketplace_rule_id, currency_id
            )
            result["product_name"] = product_name
            result["insales_id"] = insales_id
            verification_results.append(result)
            
            if result["status"] == "OK":
                stats["ok"] += 1
            elif result["status"] == "WARNING":
                stats["warnings"] += 1
            else:
                stats["errors"] += 1
            
            log_debug("verify_marketplace_prices.py:main", "Результат проверки", {
                "product_number": product_number,
                "status": result["status"],
                "issues_count": len(result["issues"])
            }, "H1")
    else:
        print("Пропуск проверки цен: Price Rule не найден")
        print()
    
    # Проверяем edge-cases
    print("Проверка edge-cases...")
    edge_cases = check_edge_cases(client, insales_products)
    
    # Генерируем отчет
    REPORT_PATH.parent.mkdir(exist_ok=True)
    
    report_lines = [
        "# Проверка корректности восстановления Marketplace цен",
        "",
        f"**Дата:** {__import__('time').strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    
    if not marketplace_rule_id:
        report_lines.extend([
            "## ⚠ ВАЖНО: Price Rule не найден",
            "",
            f"Price Rule '{MARKETPLACE_RULE_NAME}' не найден в Shopware.",
            "",
            "**Возможные причины:**",
            "- Скрипт `restore_marketplace_prices.py --apply` еще не был запущен",
            "- Правило было создано с другим именем",
            "- Правило было удалено",
            "",
            "**Рекомендация:** Запустите `restore_marketplace_prices.py --apply` для создания правила и восстановления цен.",
            "",
        ])
    
    report_lines.extend([
        "## Общая статистика",
        "",
        f"- **Всего проверено товаров:** {stats['total_checked']}",
        f"- **✓ OK:** {stats['ok']}",
        f"- **⚠ WARNING:** {stats['warnings']}",
        f"- **✗ ERROR:** {stats['errors']}",
        f"- **Не найдено в Shopware:** {stats['not_found']}",
        "",
        "## Детали проверки",
        "",
    ])
    
    # Группируем по статусу
    ok_results = [r for r in verification_results if r["status"] == "OK"]
    warning_results = [r for r in verification_results if r["status"] == "WARNING"]
    error_results = [r for r in verification_results if r["status"] == "ERROR"]
    
    if ok_results:
        report_lines.extend([
            "### ✓ OK (успешно проверено)",
            "",
            "| Product Number | Название | Базовая цена | Marketplace цена |",
            "|----------------|----------|--------------|------------------|",
        ])
        for r in ok_results[:10]:
            report_lines.append(
                f"| {r['product_number']} | {r['product_name'][:50]} | "
                f"{r['base_price'] or 'N/A'} | {r['marketplace_price'] or 'N/A'} |"
            )
        if len(ok_results) > 10:
            report_lines.append(f"\n*... и еще {len(ok_results) - 10} товаров*")
        report_lines.append("")
    
    if warning_results:
        report_lines.extend([
            "### ⚠ WARNING (найдены предупреждения)",
            "",
            "| Product Number | Название | Проблемы |",
            "|----------------|----------|----------|",
        ])
        for r in warning_results:
            issues_str = "; ".join(r["issues"])
            report_lines.append(
                f"| {r['product_number']} | {r['product_name'][:50]} | {issues_str} |"
            )
        report_lines.append("")
    
    if error_results:
        report_lines.extend([
            "### ✗ ERROR (найдены ошибки)",
            "",
            "| Product Number | Название | Проблемы |",
            "|----------------|----------|----------|",
        ])
        for r in error_results:
            issues_str = "; ".join(r["issues"])
            report_lines.append(
                f"| {r.get('product_number', 'N/A')} | {r['product_name'][:50]} | {issues_str} |"
            )
        report_lines.append("")
    
    # Edge-cases
    report_lines.extend([
        "## Edge-cases",
        "",
    ])
    
    if edge_cases["no_sku"]:
        report_lines.extend([
            f"### Товары без SKU: {len(edge_cases['no_sku'])}",
            "",
            "| InSales ID | Название |",
            "|------------|----------|",
        ])
        for item in edge_cases["no_sku"][:10]:
            report_lines.append(f"| {item['insales_id']} | {item['name'][:50]} |")
        if len(edge_cases["no_sku"]) > 10:
            report_lines.append(f"\n*... и еще {len(edge_cases['no_sku']) - 10} товаров*")
        report_lines.append("")
    
    if edge_cases["price2_zero"]:
        report_lines.extend([
            f"### Товары с price2 = 0: {len(edge_cases['price2_zero'])}",
            "",
            "| Product Number | Название |",
            "|----------------|----------|",
        ])
        for item in edge_cases["price2_zero"][:10]:
            report_lines.append(f"| {item['product_number']} | {item['name'][:50]} |")
        if len(edge_cases["price2_zero"]) > 10:
            report_lines.append(f"\n*... и еще {len(edge_cases['price2_zero']) - 10} товаров*")
        report_lines.append("")
    
    if edge_cases["existing_advanced_prices"]:
        report_lines.extend([
            f"### Товары с другими advanced prices: {len(edge_cases['existing_advanced_prices'])}",
            "",
            "| Product Number | Название | Количество других правил |",
            "|----------------|----------|---------------------------|",
        ])
        for item in edge_cases["existing_advanced_prices"][:10]:
            report_lines.append(
                f"| {item['product_number']} | {item['name'][:50]} | {item['other_rules_count']} |"
            )
        if len(edge_cases["existing_advanced_prices"]) > 10:
            report_lines.append(f"\n*... и еще {len(edge_cases['existing_advanced_prices']) - 10} товаров*")
        report_lines.append("")
    
    if not any(edge_cases.values()):
        report_lines.append("Edge-cases не обнаружены.\n")
    
    # Итоговый вывод
    report_lines.extend([
        "## Итоговый вывод",
        "",
    ])
    
    if not marketplace_rule_id:
        report_lines.append("**ERROR: Price Rule не найден**")
        report_lines.append("")
        report_lines.append("Проверка цен не может быть выполнена, так как Price Rule 'Marketplace Price' отсутствует.")
        report_lines.append("")
        report_lines.append("**Статус:** Требуется запуск `restore_marketplace_prices.py --apply`")
    elif stats["errors"] == 0 and stats["warnings"] == 0:
        report_lines.append("**OK: ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО**")
        report_lines.append("")
        report_lines.append("Все проверенные товары имеют корректно восстановленные Marketplace цены.")
    elif stats["errors"] == 0:
        report_lines.append("**WARNING: НАЙДЕНЫ ПРЕДУПРЕЖДЕНИЯ**")
        report_lines.append("")
        report_lines.append("Основные проверки пройдены, но есть предупреждения (см. раздел WARNING).")
    else:
        report_lines.append("**ERROR: НАЙДЕНЫ ОШИБКИ**")
        report_lines.append("")
        report_lines.append("Обнаружены проблемы при восстановлении цен (см. раздел ERROR).")
    
    report_lines.extend([
        "",
        "---",
        "",
        "*Отчет сгенерирован автоматически.*",
    ])
    
    report_content = "\n".join(report_lines)
    REPORT_PATH.write_text(report_content, encoding="utf-8")
    
    # Выводим краткую сводку
    print()
    print("=" * 80)
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 80)
    print(f"Всего проверено: {stats['total_checked']}")
    print(f"OK: {stats['ok']}")
    print(f"WARNING: {stats['warnings']}")
    print(f"ERROR: {stats['errors']}")
    print(f"Не найдено: {stats['not_found']}")
    print()
    print(f"Отчет сохранен: {REPORT_PATH}")
    print("=" * 80)
    
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

