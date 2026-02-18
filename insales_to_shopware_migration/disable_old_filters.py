"""
Отключение фильтров у старых Property Groups в Shopware 6.

Скрипт находит Property Groups с filterable=true, которые имеют дубликаты
с filterable=false, и отключает фильтры у старых групп.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent / "src"))

from clients import ShopwareClient, ShopwareConfig, ShopwareClientError


def normalize_name(name: str) -> str:
    """Нормализует имя для сравнения (lowercase + strip)."""
    return (name or "").lower().strip()


def get_all_property_groups(client: ShopwareClient) -> List[Dict[str, Any]]:
    """Получает все Property Groups из Shopware."""
    all_groups = []
    limit = 100
    page = 1
    
    while True:
        response = client._request(
            "POST",
            "/api/search/property-group",
            json={
                "limit": limit,
                "page": page,
                "includes": {
                    "property_group": [
                        "id",
                        "name",
                        "filterable"
                    ]
                }
            }
        )
        
        if not isinstance(response, dict):
            break
            
        data = response.get("data", [])
        if not data:
            break
            
        all_groups.extend(data)
        
        total = response.get("total", 0)
        if len(all_groups) >= total:
            break
            
        page += 1
    
    return all_groups


def find_groups_to_disable(groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Находит Property Groups, у которых нужно отключить filterable.
    
    Логика:
    - Группирует группы по нормализованному имени
    - Если есть дубликаты и хотя бы один с filterable=false:
      → отключает filterable у всех с filterable=true
    """
    groups_by_name: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    
    for group in groups:
        name = group.get("name", "")
        normalized = normalize_name(name)
        if normalized:
            groups_by_name[normalized].append(group)
    
    groups_to_disable = []
    
    for normalized_name, group_list in groups_by_name.items():
        if len(group_list) <= 1:
            # Нет дубликатов, пропускаем
            continue
        
        # Проверяем, есть ли хотя бы одна группа с filterable=false
        has_non_filterable = any(
            g.get("filterable") is False
            for g in group_list
        )
        
        if not has_non_filterable:
            # Все группы с filterable=true, пропускаем (безопаснее не трогать)
            continue
        
        # Находим все группы с filterable=true, которые нужно отключить
        for group in group_list:
            if group.get("filterable") is True:
                groups_to_disable.append({
                    "id": group.get("id"),
                    "name": group.get("name"),
                    "normalizedName": normalized_name,
                    "reason": "Дубликат с filterable=false существует"
                })
    
    return groups_to_disable


def disable_filterable(client: ShopwareClient, group_id: str, dry_run: bool = False) -> bool:
    """Отключает filterable у Property Group."""
    if dry_run:
        return True
    
    try:
        client._request(
            "PATCH",
            f"/api/property-group/{group_id}",
            json={"filterable": False}
        )
        return True
    except ShopwareClientError as e:
        print(f"   ERROR: Не удалось отключить filterable для группы {group_id}: {e}")
        return False


def reindex(client: ShopwareClient, dry_run: bool = False) -> bool:
    """Выполняет переиндексацию Shopware."""
    if dry_run:
        print("   [DRY-RUN] Пропущена переиндексация")
        return True
    
    try:
        print("   Выполнение переиндексации...")
        client._request("POST", "/api/_action/index")
        print("   Переиндексация завершена")
        return True
    except ShopwareClientError as e:
        print(f"   ERROR: Не удалось выполнить переиндексацию: {e}")
        return False


def main():
    """Основная функция."""
    parser = argparse.ArgumentParser(
        description="Отключение фильтров у старых Property Groups"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Режим проверки без применения изменений"
    )
    parser.add_argument(
        "--skip-reindex",
        action="store_true",
        help="Пропустить переиндексацию после изменений"
    )
    
    args = parser.parse_args()
    
    # Загружаем конфигурацию
    config_path = Path(__file__).parent / "config.json"
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)
    
    with config_path.open("r", encoding="utf-8") as f:
        config_data = json.load(f)
    
    shopware_config = config_data.get("shopware", {})
    client = ShopwareClient(
        ShopwareConfig(
            url=shopware_config["url"],
            access_key_id=shopware_config["access_key_id"],
            secret_access_key=shopware_config["secret_access_key"]
        )
    )
    
    print("=" * 80)
    print("ОТКЛЮЧЕНИЕ ФИЛЬТРОВ У СТАРЫХ PROPERTY GROUPS")
    if args.dry_run:
        print("РЕЖИМ: DRY-RUN (изменения не применяются)")
    print("=" * 80)
    print()
    
    # 1. Получаем все Property Groups
    print("[1/3] Получение всех Property Groups...")
    all_groups = get_all_property_groups(client)
    print(f"   Найдено Property Groups: {len(all_groups)}")
    
    # 2. Находим группы для отключения
    print("\n[2/3] Поиск групп для отключения фильтров...")
    groups_to_disable = find_groups_to_disable(all_groups)
    print(f"   Найдено групп для отключения: {len(groups_to_disable)}")
    
    if not groups_to_disable:
        print("\n   Нет групп для отключения. Всё в порядке!")
        return
    
    # Показываем детали
    print("\n   Группы, которые будут отключены:")
    for i, group in enumerate(groups_to_disable[:10], 1):
        print(f"     {i}. {group['name']} (ID: {group['id']})")
    if len(groups_to_disable) > 10:
        print(f"     ... и ещё {len(groups_to_disable) - 10} групп")
    
    # 3. Отключаем фильтры
    print(f"\n[3/3] Отключение filterable у {len(groups_to_disable)} групп...")
    if args.dry_run:
        print("   [DRY-RUN] Изменения не применяются")
    else:
        print("   Применение изменений...")
    
    success_count = 0
    failed_count = 0
    operations_log = []
    
    for group in groups_to_disable:
        success = disable_filterable(client, group["id"], dry_run=args.dry_run)
        if success:
            success_count += 1
            if not args.dry_run:
                print(f"   ✓ Отключено: {group['name']}")
        else:
            failed_count += 1
            print(f"   ✗ Ошибка: {group['name']}")
        
        operations_log.append({
            "groupId": group["id"],
            "name": group["name"],
            "success": success
        })
    
    print(f"\n   Результат: {success_count} успешно, {failed_count} ошибок")
    
    # 4. Переиндексация
    if not args.skip_reindex and success_count > 0:
        print("\n[4/4] Переиндексация Shopware...")
        reindex(client, dry_run=args.dry_run)
    
    # Сохранение лога операций
    log_path = Path(__file__).parent / "disable_filters_log.json"
    log_data = {
        "dryRun": args.dry_run,
        "totalGroups": len(groups_to_disable),
        "successCount": success_count,
        "failedCount": failed_count,
        "operations": operations_log
    }
    
    with log_path.open("w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    
    print(f"\nЛог операций сохранён: {log_path}")
    print("\n" + "=" * 80)
    print("ОТКЛЮЧЕНИЕ ФИЛЬТРОВ ЗАВЕРШЕНО")
    print("=" * 80)


if __name__ == "__main__":
    main()




