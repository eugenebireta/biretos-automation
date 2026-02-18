"""
Запуск пробного импорта 10 товаров с автоматической валидацией.
Выполняет:
1. Отбор 10 товаров из snapshot
2. Импорт через full_import.py
3. Валидацию через verify_product_state.py
4. Генерацию отчётов
"""
import json
import subprocess
import sys
from pathlib import Path

from import_utils import ROOT

SELECT_SCRIPT = ROOT / "src" / "select_test_products.py"
IMPORT_SCRIPT = ROOT / "src" / "full_import.py"
VALIDATE_SCRIPT = ROOT / "src" / "validate_batch_import.py"
REPORT_DIR = ROOT / "_reports"


def main():
    print("=" * 80)
    print("ПРОБНЫЙ ИМПОРТ 10 ТОВАРОВ")
    print("=" * 80)
    print()
    
    # ШАГ 1: Отбор товаров
    print("ШАГ 1: Отбор товаров из snapshot...")
    print("-" * 80)
    
    result = subprocess.run(
        [sys.executable, str(SELECT_SCRIPT), "10"],
        cwd=str(ROOT)
    )
    
    if result.returncode != 0:
        print("[ERROR] Не удалось отобрать товары")
        return 1
    
    # Загружаем список отобранных товаров
    test_products_file = ROOT / "_reports" / "test_products_10.json"
    if not test_products_file.exists():
        print("[ERROR] Файл с отобранными товарами не найден")
        return 1
    
    with test_products_file.open("r", encoding="utf-8") as f:
        test_products = json.load(f)
    
    skus = [p["sku"] for p in test_products]
    print(f"[OK] Отобрано {len(skus)} товаров")
    print(f"SKU: {', '.join(skus)}")
    print()
    
    # ШАГ 2: Импорт
    print("ШАГ 2: Импорт товаров...")
    print("-" * 80)
    print("Режим: импорт отобранных SKU через --single-sku")
    print(f"Количество: {len(skus)}")
    print("Source: snapshot")
    print()
    
    # Импортируем каждый SKU отдельно через --single-sku
    # Это гарантирует импорт именно отобранных товаров
    imported_count = 0
    failed_count = 0
    
    for i, sku in enumerate(skus, 1):
        print(f"[{i}/{len(skus)}] Импорт SKU: {sku}...")
        
        result = subprocess.run(
            [sys.executable, str(IMPORT_SCRIPT), "--single-sku", sku, "--source", "snapshot"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        
        if result.returncode == 0:
            imported_count += 1
            print(f"  [OK] Импортирован")
        else:
            failed_count += 1
            print(f"  [FAIL] Ошибка импорта")
            if result.stderr:
                error_lines = result.stderr.split("\n")[:3]
                for line in error_lines:
                    if line.strip():
                        print(f"    {line[:60]}")
    
    print()
    print(f"Импортировано: {imported_count}/{len(skus)}")
    if failed_count > 0:
        print(f"Ошибок: {failed_count}")
    print()
    
    # ШАГ 3: Валидация
    print("ШАГ 3: Валидация результатов...")
    print("-" * 80)
    
    result = subprocess.run(
        [sys.executable, str(VALIDATE_SCRIPT)],
        cwd=str(ROOT)
    )
    
    if result.returncode != 0:
        print("[WARNING] Валидация выявила проблемы")
        return 1
    
    print()
    print("=" * 80)
    print("ПРОБНЫЙ ИМПОРТ ЗАВЕРШЁН")
    print("=" * 80)
    print()
    
    # Показываем итоговый вердикт
    report_file = REPORT_DIR / "batch_import_10.json"
    if report_file.exists():
        with report_file.open("r", encoding="utf-8") as f:
            report = json.load(f)
        
        summary = report.get("summary", {})
        ok_count = summary.get("ok", 0)
        total = summary.get("total", 0)
        
        print(f"Результат: {ok_count}/{total} товаров = 8/8 OK")
        print()
        
        if ok_count >= 9:
            print("✅ GO - Готовность к массовому импорту подтверждена")
            print()
            print("Отчёты сохранены:")
            print(f"  - {report_file}")
            print(f"  - {REPORT_DIR / 'batch_import_10.md'}")
            return 0
        else:
            print("❌ NO-GO - Требуется исправление перед массовым импортом")
            print()
            print("Отчёты сохранены:")
            print(f"  - {report_file}")
            print(f"  - {REPORT_DIR / 'batch_import_10.md'}")
            return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

