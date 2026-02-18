from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from clients import ShopwareClient


def normalize_category_name(name: str) -> str:
    """
    Нормализует название категории для сравнения.
    
    Args:
        name: Название категории
        
    Returns:
        Нормализованное название (lowercase, trim, unicode нормализация)
    """
    if not name:
        return ""
    # Trim
    normalized = name.strip()
    # Lowercase
    normalized = normalized.lower()
    # Удаляем лишние пробелы
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def parse_category_path(path_str: str) -> List[str]:
    """
    Парсит строку пути категории вида "Каталог > Электрика > Реле".
    
    Args:
        path_str: Строка пути категории
        
    Returns:
        Список названий категорий от корня к листу
    """
    if not path_str:
        return []
    
    # Разделяем по ">" или другим разделителям
    parts = re.split(r"\s*[>|]\s*", path_str)
    # Нормализуем каждую часть
    normalized_parts = [normalize_category_name(part) for part in parts if part.strip()]
    return normalized_parts


def find_category_by_path(
    client: ShopwareClient,
    category_path: str,
    root_category_id: Optional[str] = None,
) -> Optional[str]:
    """
    Находит категорию в Shopware по пути вида "Каталог > Электрика > Реле".
    
    Ищет самую глубокую (leaf) категорию по пути, проходя по дереву категорий.
    
    Args:
        client: ShopwareClient для запросов к API
        category_path: Путь категории (строка с разделителями ">" или "|")
        root_category_id: ID корневой категории для начала поиска (опционально)
        
    Returns:
        UUID категории Shopware или None если не найдена
    """
    if not category_path:
        return None
    
    # Парсим путь
    path_parts = parse_category_path(category_path)
    if not path_parts:
        return None
    
    # Если путь состоит из одного элемента (число), это может быть ID, не путь
    if len(path_parts) == 1 and path_parts[0].isdigit():
        # Это не путь, а ID - возвращаем None
        return None
    
    # Получаем все категории Shopware для локального поиска
    try:
        all_categories = _get_all_categories_with_cache(client)
    except Exception:
        # Если не удалось загрузить, возвращаем None
        return None
    
    # Строим индекс категорий по названиям и parentId
    categories_by_parent: Dict[str, List[Dict[str, Any]]] = {}
    categories_by_id: Dict[str, Dict[str, Any]] = {}
    
    for cat in all_categories:
        cat_id = cat.get("id", "")
        parent_id = cat.get("parentId") or "ROOT"
        cat_name = normalize_category_name(cat.get("name", ""))
        
        if not cat_id:
            continue
        
        categories_by_id[cat_id] = cat
        
        if parent_id not in categories_by_parent:
            categories_by_parent[parent_id] = []
        categories_by_parent[parent_id].append({
            "id": cat_id,
            "name": cat_name,
            "original_name": cat.get("name", ""),
        })
    
    # Начинаем поиск с корня
    current_parent_id = root_category_id or "ROOT"
    found_category_id = None
    last_found_category_id = None
    
    # Проходим по пути, находим самую глубокую существующую категорию
    for path_part in path_parts:
        # Ищем категорию с таким названием среди детей current_parent_id
        children = categories_by_parent.get(current_parent_id, [])
        
        found = False
        for child in children:
            if child["name"] == path_part:
                found_category_id = child["id"]
                current_parent_id = child["id"]
                last_found_category_id = child["id"]
                found = True
                break
        
        if not found:
            # Не нашли категорию на этом уровне пути
            # Возвращаем последнюю найденную категорию, если она была
            break
    
    # Если путь полностью не найден, используем последнюю найденную категорию
    if not found_category_id and last_found_category_id:
        found_category_id = last_found_category_id
    
    if not found_category_id:
        return None
    
    # Нашли категорию - ищем самую глубокую leaf категорию
    # Проверяем, является ли текущая категория листовой (нет дочерних в кэше)
    if found_category_id not in categories_by_parent or not categories_by_parent.get(found_category_id):
        # Категория листовая (нет дочерних)
        return found_category_id
    
    # Если категория не листовая, ищем самую глубокую leaf дочернюю категорию
    def find_deepest_leaf(category_id: str) -> Optional[str]:
        """Рекурсивно находит самую глубокую leaf категорию в поддереве."""
        # Проверяем, является ли текущая категория листовой (нет дочерних)
        children = categories_by_parent.get(category_id, [])
        if not children:
            # Нет детей - это leaf категория
            return category_id
        
        # Рекурсивно ищем в дочерних категориях
        # Ищем первую найденную leaf категорию (самую глубокую в первом поддереве)
        for child in children:
            leaf = find_deepest_leaf(child["id"])
            if leaf:
                return leaf
        
        # Если ни одна дочерняя не leaf, возвращаем текущую (но это не должно произойти)
        return None
    
    # Ищем самую глубокую leaf категорию
    deepest_leaf = find_deepest_leaf(found_category_id)
    # Если не нашли leaf, возвращаем None (требуется именно leaf категория)
    return deepest_leaf


# Кэш для всех категорий (чтобы не загружать каждый раз)
_category_cache: Optional[List[Dict[str, Any]]] = None


def _get_all_categories_with_cache(client: ShopwareClient) -> List[Dict[str, Any]]:
    """Получает все категории из Shopware с кэшированием."""
    global _category_cache
    
    if _category_cache is not None:
        return _category_cache
    
    all_categories = []
    page = 1
    per_page = 100
    
    while True:
        try:
            response = client._request(
                "POST",
                "/api/search/category",
                json={
                    "limit": per_page,
                    "page": page,
                    "includes": {"category": ["id", "name", "parentId"]},
                },
            )
            if isinstance(response, dict) and "data" in response:
                data = response.get("data", [])
                if not data:
                    break
                all_categories.extend(data)
                if len(data) < per_page:
                    break
                page += 1
            else:
                break
        except Exception:
            break
    
    _category_cache = all_categories
    return all_categories


def is_leaf_category(
    client: ShopwareClient,
    category_id: str,
) -> bool:
    """
    Проверяет, является ли категория листовой (не имеет дочерних категорий).
    
    Args:
        client: ShopwareClient для запросов к API
        category_id: ID категории в Shopware
        
    Returns:
        True если категория листовая (нет детей), False если есть дети
    """
    try:
        response = client._request(
            "POST",
            "/api/search/category",
            json={
                "filter": [
                    {"field": "parentId", "type": "equals", "value": category_id},
                ],
                "limit": 1,
                "includes": {"category": ["id"]},
            },
        )
        if isinstance(response, dict):
            total = response.get("total", 0)
            return total == 0
        return True  # Если не можем определить, считаем листовой
    except Exception:
        # При ошибке считаем листовой (безопасный fallback)
        return True


def get_category_chain(
    client: ShopwareClient,
    leaf_category_id: str,
) -> List[str]:
    """
    Получает цепочку категорий от leaf до root (включая все родительские категории).
    
    Согласно канонической логике Shopware 6:
    - Товар должен быть привязан ко ВСЕМ категориям цепочки (product.categories)
    - Самая глубокая категория (leaf) используется для product_visibility.categoryId
    
    Args:
        client: ShopwareClient для запросов к API
        leaf_category_id: ID листовой категории (самой глубокой)
        
    Returns:
        Список ID категорий от root к leaf (первый элемент - root, последний - leaf)
        Если категория не найдена, возвращает список с одним элементом [leaf_category_id]
    """
    if not leaf_category_id:
        return []
    
    try:
        # Получаем все категории с кэшированием
        all_categories = _get_all_categories_with_cache(client)
        
        # Строим индекс категорий по ID
        categories_by_id: Dict[str, Dict[str, Any]] = {}
        for cat in all_categories:
            cat_id = cat.get("id", "")
            if cat_id:
                categories_by_id[cat_id] = cat
        
        # Если категория не найдена в кэше, возвращаем только leaf
        if leaf_category_id not in categories_by_id:
            return [leaf_category_id]
        
        # Строим цепочку от leaf к root
        chain: List[str] = []
        current_id: Optional[str] = leaf_category_id
        
        # Проходим по цепочке родителей до root (parentId = null)
        visited = set()  # Защита от циклических ссылок
        while current_id and current_id not in visited:
            visited.add(current_id)
            chain.append(current_id)
            
            category = categories_by_id.get(current_id)
            if not category:
                break
            
            parent_id = category.get("parentId")
            if not parent_id:
                # Дошли до root (parentId = null)
                break
            
            current_id = parent_id
        
        # Возвращаем цепочку от root к leaf (обращаем список)
        chain.reverse()
        
        # Если цепочка пустая, возвращаем хотя бы leaf
        if not chain:
            return [leaf_category_id]
        
        return chain
    except Exception as e:
        # При ошибке возвращаем только leaf категорию
        # Это безопасный fallback - товар будет хотя бы в одной категории
        return [leaf_category_id]



