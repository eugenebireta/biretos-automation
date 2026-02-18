#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Валидация обновления properties: проверка before / after delete / after update.
"""

import sys
import time
from pathlib import Path
from typing import List, Set

sys.path.insert(0, str(Path(__file__).parent))

from clients.shopware_client import ShopwareClient, ShopwareConfig
from full_import import load_json, find_product_by_number


def main() -> int:
    """Валидация обновления properties."""
    product_number = "500944170"
    
    # Загружаем конфигурацию
    config_path = Path(__file__).parent.parent / "config.json"
    if not config_path.exists():
        print(f"[ERROR] Конфигурация не найдена: {config_path}")
        return 1
    
    config = load_json(config_path)
    
    # Создаем клиент
    shop_cfg = ShopwareConfig(
        url=config["shopware"]["url"],
        access_key_id=config["shopware"]["access_key_id"],
        secret_access_key=config["shopware"]["secret_access_key"],
    )
    client = ShopwareClient(shop_cfg, timeout=10)
    
    print("="*70)
    print("[VALIDATE] Валидация обновления properties")
    print("="*70)
    
    # Находим товар
    product_id = find_product_by_number(client, product_number)
    if not product_id:
        print(f"[ERROR] Товар не найден: {product_number}")
        return 1
    
    print(f"[OK] Товар найден: {product_id}")
    
    # ШАГ 1: Получаем properties BEFORE
    print(f"\n[STEP 1] Properties BEFORE...")
    properties_before = set(client.get_product_properties(product_id))
    print(f"  Properties: {sorted(properties_before) if properties_before else 'пусто'}")
    print(f"  Количество: {len(properties_before)}")
    
    # ШАГ 2: DELETE properties
    print(f"\n[STEP 2] DELETE properties...")
    delete_success = client.delete_product_properties(product_id)
    if not delete_success:
        print(f"[ERROR] Не удалось удалить properties")
        return 1
    
    time.sleep(0.3)
    
    # ШАГ 3: Получаем properties AFTER DELETE
    print(f"\n[STEP 3] Properties AFTER DELETE...")
    properties_after_delete = set(client.get_product_properties(product_id))
    print(f"  Properties: {sorted(properties_after_delete) if properties_after_delete else 'пусто'}")
    print(f"  Количество: {len(properties_after_delete)}")
    
    if properties_after_delete:
        print(f"[ERROR] Properties НЕ пустые после DELETE!")
        print(f"  Осталось: {sorted(properties_after_delete)}")
        return 1
    
    # ШАГ 4: UPDATE properties (используем те же, что были до удаления, для проверки)
    print(f"\n[STEP 4] UPDATE properties...")
    if properties_before:
        # Используем первые 2 properties для теста (если есть)
        test_properties = list(properties_before)[:2]
        print(f"  Устанавливаем: {sorted(test_properties)}")
        
        update_success = client.update_product_properties(
            product_id=product_id,
            property_option_ids=test_properties
        )
        
        if not update_success:
            print(f"[ERROR] Не удалось обновить properties")
            return 1
        
        time.sleep(0.3)
        
        # ШАГ 5: Получаем properties AFTER UPDATE
        print(f"\n[STEP 5] Properties AFTER UPDATE...")
        properties_after_update = set(client.get_product_properties(product_id))
        print(f"  Properties: {sorted(properties_after_update) if properties_after_update else 'пусто'}")
        print(f"  Количество: {len(properties_after_update)}")
        print(f"  Ожидалось: {sorted(test_properties)}")
        
        if properties_after_update != set(test_properties):
            print(f"[ERROR] Properties НЕ совпадают после UPDATE!")
            print(f"  Ожидалось: {sorted(test_properties)}")
            print(f"  Получено: {sorted(properties_after_update)}")
            missing = set(test_properties) - properties_after_update
            extra = properties_after_update - set(test_properties)
            if missing:
                print(f"  Отсутствуют: {sorted(missing)}")
            if extra:
                print(f"  Лишние: {sorted(extra)}")
            return 1
        
        print(f"[OK] Properties совпадают после UPDATE")
    else:
        print(f"[INFO] Нет properties для теста UPDATE")
    
    # Финальный вывод
    print("\n" + "="*70)
    print("[RESULT]")
    print("="*70)
    print(f"[OK] Properties BEFORE: {len(properties_before)} ({sorted(properties_before) if properties_before else 'пусто'})")
    print(f"[OK] Properties AFTER DELETE: {len(properties_after_delete)} (пусто)")
    if properties_before:
        print(f"[OK] Properties AFTER UPDATE: {len(properties_after_update)} ({sorted(properties_after_update)})")
        print(f"[OK] Валидация пройдена: properties заменяются полностью")
    else:
        print(f"[OK] Валидация пройдена: DELETE работает корректно")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())




