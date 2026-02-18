"""
Запуск пробного импорта 10 товаров.
Использует full_import.py с фильтрацией по отобранным SKU.
"""
import subprocess
import sys
from pathlib import Path

from import_utils import ROOT

REPORTS_DIR = ROOT / "_reports"
SELECTED_PRODUCTS_FILE = REPORTS_DIR / "selected_products_10.txt"
FULL_IMPORT_SCRIPT = ROOT / "src" / "full_import.py"


def load_selected_skus() -> list[str]:
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


def main():
    print("=" * 80)
    print("ПРОБНЫЙ ИМПОРТ 10 ТОВАРОВ")
    print("=" * 80)
    print()
    
    # Загружаем список SKU
    print("1) Загрузка списка SKU...")
    skus = load_selected_skus()
    if not skus:
        print("[ERROR] Не удалось загрузить список SKU")
        return 1
    
    print(f"   [OK] Загружено SKU: {len(skus)}")
    print(f"   SKU: {', '.join(skus)}")
    print()
    
    # Запускаем импорт для каждого SKU в режиме single-sku
    # Это обеспечит полный контроль и логирование
    print("2) Запуск импорта товаров...")
    print("-" * 80)
    
    success_count = 0
    fail_count = 0
    
    for i, sku in enumerate(skus, 1):
        print(f"   [{i}/{len(skus)}] Импорт SKU: {sku}...", end=" ", flush=True)
        
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
                success_count += 1
            else:
                print(f"[FAIL] (code: {result.returncode})")
                fail_count += 1
                # Выводим первые строки ошибки
                error_lines = result.stderr.split("\n")[:3]
                for line in error_lines:
                    if line.strip():
                        print(f"      {line[:60]}")
        
        except subprocess.TimeoutExpired:
            print("[TIMEOUT]")
            fail_count += 1
        except Exception as e:
            print(f"[ERROR]: {str(e)[:40]}")
            fail_count += 1
    
    print()
    print("=" * 80)
    print("РЕЗУЛЬТАТЫ ИМПОРТА")
    print("=" * 80)
    print(f"Успешно: {success_count}")
    print(f"Ошибок: {fail_count}")
    print()
    
    if success_count >= 9:
        print("[OK] Импорт завершен успешно (>=9/10)")
        return 0
    else:
        print("[FAIL] Импорт завершен с ошибками (<9/10)")
        return 1


if __name__ == "__main__":
    sys.exit(main())

