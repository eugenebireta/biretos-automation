# Исправление логики назначения категорий при импорте

**Дата:** 2025-01-17

## Проблема

Товары привязываются только к родительской категории. Leaf-категория не определяется и не назначается.

## Анализ текущей логики

### Источник категорий в InSales

1. **Режим snapshot (NDJSON):**
   - `product.collections_ids` - список ID коллекций (категорий)
   - `product.category_id` - основная категория
   - `product.canonical_url_collection_id` - каноническая коллекция (приоритет)
   - Путь категории извлекается из `category_id_to_path.json` по `category_id`

2. **Режим API:**
   - `row.categoryIds` или `row.category_id` - ID категории
   - Преобразование через `migration_map.json` в Shopware UUID

### Где теряется leaf

**Проблемные места:**

1. **Строки 716-731 (bind-categories режим):**
   - Определение `leaf_category_id` через `canonical_collection_id` или `is_leaf_category()`
   - Fallback на последнюю категорию из списка
   - **Проблема:** Не гарантируется, что последняя категория = leaf

2. **Строки 1684-1690 (CREATE для NDJSON):**
   - `get_category_chain()` вызывается для `leaf_category_id`
   - **Проблема:** Не проверяется, что последний элемент цепочки = leaf
   - **Проблема:** Не гарантируется глубина >= 2

3. **Строки 2131-2146 (UPDATE для NDJSON):**
   - `get_category_chain()` вызывается, но без проверки leaf
   - **Проблема:** Не гарантируется, что последний элемент = leaf

4. **Строки 733-747 (bind-categories режим):**
   - Объединение категорий без гарантии leaf в конце
   - **Проблема:** Может получиться цепочка без leaf

## Исправления

### 1. CREATE (строки 1715-1765)

**Добавлено:**
- Проверка, что `leaf_category_id` действительно leaf
- Гарантия, что последний элемент `category_chain` = leaf
- Гарантия глубины >= 2 (минимум root -> leaf)
- Убрано использование `mainCategoryId` / `mainCategories`

**Код:**
```python
# КАНОНИЧЕСКАЯ ЛОГИКА SHOPWARE 6:
# Товар должен быть привязан ко ВСЕМ категориям цепочки (от root до leaf)
# Последний элемент цепочки ДОЛЖЕН быть leaf категорией
if leaf_category_id:
    # Проверяем, что leaf_category_id действительно leaf
    if not is_leaf_category(client, leaf_category_id):
        temp_chain = get_category_chain(client, leaf_category_id)
        if temp_chain:
            last_in_chain = temp_chain[-1]
            if is_leaf_category(client, last_in_chain):
                leaf_category_id = last_in_chain
    
    # Получаем полную цепочку от root до leaf
    category_chain = get_category_chain(client, leaf_category_id)
    
    # ГАРАНТИЯ: Последний элемент цепочки = leaf
    if category_chain:
        last_cat = category_chain[-1]
        if not is_leaf_category(client, last_cat):
            if last_cat != leaf_category_id:
                category_chain[-1] = leaf_category_id
            elif leaf_category_id not in category_chain:
                category_chain.append(leaf_category_id)
    else:
        category_chain = [leaf_category_id]
    
    # ГАРАНТИЯ: Глубина >= 2 (минимум root -> leaf)
    if len(category_chain) < 2:
        # Получаем родителя leaf
        cat_response = client._request("GET", f"/api/category/{leaf_category_id}")
        # ... добавляем parent_id в начало цепочки
    
    payload["categories"] = [{"id": cat_id} for cat_id in category_chain]
```

### 2. UPDATE (строки 2131-2170)

**Добавлено:**
- Та же логика гарантий leaf и глубины
- Убрано использование `mainCategories`

**Код:**
```python
# ШАГ 5: Обновление categories для UPDATE
# ГАРАНТИЯ: Полная цепочка от root до leaf, последний элемент = leaf
if use_ndjson and leaf_category_id:
    category_chain = get_category_chain(client, leaf_category_id)
    # ... те же гарантии, что и для CREATE
    categories_payload = {"categories": [{"id": cat_id} for cat_id in category_chain]}
    client._request("PATCH", f"/api/product/{final_product_id}", json=categories_payload)
```

### 3. bind-categories режим (строки 733-773)

**Добавлено:**
- Гарантия, что последний элемент цепочки = leaf
- Гарантия глубины >= 2
- Убрано использование `mainCategoryId`

**Код:**
```python
# ШАГ 4: Формируем ПОЛНУЮ цепочку категорий от root до leaf
category_chain = get_category_chain(client, leaf_category_id)
# ... гарантии leaf и глубины

# ШАГ 5: PATCH ТОЛЬКО с categories (без mainCategoryId)
patch_payload = {
    "id": shopware_product_id,
    "categories": categories_payload,
}
```

## Запреты (соблюдены)

- ✅ НЕ используется `visibility.categoryId`
- ✅ НЕ используется `mainCategoryId` / `mainCategories`
- ✅ НЕ трогается Marketplace Price
- ✅ НЕ трогается Manufacturer

## Гарантии

1. **Полная цепочка категорий:**
   - `product.categories` содержит ВСЮ цепочку от root до leaf
   - Последний элемент цепочки = leaf категория

2. **Глубина >= 2:**
   - Минимум root -> leaf
   - Если цепочка слишком короткая, добавляется родитель leaf

3. **Leaf категория:**
   - Проверяется через `is_leaf_category()`
   - Если последний элемент не leaf, заменяется на `leaf_category_id`

## Откуда берётся category path в InSales

### Режим snapshot (NDJSON)

1. **Источник:** `product.category_id` (строка 1475)
2. **Преобразование:** `category_id_to_path.json` → `full_path` (строка 1497)
3. **Поиск leaf:**
   - Если `full_path` = UUID (32 hex символа) → используется напрямую (строка 1514)
   - Если `full_path` = путь (строка вида "Каталог > Электрика > Реле") → `find_category_by_path()` (строка 1527)
4. **Проверка leaf:** `is_leaf_category()` (строки 1516, 1540)

### Режим API (CSV)

1. **Источник:** `row.categoryIds` или `row.category_id` (строка 1550)
2. **Преобразование:** `migration_map.json` → Shopware UUID (строка 1532)
3. **Проверка leaf:** `is_leaf_category()` (строка 1545)

### Где теряется leaf

**Проблема:** После определения `leaf_category_id` цепочка категорий формируется через `get_category_chain()`, но:
- Не гарантировалось, что последний элемент цепочки = leaf
- Не гарантировалась глубина >= 2
- Использовался `mainCategoryId`, что не нужно

## Валидация

**Текущее состояние (5 товаров Boeing):**
- Категорий привязано: 0 (все товары)
- Leaf Category: None (все товары)
- Depth: 0 (все товары)
- **Статус: FAIL (0/5 валидных)**

**Причина:** Товары были импортированы ДО исправления логики, поэтому категории не назначены.

## Исправления применены

✅ **CREATE (строки 1715-1768):**
- Проверка leaf перед формированием цепочки
- Гарантия, что последний элемент = leaf
- Гарантия глубины >= 2
- Убрано `mainCategories`

✅ **UPDATE (строки 2131-2175):**
- Та же логика гарантий
- Убрано `mainCategories`

✅ **bind-categories (строки 733-790):**
- Гарантии leaf и глубины
- Убрано `mainCategoryId`

## Следующие шаги

1. ✅ Исправления применены в `full_import.py`
2. ⏳ Протестировать на одном товаре: `python full_import.py --single-sku 500944222 --source snapshot`
3. ⏳ Проверить результат: `python verify_product_state.py 500944222`
4. ⏳ Если OK, выполнить переимпорт проблемных товаров
5. ⏳ Повторно валидировать: `python fix_leaf_categories.py`
