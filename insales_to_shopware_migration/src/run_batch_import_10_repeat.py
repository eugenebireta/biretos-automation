"""
Повторный импорт тех же 10 товаров после исправления логики Marketplace price.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from run_batch_import_10 import main as run_import_main
from validate_batch_import import main as validate_main

# Те же 10 SKU
TEST_SKUS = [
    "500944170", "500944178", "500944207", "500944220",
    "500944223", "500944234", "500944237", "500944238",
    "500944241", "500944256"
]

if __name__ == "__main__":
    print("=" * 80)
    print("ПОВТОРНЫЙ ИМПОРТ 10 ТОВАРОВ (после исправления Marketplace price)")
    print("=" * 80)
    print()
    print(f"SKU для импорта: {', '.join(TEST_SKUS)}")
    print()
    
    # Сохраняем список SKU для валидации
    from import_utils import ROOT
    REPORTS_DIR = ROOT / "_reports"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    selected_file = REPORTS_DIR / "selected_products_10.txt"
    with selected_file.open("w", encoding="utf-8") as f:
        for sku in TEST_SKUS:
            f.write(f"{sku}\n")
    
    print(f"[OK] Список SKU сохранен: {selected_file}")
    print()
    
    # Запускаем импорт
    print("=" * 80)
    print("ШАГ 1: ИМПОРТ ТОВАРОВ")
    print("=" * 80)
    print()
    
    import_result = run_import_main()
    
    if import_result != 0:
        print()
        print("[WARNING] Импорт завершен с ошибками, но продолжаем валидацию...")
        print()
    
    # Запускаем валидацию
    print("=" * 80)
    print("ШАГ 2: ВАЛИДАЦИЯ РЕЗУЛЬТАТОВ")
    print("=" * 80)
    print()
    
    # Устанавливаем суффикс для отчётов
    import validate_batch_import
    validate_batch_import.REPORT_SUFFIX = "_repeat"
    
    validate_result = validate_main()
    
    print()
    print("=" * 80)
    if validate_result == 0:
        print("РЕЗУЛЬТАТ: [GO] - готовность к массовому импорту подтверждена")
    else:
        print("РЕЗУЛЬТАТ: [NO-GO] - требуется дополнительное исправление")
    print("=" * 80)
    
    sys.exit(validate_result)

