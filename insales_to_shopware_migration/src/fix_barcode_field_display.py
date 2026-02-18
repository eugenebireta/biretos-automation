#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Исправление отображения custom field internal_barcode в Shopware Admin.

Выполняет:
1. Находит custom field internal_barcode
2. Находит его custom field set
3. Добавляет relation к entity 'product' если отсутствует
4. Убеждается что set active = true
5. Устанавливает customFieldPosition = 10
6. Очищает кеш админки
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any

sys.path.insert(0, str(Path(__file__).parent))

from clients.shopware_client import ShopwareClient, ShopwareConfig

def load_json(path: Path) -> dict:
    """Загружает JSON файл."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def find_custom_field(client: ShopwareClient) -> Optional[Dict[str, Any]]:
    """Находит custom field internal_barcode."""
    print("\n[ШАГ 1] Поиск custom field 'internal_barcode'...")
    
    try:
        search_response = client._request(
            "POST",
            "/api/search/custom-field",
            json={
                "filter": [
                    {"field": "name", "type": "equals", "value": "internal_barcode"}
                ],
                "limit": 1
            }
        )
        
        if not isinstance(search_response, dict):
            print("[ERROR] Неожиданный формат ответа Search API")
            return None
        
        data = search_response.get("data", [])
        if not data or len(data) == 0:
            print("[FAIL] Custom field 'internal_barcode' НЕ НАЙДЕН")
            return None
        
        custom_field = data[0]
        custom_field_id = custom_field.get("id")
        custom_field_attrs = custom_field.get("attributes", {})
        
        print(f"[OK] Custom field найден:")
        print(f"  - ID: {custom_field_id}")
        print(f"  - Name: {custom_field_attrs.get('name')}")
        print(f"  - Type: {custom_field_attrs.get('type')}")
        
        # Получаем полную информацию
        try:
            full_response = client._request("GET", f"/api/custom-field/{custom_field_id}")
            full_data = full_response.get("data", {}) if isinstance(full_response, dict) else {}
            return {
                "id": custom_field_id,
                "attributes": full_data.get("attributes", custom_field_attrs),
                "data": full_data
            }
        except Exception as e:
            print(f"[WARNING] Не удалось получить полную информацию: {e}")
            return {
                "id": custom_field_id,
                "attributes": custom_field_attrs,
                "data": custom_field
            }
            
    except Exception as e:
        print(f"[ERROR] Ошибка поиска custom field: {e}")
        import traceback
        traceback.print_exc()
        return None

def create_minimal_product_set(client: ShopwareClient, custom_field_id: str) -> Optional[Dict[str, Any]]:
    """Создает минимальный custom field set для product, если set-ов вообще нет."""
    print("\n[INFO] Создание минимального custom field set для product...")
    
    try:
        import uuid
        set_id = str(uuid.uuid4().hex)
        
        # Создаем set
        set_payload = {
            "id": set_id,
            "name": "product_custom_fields",
            "active": True,
            "config": {
                "label": {
                    "ru-RU": "Дополнительные поля товара"
                }
            }
        }
        
        client._request("POST", "/api/custom-field-set", json=set_payload)
        print(f"[OK] Custom field set создан (ID: {set_id})")
        
        # Добавляем поле в set
        # В Shopware связь между set и field устанавливается через поле customFieldSetId в custom field
        try:
            # Обновляем custom field, добавляя customFieldSetId
            client._request("PATCH", f"/api/custom-field/{custom_field_id}", json={
                "customFieldSetId": set_id
            })
            print(f"[OK] Поле добавлено в set")
        except Exception as e:
            print(f"[WARNING] Не удалось добавить поле через PATCH: {e}")
            # Пробуем через associations
            try:
                client._request("PATCH", f"/api/custom-field-set/{set_id}", json={
                    "customFields": [{"id": custom_field_id}]
                })
                print(f"[OK] Поле добавлено в set через associations")
            except Exception as e2:
                print(f"[WARNING] Не удалось добавить поле через associations: {e2}")
        
        # Добавляем relation к product
        relation_id = str(uuid.uuid4().hex)
        relation_payload = {
            "id": relation_id,
            "customFieldSetId": set_id,
            "entityName": "product"
        }
        client._request("POST", "/api/custom-field-set-relation", json=relation_payload)
        print(f"[OK] Relation к entity 'product' добавлен")
        
        return {
            "id": set_id,
            "name": "product_custom_fields",
            "active": True,
            "attributes": set_payload.get("config", {})
        }
        
    except Exception as e:
        print(f"[ERROR] Ошибка создания set: {e}")
        import traceback
        traceback.print_exc()
        return None

def find_custom_field_set(client: ShopwareClient, custom_field_id: str) -> Optional[Dict[str, Any]]:
    """Находит custom field set, содержащий internal_barcode."""
    print("\n[ШАГ 2] Поиск custom field set...")
    
    try:
        # Метод 1: Получаем все custom field sets через GET
        print("[INFO] Получаем все custom field sets...")
        try:
            all_sets_response = client._request("GET", "/api/custom-field-set")
            all_sets = all_sets_response.get("data", []) if isinstance(all_sets_response, dict) else []
            print(f"[INFO] Найдено sets: {len(all_sets)}")
        except Exception as e:
            print(f"[WARNING] Ошибка GET запроса: {e}")
            all_sets = []
        
        target_set = None
        
        # Проверяем каждый set
        for cfs in all_sets:
            cfs_id = cfs.get("id")
            if not cfs_id:
                continue
                
            try:
                # Получаем детали set-а с customFields
                print(f"[INFO] Проверяем set {cfs_id}...")
                set_detail = client._request(
                    "GET",
                    f"/api/custom-field-set/{cfs_id}?associations[customFields]=true"
                )
                set_data = set_detail.get("data", {}) if isinstance(set_detail, dict) else {}
                set_attributes = set_data.get("attributes", {})
                
                # Проверяем customFields в relationships
                relationships = set_data.get("relationships", {})
                custom_fields_rel = relationships.get("customFields", {})
                custom_fields_data = custom_fields_rel.get("data", [])
                
                # Проверяем, есть ли наше поле
                for cf_rel in custom_fields_data:
                    if cf_rel.get("id") == custom_field_id:
                        target_set = {
                            "id": cfs_id,
                            "name": set_attributes.get("name"),
                            "active": set_attributes.get("active", False),
                            "attributes": set_attributes
                        }
                        print(f"[OK] Поле найдено в set '{target_set['name']}'")
                        break
                
                if target_set:
                    break
                    
                # Также проверяем через included
                included = set_detail.get("included", [])
                for item in included:
                    if item.get("type") == "custom_field" and item.get("id") == custom_field_id:
                        target_set = {
                            "id": cfs_id,
                            "name": set_attributes.get("name"),
                            "active": set_attributes.get("active", False),
                            "attributes": set_attributes
                        }
                        print(f"[OK] Поле найдено в set '{target_set['name']}' (через included)")
                        break
                
                if target_set:
                    break
                    
            except Exception as e:
                print(f"[WARNING] Ошибка проверки set {cfs_id}: {e}")
                continue
        
        # Метод 2: Если не нашли, пробуем через Search API
        if not target_set:
            print("[INFO] Пробуем поиск через Search API...")
            try:
                sets_response = client._request(
                    "POST",
                    "/api/search/custom-field-set",
                    json={
                        "associations": {
                            "customFields": {}
                        },
                        "limit": 100
                    }
                )
                
                if isinstance(sets_response, dict):
                    sets_data = sets_response.get("data", [])
                    included = sets_response.get("included", [])
                    
                    # Проверяем через relationships
                    for cfs in sets_data:
                        cfs_id = cfs.get("id")
                        relationships = cfs.get("relationships", {})
                        custom_fields_rel = relationships.get("customFields", {})
                        custom_fields_data = custom_fields_rel.get("data", [])
                        
                        for cf_rel in custom_fields_data:
                            if cf_rel.get("id") == custom_field_id:
                                cfs_attributes = cfs.get("attributes", {})
                                target_set = {
                                    "id": cfs_id,
                                    "name": cfs_attributes.get("name"),
                                    "active": cfs_attributes.get("active", False),
                                    "attributes": cfs_attributes
                                }
                                break
                        if target_set:
                            break
                    
                    # Проверяем через included
                    if not target_set:
                        for item in included:
                            if item.get("type") == "custom_field" and item.get("id") == custom_field_id:
                                # Находим set для этого поля
                                for cfs in sets_data:
                                    cfs_id = cfs.get("id")
                                    relationships = cfs.get("relationships", {})
                                    custom_fields_rel = relationships.get("customFields", {})
                                    custom_fields_data = custom_fields_rel.get("data", [])
                                    
                                    for cf_rel in custom_fields_data:
                                        if cf_rel.get("id") == custom_field_id:
                                            cfs_attributes = cfs.get("attributes", {})
                                            target_set = {
                                                "id": cfs_id,
                                                "name": cfs_attributes.get("name"),
                                                "active": cfs_attributes.get("active", False),
                                                "attributes": cfs_attributes
                                            }
                                            break
                                    if target_set:
                                        break
                                if target_set:
                                    break
            except Exception as e:
                print(f"[WARNING] Ошибка Search API: {e}")
        
        if target_set:
            print(f"[OK] Custom field set найден:")
            print(f"  - ID: {target_set['id']}")
            print(f"  - Name: {target_set['name']}")
            print(f"  - Active: {target_set['active']}")
            return target_set
        else:
            print("[WARNING] Custom field set НЕ НАЙДЕН")
            print("[INFO] Возможно, поле не привязано ни к одному set-у")
            print("[INFO] Попробуем найти set для product и добавить туда поле...")
            
            # Ищем set для product
            try:
                all_sets_response = client._request("GET", "/api/custom-field-set")
                all_sets = all_sets_response.get("data", []) if isinstance(all_sets_response, dict) else []
                
                for cfs in all_sets:
                    cfs_id = cfs.get("id")
                    try:
                        # Проверяем relations этого set-а
                        set_detail = client._request(
                            "GET",
                            f"/api/custom-field-set/{cfs_id}?associations[relations]=true"
                        )
                        set_data = set_detail.get("data", {}) if isinstance(set_detail, dict) else {}
                        relationships = set_data.get("relationships", {})
                        relations_rel = relationships.get("relations", {})
                        relations_data = relations_rel.get("data", [])
                        
                        # Проверяем, есть ли relation к product
                        has_product = False
                        for rel in relations_data:
                            rel_id = rel.get("id")
                            try:
                                rel_detail = client._request("GET", f"/api/custom-field-set-relation/{rel_id}")
                                rel_data = rel_detail.get("data", {}) if isinstance(rel_detail, dict) else {}
                                rel_attributes = rel_data.get("attributes", {})
                                if rel_attributes.get("entityName") == "product":
                                    has_product = True
                                    break
                            except:
                                continue
                        
                        if has_product:
                            # Нашли set для product, используем его
                            set_attributes = set_data.get("attributes", {})
                            target_set = {
                                "id": cfs_id,
                                "name": set_attributes.get("name"),
                                "active": set_attributes.get("active", False),
                                "attributes": set_attributes
                            }
                            print(f"[OK] Найден set для product: {target_set['name']}")
                            print(f"[INFO] Добавим поле internal_barcode в этот set")
                            return target_set
                    except:
                        continue
            except Exception as e:
                print(f"[WARNING] Ошибка поиска set для product: {e}")
            
            return None
            
    except Exception as e:
        print(f"[ERROR] Ошибка поиска custom field set: {e}")
        import traceback
        traceback.print_exc()
        return None

def check_product_relation(client: ShopwareClient, set_id: str) -> bool:
    """Проверяет, есть ли relation к entity 'product'."""
    print("\n[ШАГ 3] Проверка relations к entity 'product'...")
    
    try:
        # Получаем relations для set-а
        set_detail = client._request(
            "GET",
            f"/api/custom-field-set/{set_id}?associations[relations]=true"
        )
        
        set_data = set_detail.get("data", {}) if isinstance(set_detail, dict) else {}
        relationships = set_data.get("relationships", {})
        relations_rel = relationships.get("relations", {})
        relations_data = relations_rel.get("data", [])
        
        has_product_relation = False
        
        if relations_data:
            for rel in relations_data:
                rel_id = rel.get("id")
                try:
                    rel_detail = client._request("GET", f"/api/custom-field-set-relation/{rel_id}")
                    rel_data = rel_detail.get("data", {}) if isinstance(rel_detail, dict) else {}
                    rel_attributes = rel_data.get("attributes", {})
                    
                    entity_name = rel_attributes.get("entityName")
                    if entity_name == "product":
                        has_product_relation = True
                        print(f"[OK] Relation к entity 'product' найден (ID: {rel_id})")
                        break
                except Exception as e:
                    continue
        
        # Пробуем через included
        if not has_product_relation:
            included = set_detail.get("included", [])
            for item in included:
                if item.get("type") == "custom_field_set_relation":
                    entity_name = item.get("attributes", {}).get("entityName")
                    if entity_name == "product":
                        has_product_relation = True
                        rel_id = item.get("id")
                        print(f"[OK] Relation к entity 'product' найден через included (ID: {rel_id})")
                        break
        
        # Альтернативный способ: поиск через Search API
        if not has_product_relation:
            try:
                search_response = client._request(
                    "POST",
                    "/api/search/custom-field-set-relation",
                    json={
                        "filter": [
                            {"field": "customFieldSetId", "type": "equals", "value": set_id},
                            {"field": "entityName", "type": "equals", "value": "product"}
                        ],
                        "limit": 1
                    }
                )
                if isinstance(search_response, dict):
                    search_data = search_response.get("data", [])
                    if search_data and len(search_data) > 0:
                        has_product_relation = True
                        rel_id = search_data[0].get("id")
                        print(f"[OK] Relation к entity 'product' найден через Search API (ID: {rel_id})")
            except Exception as e:
                pass
        
        if not has_product_relation:
            print("[WARNING] Relation к entity 'product' НЕ НАЙДЕН")
        
        return has_product_relation
        
    except Exception as e:
        print(f"[ERROR] Ошибка проверки relations: {e}")
        import traceback
        traceback.print_exc()
        return False

def add_product_relation(client: ShopwareClient, set_id: str) -> bool:
    """Добавляет relation к entity 'product'."""
    print("\n[ШАГ 4] Добавление relation к entity 'product'...")
    
    try:
        import uuid
        relation_id = str(uuid.uuid4().hex)
        
        payload = {
            "id": relation_id,
            "customFieldSetId": set_id,
            "entityName": "product"
        }
        
        client._request("POST", "/api/custom-field-set-relation", json=payload)
        print(f"[OK] Relation к entity 'product' добавлен (ID: {relation_id})")
        return True
        
    except Exception as e:
        error_str = str(e)
        # Проверяем, не является ли это ошибкой дубликата (relation уже существует)
        if "Duplicate entry" in error_str or "1062" in error_str or "uniq.custom_field_set_relation.entity_name" in error_str:
            print(f"[OK] Relation к entity 'product' уже существует (дубликат проигнорирован)")
            return True
        print(f"[ERROR] Ошибка добавления relation: {e}")
        import traceback
        traceback.print_exc()
        return False

def ensure_set_active(client: ShopwareClient, set_id: str) -> bool:
    """Убеждается, что custom field set активен."""
    print("\n[ШАГ 5] Проверка активности custom field set...")
    
    try:
        # Получаем текущее состояние
        set_detail = client._request("GET", f"/api/custom-field-set/{set_id}")
        set_data = set_detail.get("data", {}) if isinstance(set_detail, dict) else {}
        set_attributes = set_data.get("attributes", {})
        is_active = set_attributes.get("active", False)
        
        if is_active:
            print(f"[OK] Custom field set уже активен")
            return True
        
        # Активируем set
        print(f"[INFO] Активируем custom field set...")
        client._request("PATCH", f"/api/custom-field-set/{set_id}", json={"active": True})
        
        # Проверяем
        time.sleep(0.5)
        set_detail = client._request("GET", f"/api/custom-field-set/{set_id}")
        set_data = set_detail.get("data", {}) if isinstance(set_detail, dict) else {}
        set_attributes = set_data.get("attributes", {})
        is_active = set_attributes.get("active", False)
        
        if is_active:
            print(f"[OK] Custom field set активирован")
            return True
        else:
            print(f"[WARNING] Не удалось активировать custom field set")
            return False
            
    except Exception as e:
        print(f"[ERROR] Ошибка проверки/активации set: {e}")
        import traceback
        traceback.print_exc()
        return False

def set_field_position(client: ShopwareClient, custom_field_id: str) -> bool:
    """Устанавливает customFieldPosition = 10 для поля."""
    print("\n[ШАГ 6] Установка customFieldPosition = 10...")
    
    try:
        # Получаем текущую конфигурацию
        field_detail = client._request("GET", f"/api/custom-field/{custom_field_id}")
        field_data = field_detail.get("data", {}) if isinstance(field_detail, dict) else {}
        field_attributes = field_data.get("attributes", {})
        current_config = field_attributes.get("config", {})
        
        current_position = current_config.get("customFieldPosition", 0)
        print(f"[INFO] Текущая позиция: {current_position}")
        
        if current_position == 10:
            print(f"[OK] Позиция уже установлена в 10")
            return True
        
        # Обновляем конфигурацию
        new_config = current_config.copy()
        new_config["customFieldPosition"] = 10
        
        # Сохраняем label и helpText если они есть
        if "label" not in new_config:
            new_config["label"] = current_config.get("label", {"ru-RU": "Внутренний штрих-код"})
        if "helpText" not in new_config:
            new_config["helpText"] = current_config.get("helpText", {"ru-RU": "Пользовательский штрих-код из InSales"})
        
        payload = {
            "config": new_config
        }
        
        client._request("PATCH", f"/api/custom-field/{custom_field_id}", json=payload)
        
        # Проверяем
        time.sleep(0.5)
        field_detail = client._request("GET", f"/api/custom-field/{custom_field_id}")
        field_data = field_detail.get("data", {}) if isinstance(field_detail, dict) else {}
        field_attributes = field_data.get("attributes", {})
        updated_config = field_attributes.get("config", {})
        updated_position = updated_config.get("customFieldPosition", 0)
        
        if updated_position == 10:
            print(f"[OK] Позиция установлена в 10")
            return True
        else:
            print(f"[WARNING] Позиция не обновилась (текущая: {updated_position})")
            return False
            
    except Exception as e:
        print(f"[ERROR] Ошибка установки позиции: {e}")
        import traceback
        traceback.print_exc()
        return False

def clear_admin_cache(client: ShopwareClient) -> bool:
    """Очищает кеш админки Shopware."""
    print("\n[ШАГ 7] Очистка кеша админки...")
    
    try:
        # Очистка кеша через API
        client._request("DELETE", "/api/_action/cache")
        print(f"[OK] Кеш админки очищен")
        return True
        
    except Exception as e:
        print(f"[WARNING] Не удалось очистить кеш через API: {e}")
        print(f"[INFO] Возможно, нужно очистить кеш вручную через админку или CLI")
        return False

def main() -> int:
    """Основная функция."""
    
    print("="*80)
    print("ИСПРАВЛЕНИЕ ОТОБРАЖЕНИЯ CUSTOM FIELD internal_barcode")
    print("="*80)
    
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
    client = ShopwareClient(shop_cfg, timeout=30)
    
    # ШАГ 1: Найти custom field
    custom_field = find_custom_field(client)
    if not custom_field:
        print("\n[FAIL] Не удалось найти custom field. Прерываем выполнение.")
        return 1
    
    custom_field_id = custom_field["id"]
    
    # ШАГ 2: Найти custom field set
    custom_field_set = find_custom_field_set(client, custom_field_id)
    
    # Если set не найден, но поле существует, нужно добавить его в существующий set для product
    if not custom_field_set:
        print("\n[INFO] Custom field set не найден. Пробуем добавить поле в существующий set для product...")
        
        # Ищем set для product
        try:
            all_sets_response = client._request("GET", "/api/custom-field-set")
            all_sets = all_sets_response.get("data", []) if isinstance(all_sets_response, dict) else []
            
            product_set = None
            for cfs in all_sets:
                cfs_id = cfs.get("id")
                try:
                    set_detail = client._request(
                        "GET",
                        f"/api/custom-field-set/{cfs_id}?associations[relations]=true"
                    )
                    set_data = set_detail.get("data", {}) if isinstance(set_detail, dict) else {}
                    relationships = set_data.get("relationships", {})
                    relations_rel = relationships.get("relations", {})
                    relations_data = relations_rel.get("data", [])
                    
                    # Проверяем, есть ли relation к product
                    for rel in relations_data:
                        rel_id = rel.get("id")
                        try:
                            rel_detail = client._request("GET", f"/api/custom-field-set-relation/{rel_id}")
                            rel_data = rel_detail.get("data", {}) if isinstance(rel_detail, dict) else {}
                            rel_attributes = rel_data.get("attributes", {})
                            if rel_attributes.get("entityName") == "product":
                                set_attributes = set_data.get("attributes", {})
                                product_set = {
                                    "id": cfs_id,
                                    "name": set_attributes.get("name"),
                                    "active": set_attributes.get("active", False),
                                    "attributes": set_attributes
                                }
                                break
                        except:
                            continue
                    if product_set:
                        break
                except:
                    continue
            
            if product_set:
                print(f"[OK] Найден set для product: {product_set['name']}")
                print(f"[INFO] Добавляем поле internal_barcode в этот set...")
                
                # Добавляем поле в set через PATCH
                try:
                    # Получаем текущие customFields set-а
                    set_detail = client._request(
                        "GET",
                        f"/api/custom-field-set/{product_set['id']}?associations[customFields]=true"
                    )
                    set_data = set_detail.get("data", {}) if isinstance(set_detail, dict) else {}
                    relationships = set_data.get("relationships", {})
                    custom_fields_rel = relationships.get("customFields", {})
                    existing_fields = custom_fields_rel.get("data", [])
                    
                    # Проверяем, нет ли уже нашего поля
                    field_exists = False
                    for cf_rel in existing_fields:
                        if cf_rel.get("id") == custom_field_id:
                            field_exists = True
                            break
                    
                    if not field_exists:
                        # Добавляем поле через обновление custom field (устанавливаем customFieldSetId)
                        try:
                            client._request("PATCH", f"/api/custom-field/{custom_field_id}", json={
                                "customFieldSetId": product_set['id']
                            })
                            print(f"[OK] Поле добавлено в set через customFieldSetId")
                        except Exception as e:
                            print(f"[WARNING] Не удалось через customFieldSetId: {e}")
                            # Пробуем через associations в set
                            existing_field_ids = [cf.get("id") for cf in existing_fields if cf.get("id")]
                            existing_field_ids.append(custom_field_id)
                            payload = {
                                "customFields": [{"id": fid} for fid in existing_field_ids]
                            }
                            client._request("PATCH", f"/api/custom-field-set/{product_set['id']}", json=payload)
                            print(f"[OK] Поле добавлено в set через associations")
                    else:
                        print(f"[INFO] Поле уже есть в set")
                    
                    custom_field_set = product_set
                except Exception as e:
                    print(f"[WARNING] Не удалось добавить поле в set: {e}")
                    print(f"[INFO] Продолжаем с найденным set-ом...")
                    custom_field_set = product_set
            else:
                print("\n[INFO] Set для product не найден.")
                print("[INFO] Создаем минимальный set для product...")
                custom_field_set = create_minimal_product_set(client, custom_field_id)
                if not custom_field_set:
                    print("\n[FAIL] Не удалось создать set. Прерываем выполнение.")
                    return 1
        except Exception as e:
            print(f"[ERROR] Ошибка поиска set для product: {e}")
            return 1
    
    if not custom_field_set:
        print("\n[FAIL] Не удалось найти или создать custom field set. Прерываем выполнение.")
        return 1
    
    set_id = custom_field_set["id"]
    
    # ШАГ 3: Проверить relation к product
    has_product_relation = check_product_relation(client, set_id)
    
    # ШАГ 4: Добавить relation если отсутствует
    if not has_product_relation:
        if add_product_relation(client, set_id):
            # Ждем и проверяем снова
            time.sleep(1)
            has_product_relation = check_product_relation(client, set_id)
        else:
            print("\n[WARNING] Не удалось добавить relation, но продолжаем...")
    
    # ШАГ 5: Убедиться что set активен
    if not ensure_set_active(client, set_id):
        print("\n[WARNING] Не удалось активировать set, но продолжаем...")
    
    # ШАГ 6: Установить позицию поля
    if not set_field_position(client, custom_field_id):
        print("\n[WARNING] Не удалось установить позицию, но продолжаем...")
    
    # ШАГ 7: Очистить кеш
    clear_admin_cache(client)
    
    # ИТОГОВЫЙ ОТЧЕТ
    print("\n" + "="*80)
    print("ИТОГОВЫЙ ОТЧЕТ")
    print("="*80)
    
    print(f"\n[1] Custom field 'internal_barcode':")
    print(f"    [OK] Найден (ID: {custom_field_id})")
    
    print(f"\n[2] Custom field set:")
    print(f"    [OK] Найден: {custom_field_set['name']} (ID: {set_id})")
    
    # Финальная проверка
    print(f"\n[3] Финальная проверка конфигурации...")
    time.sleep(1)
    
    # Проверяем set
    set_detail = client._request("GET", f"/api/custom-field-set/{set_id}?associations[relations]=true")
    set_data = set_detail.get("data", {}) if isinstance(set_detail, dict) else {}
    set_attributes = set_data.get("attributes", {})
    
    print(f"    - Set active: {set_attributes.get('active', False)}")
    
    # Проверяем relations
    relationships = set_data.get("relationships", {})
    relations_rel = relationships.get("relations", {})
    relations_data = relations_rel.get("data", [])
    
    has_product = False
    if relations_data:
        for rel in relations_data:
            rel_id = rel.get("id")
            try:
                rel_detail = client._request("GET", f"/api/custom-field-set-relation/{rel_id}")
                rel_data = rel_detail.get("data", {}) if isinstance(rel_detail, dict) else {}
                rel_attributes = rel_data.get("attributes", {})
                if rel_attributes.get("entityName") == "product":
                    has_product = True
                    break
            except:
                continue
    
    # Альтернативная проверка через Search API
    if not has_product:
        try:
            search_response = client._request(
                "POST",
                "/api/search/custom-field-set-relation",
                json={
                    "filter": [
                        {"field": "customFieldSetId", "type": "equals", "value": set_id},
                        {"field": "entityName", "type": "equals", "value": "product"}
                    ],
                    "limit": 1
                }
            )
            if isinstance(search_response, dict):
                search_data = search_response.get("data", [])
                if search_data and len(search_data) > 0:
                    has_product = True
        except:
            pass
    
    # Проверяем через included
    if not has_product:
        included = set_detail.get("included", [])
        for item in included:
            if item.get("type") == "custom_field_set_relation":
                entity_name = item.get("attributes", {}).get("entityName")
                if entity_name == "product":
                    has_product = True
                    break
    
    print(f"    - Relation к 'product': {'Да' if has_product else 'Нет'}")
    
    # Проверяем позицию
    field_detail = client._request("GET", f"/api/custom-field/{custom_field_id}")
    field_data = field_detail.get("data", {}) if isinstance(field_detail, dict) else {}
    field_attributes = field_data.get("attributes", {})
    field_config = field_attributes.get("config", {})
    position = field_config.get("customFieldPosition", 0)
    
    print(f"    - CustomFieldPosition: {position}")
    
    print(f"\n[4] Результат:")
    if set_attributes.get("active", False) and has_product and position > 0:
        print(f"    [OK] ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
        print(f"    [OK] Поле должно отображаться в Admin UI")
        print(f"\n    [INFO] Если поле все еще не видно:")
        print(f"        - Очистите кеш браузера (Ctrl+Shift+R)")
        print(f"        - Проверьте права доступа пользователя")
        print(f"        - Убедитесь, что вы открыли карточку товара в админке")
    else:
        print(f"    [WARNING] НЕКОТОРЫЕ ПРОВЕРКИ НЕ ПРОЙДЕНЫ")
        if not set_attributes.get("active", False):
            print(f"        - Set не активен")
        if not has_product:
            print(f"        - Нет relation к 'product'")
        if position == 0:
            print(f"        - Позиция не установлена")
    
    print("\n" + "="*80)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

