"""
Валидация результатов пробного импорта 10 товаров.
Запускает verify_product_state.py для каждого SKU и собирает результаты.
"""
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from import_utils import ROOT

REPORTS_DIR = ROOT / "_reports"
SELECTED_PRODUCTS_FILE = REPORTS_DIR / "selected_products_10.txt"
REPORT_SUFFIX = ""  # Может быть "_repeat" для повторного импорта


def load_selected_skus() -> List[str]:
    """Загружает список отобранных SKU."""
    if not SELECTED_PRODUCTS_FILE.exists():
        print(f"[ERROR] Файл со списком SKU не найден: {SELECTED_PRODUCTS_FILE}")
        return []
    
    skus = []
    with SELECTED_PRODUCTS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            sku = line.strip()
            if sku:
                skus.append(sku)
    
    return skus


def run_verify_product_state(sku: str) -> Dict[str, Any]:
    """Запускает verify_product_state.py для одного SKU и парсит результат."""
    script_path = ROOT / "src" / "verify_product_state.py"
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), sku],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30
        )
        
        output = result.stdout + result.stderr
        
        # Парсим результат
        result_data = {
            "sku": sku,
            "success": result.returncode == 0,
            "output": output,
            "manufacturer": "N/A",
            "categories_count": 0,
            "result": "FAIL",
            "reason": "Не удалось распарсить результат",
            "checklist": {}
        }
        
        # Извлекаем данные из вывода
        lines = output.split("\n")
        
        # Ищем manufacturer (ищем строку "Name: Boeing" в секции MANUFACTURER)
        in_manufacturer_section = False
        for line in lines:
            if "1) MANUFACTURER" in line or "MANUFACTURER" in line and "---" in lines[max(0, lines.index(line)-1):lines.index(line)+2]:
                in_manufacturer_section = True
                continue
            if in_manufacturer_section and "Name:" in line:
                parts = line.split("Name:")
                if len(parts) > 1:
                    result_data["manufacturer"] = parts[1].strip()
                    break
        
        # Ищем количество категорий
        for line in lines:
            if "Всего категорий:" in line or "категорий:" in line.lower():
                # Ищем число после "категорий:"
                import re
                match = re.search(r'категорий:\s*(\d+)', line, re.IGNORECASE)
                if match:
                    try:
                        result_data["categories_count"] = int(match.group(1))
                    except:
                        pass
                # Fallback: парсим вручную
                if result_data["categories_count"] == 0:
                    parts = line.split(":")
                    if len(parts) > 1:
                        try:
                            num_str = parts[1].strip().split()[0]
                            result_data["categories_count"] = int(num_str)
                        except:
                            pass
                break
        
        # Ищем детальный чеклист (ищем строки вида "1  | manufacturerNumber | RELAXED | [OK]")
        # Новая структура таблицы: № | Параметр | Режим | Статус
        checklist_items = {}
        for line in lines:
            # Ищем строки таблицы с паттерном "| [OK]" или "| [FAIL]"
            if "|" in line and ("[OK]" in line or "[FAIL]" in line or "[WARN]" in line):
                # Пропускаем заголовки
                if "Параметр" in line or "№" in line or "---" in line or "Режим" in line:
                    continue
                try:
                    parts = [p.strip() for p in line.split("|")]
                    # Новая структура: № | Параметр | Режим | Статус (4 части)
                    # Старая структура: № | Параметр | Статус (3 части) - для обратной совместимости
                    if len(parts) >= 3:
                        # Проверяем, что первая часть - число
                        first_part = parts[0].strip()
                        if first_part and (first_part.isdigit() or (first_part and first_part[0].isdigit())):
                            # Определяем структуру: если 4 части, то новая структура с Режим
                            if len(parts) >= 4:
                                item_name = parts[1].strip()
                                item_status = parts[3].strip()  # Статус в 4-й колонке
                            else:
                                item_name = parts[1].strip()
                                item_status = parts[2].strip()  # Статус в 3-й колонке
                            
                            # Убираем пометки режимов из названия (RELAXED/STRICT)
                            item_name = item_name.replace(" (RELAXED)", "").replace(" (STRICT)", "").strip()
                            
                            # Извлекаем статус
                            if "[OK]" in item_status:
                                checklist_items[item_name] = "OK"
                            elif "[FAIL]" in item_status:
                                checklist_items[item_name] = "FAIL"
                            elif "[WARN]" in item_status:
                                checklist_items[item_name] = "WARN"
                except Exception:
                    pass
        
        result_data["checklist"] = checklist_items
        
        # Определяем общий результат
        # Проверяем все 8 пунктов: 6 STRICT + 2 RELAXED
        # STRICT: ean, Tax, Visibilities, Categories, Marketplace price, Stock & Status
        # RELAXED: manufacturerNumber, customFields.internal_barcode, Manufacturer
        critical_items = {
            "manufacturerNumber": checklist_items.get("manufacturerNumber", "FAIL"),
            "ean (GTIN/EAN)": checklist_items.get("ean (GTIN/EAN)", "FAIL"),
            "customFields.internal_barcode": checklist_items.get("customFields.internal_barcode", "FAIL"),
            "Tax": checklist_items.get("Tax", "FAIL"),
            "Visibilities": checklist_items.get("Visibilities", "FAIL"),
            "Categories": checklist_items.get("Categories", "FAIL"),
            "Marketplace price": checklist_items.get("Marketplace price", "FAIL"),
            "Manufacturer": checklist_items.get("Manufacturer", "FAIL"),
        }
        
        ok_count = sum(1 for status in checklist_items.values() if status == "OK")
        critical_ok_count = sum(1 for status in critical_items.values() if status == "OK")
        total_count = len(checklist_items)
        
        # Результат OK, если все критические пункты OK (8/8: 6 STRICT + 2 RELAXED)
        if critical_ok_count == 8 and total_count >= 8:
            result_data["result"] = "OK"
            result_data["reason"] = f"8/8 критических OK (6 STRICT + 2 RELAXED)"
        elif ok_count == 8 and total_count == 8:
            result_data["result"] = "OK"
            result_data["reason"] = "8/8 OK"
        else:
            result_data["result"] = "FAIL"
            failed_critical = [name for name, status in critical_items.items() if status != "OK"]
            if failed_critical:
                result_data["reason"] = f"{critical_ok_count}/8 критических OK. FAIL: {', '.join(failed_critical[:3])}"
            else:
                failed_items = [name for name, status in checklist_items.items() if status != "OK"]
                result_data["reason"] = f"{ok_count}/8 OK. FAIL: {', '.join(failed_items[:3])}"
        
        # Ищем manufacturer из детального вывода
        for line in lines:
            if "Manufacturer:" in line and "Name:" in line:
                parts = line.split("Name:")
                if len(parts) > 1:
                    result_data["manufacturer"] = parts[1].strip()
                    break
        
        return result_data
        
    except subprocess.TimeoutExpired:
        return {
            "sku": sku,
            "success": False,
            "output": "Timeout",
            "manufacturer": "N/A",
            "categories_count": 0,
            "result": "FAIL",
            "reason": "Timeout при проверке",
            "checklist": {}
        }
    except Exception as e:
        return {
            "sku": sku,
            "success": False,
            "output": str(e),
            "manufacturer": "N/A",
            "categories_count": 0,
            "result": "FAIL",
            "reason": f"Ошибка: {str(e)}",
            "checklist": {}
        }


def main():
    print("=" * 80)
    print("ВАЛИДАЦИЯ РЕЗУЛЬТАТОВ ПРОБНОГО ИМПОРТА")
    print("=" * 80)
    print()
    
    # Загружаем список SKU
    print("1) Загрузка списка SKU...")
    skus = load_selected_skus()
    if not skus:
        print("[ERROR] Не удалось загрузить список SKU")
        return 1
    
    print(f"   [OK] Загружено SKU: {len(skus)}")
    print()
    
    # Валидируем каждый товар
    print("2) Валидация товаров...")
    print("-" * 80)
    
    results = []
    for i, sku in enumerate(skus, 1):
        print(f"   [{i}/{len(skus)}] Проверка SKU: {sku}...", end=" ", flush=True)
        result = run_verify_product_state(sku)
        results.append(result)
        
        status_icon = "[OK]" if result["result"] == "OK" else "[FAIL]"
        print(f"{status_icon} {result['result']}")
    
    print()
    print("=" * 80)
    print("РЕЗУЛЬТАТЫ ВАЛИДАЦИИ")
    print("=" * 80)
    print()
    
    # Подсчитываем статистику
    ok_count = sum(1 for r in results if r["result"] == "OK")
    fail_count = len(results) - ok_count
    
    print(f"Всего товаров: {len(results)}")
    print(f"OK: {ok_count}")
    print(f"FAIL: {fail_count}")
    print()
    
    # Выводим таблицу
    print("Таблица результатов:")
    print("-" * 80)
    print(f"{'SKU':<15} | {'Manufacturer':<20} | {'Categories':<10} | {'Result':<6} | {'Reason'}")
    print("-" * 80)
    
    for result in results:
        sku = result["sku"]
        manufacturer = result["manufacturer"][:20]
        categories = str(result["categories_count"])
        result_status = result["result"]
        reason = result["reason"][:40]
        print(f"{sku:<15} | {manufacturer:<20} | {categories:<10} | {result_status:<6} | {reason}")
    
    print()
    
    # Сохраняем результаты в JSON
    json_file = REPORTS_DIR / f"batch_import_10{REPORT_SUFFIX}.json"
    with json_file.open("w", encoding="utf-8") as f:
        json.dump({
            "total": len(results),
            "ok": ok_count,
            "fail": fail_count,
            "results": results
        }, f, ensure_ascii=False, indent=2)
    
    print(f"[OK] JSON отчёт сохранен: {json_file}")
    
    # Создаём Markdown отчёт
    md_file = REPORTS_DIR / f"batch_import_10{REPORT_SUFFIX}.md"
    with md_file.open("w", encoding="utf-8") as f:
        f.write("# Отчёт о пробном импорте 10 товаров\n\n")
        f.write(f"**Дата:** {Path(__file__).stat().st_mtime}\n\n")
        f.write(f"**Всего товаров:** {len(results)}\n")
        f.write(f"**OK:** {ok_count}\n")
        f.write(f"**FAIL:** {fail_count}\n\n")
        
        f.write("## Таблица результатов\n\n")
        f.write("| SKU | Manufacturer | Categories | Result | Reason |\n")
        f.write("|-----|-------------|------------|--------|--------|\n")
        
        for result in results:
            f.write(f"| {result['sku']} | {result['manufacturer']} | {result['categories_count']} | "
                   f"{result['result']} | {result['reason']} |\n")
        
        f.write("\n## Детальные результаты\n\n")
        for result in results:
            f.write(f"### SKU: {result['sku']}\n\n")
            f.write(f"- **Manufacturer:** {result['manufacturer']}\n")
            f.write(f"- **Categories:** {result['categories_count']}\n")
            f.write(f"- **Result:** {result['result']}\n")
            f.write(f"- **Reason:** {result['reason']}\n\n")
            f.write("**Checklist:**\n")
            for item, status in result['checklist'].items():
                f.write(f"- {item}: {status}\n")
            f.write("\n")
    
    print(f"[OK] Markdown отчёт сохранен: {md_file}")
    print()
    
    # Вывод GO/NO-GO
    print("=" * 80)
    if ok_count >= 9:
        print("РЕЗУЛЬТАТ: [GO] - готовность к массовому импорту подтверждена")
    else:
        print("РЕЗУЛЬТАТ: [NO-GO] - требуется исправление проблем")
        # Проверяем, есть ли проблема с Marketplace price
        marketplace_price_fails = sum(1 for r in results if r.get("checklist", {}).get("Marketplace price") == "FAIL")
        if marketplace_price_fails > 0:
            print(f"ПРОБЛЕМА: {marketplace_price_fails} товаров с дублями Marketplace price")
            print("ИСПРАВЛЕНИЕ: Логика удаления старых prices применена в full_import.py")
            print("ДЕЙСТВИЕ: Повторить импорт 10 товаров для проверки исправления")
    print("=" * 80)
    
    return 0 if ok_count >= 9 else 1


if __name__ == "__main__":
    sys.exit(main())
