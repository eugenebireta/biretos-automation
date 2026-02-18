# План канонического pipeline для Properties и Variants

**Дата:** 2025-12-14  
**Статус:** План (без реализации)

---

## Цель

Подготовить канонический pipeline для properties и variants в Shopware 6.7, аналогичный исправленному image pipeline (media + cover).

---

## 1. Анализ текущей логики

### Properties

**CREATE путь:**
- ✅ Properties создаются через `process_characteristics()`
- ✅ Добавляются в payload: `{"properties": [{"id": "..."}]}`
- ✅ Работает корректно

**UPDATE путь:**
- ❌ Properties **НЕ обновляются** при UPDATE
- Комментарий: "Shopware добавляет, не заменяет"
- Риск: Невозможно удалить старые properties или заменить их

**Формат:**
```json
{
  "properties": [
    {"id": "property_option_id_1"},
    {"id": "property_option_id_2"}
  ]
}
```

### Variants

**Текущее состояние:**
- ❌ Используется только первый вариант: `variants[0]`
- ❌ Нет создания child products
- ❌ Нет `configuratorSettings`
- ❌ Нет parent/child структуры

**Извлекаемые данные (только из первого варианта):**
- `sku` → `productNumber`
- `price` → `price[0].gross`
- `quantity` → `stock`
- `weight` → `weight`
- `dimensions` → `width`, `height`, `length`
- `barcode` → `customFields.internal_barcode`

---

## 2. Риски (аналогично coverId)

### Риск 1: Properties при PATCH могут быть read-only

**Аналогия с coverId:**
- `coverId` был read-only при прямом PATCH
- Решение: associations.cover `{"cover": {"id": "..."}}`
- **Вопрос:** Является ли `properties` read-only при PATCH?

**Эксперимент нужен:**
- PATCH product с `{"properties": [{"id": "new_id"}]}`
- Проверить: сохраняются ли properties?
- Если нет → нужен associations-подход

### Риск 2: Properties при PATCH могут append, а не replace

**Текущий комментарий:**
> "Shopware добавляет, не заменяет"

**Проблема:**
- При UPDATE старые properties остаются
- Новые properties добавляются
- Результат: дубликаты properties

**Решение:**
- DELETE старых properties перед PATCH
- Или использовать associations для замены

### Риск 3: Options / ConfiguratorSettings могут быть read-only

**Если variants нужны:**
- `options` может быть read-only при PATCH
- `configuratorSettings` может быть read-only при PATCH
- `parentId` может быть read-only при PATCH

**Решение:**
- Исследовать поведение Shopware 6.7
- Использовать associations, если read-only

---

## 3. Канонический порядок CREATE

### Шаг 1: Подготовка Properties
1. Создание Property Groups (если не существуют)
2. Создание Property Options (если не существуют)
3. Сбор списка `property_option_ids`

### Шаг 2: Подготовка Media
1. Создание Media entities
2. Сбор списка `media_ids`

### Шаг 3: Создание Product
```
POST /api/product
{
  "name": "...",
  "productNumber": "...",
  "price": [...],
  "stock": ...,
  "categories": [{"id": "..."}],
  "manufacturerId": "...",
  "properties": [{"id": "..."}],  // ТОЛЬКО для CREATE
  "weight": ...,
  "width": ...,
  "height": ...,
  "length": ...
}
```

### Шаг 4: Создание Product-Media связей
```
POST /api/product-media (для каждого изображения)
{
  "productId": "...",
  "mediaId": "...",
  "position": ...
}
```

### Шаг 5: Установка Cover
```
PATCH /api/product/{id}
{
  "cover": {
    "id": "product_media_id"
  }
}
```

### Шаг 6: Установка CustomFields
```
PATCH /api/product/{id}
{
  "customFields": {
    "internal_barcode": "..."
  }
}
```

---

## 4. Канонический порядок UPDATE

### Шаг 1: PATCH основных полей (БЕЗ properties, customFields, coverId)
```
PATCH /api/product/{id}
{
  "name": "...",
  "productNumber": "...",
  "price": [...],
  "stock": ...,
  "weight": ...,
  "width": ...,
  "height": ...,
  "length": ...
}
```

### Шаг 2: PATCH CustomFields
```
PATCH /api/product/{id}
{
  "customFields": {
    "internal_barcode": "..."
  }
}
```

### Шаг 3: DELETE старых Product-Media
```
DELETE /api/product-media/{id} (для каждого старого product_media)
```

### Шаг 4: CREATE новых Product-Media
```
POST /api/product-media (для каждого нового изображения)
{
  "productId": "...",
  "mediaId": "...",
  "position": ...
}
```

### Шаг 5: PATCH Cover (associations.cover)
```
PATCH /api/product/{id}
{
  "cover": {
    "id": "product_media_id"
  }
}
```

### Шаг 6: Properties UPDATE (требует исследования)

**Вариант A: Если properties read-only при PATCH**
```
PATCH /api/product/{id}
{
  "properties": [
    {"id": "property_option_id_1"},
    {"id": "property_option_id_2"}
  ]
}
```
→ Если не работает, использовать associations:
```
PATCH /api/product/{id}
{
  "properties": [
    {"id": "property_option_id_1"},
    {"id": "property_option_id_2"}
  ]
}
```

**Вариант B: Если properties append при PATCH**
1. DELETE старых properties:
   ```
   DELETE /api/product-property/{id} (для каждого старого property)
   ```
2. PATCH с новыми properties:
   ```
   PATCH /api/product/{id}
   {
     "properties": [
       {"id": "property_option_id_1"},
       {"id": "property_option_id_2"}
     ]
   }
   ```

**Вариант C: Если properties replace при PATCH**
```
PATCH /api/product/{id}
{
  "properties": [
    {"id": "property_option_id_1"},
    {"id": "property_option_id_2"}
  ]
}
```

---

## 5. Guards от регрессий

### Guard 1: Проверка формата Properties

**Место:** `full_import.py`, перед добавлением properties в payload

**Проверка:**
```python
# ЗАЩИТА ОТ РЕГРЕССИИ: Properties должны быть в формате [{"id": "..."}]
if "properties" in payload:
    for prop in payload["properties"]:
        if not isinstance(prop, dict) or "id" not in prop:
            warnings.warn(
                f"[REGRESSION GUARD] Неверный формат properties для товара {product_number}. "
                f"Ожидается [{{\"id\": \"...\"}}], получено: {prop}",
                UserWarning
            )
```

### Guard 2: Проверка Properties в основном PATCH

**Место:** `full_import.py`, в UPDATE логике

**Проверка:**
```python
# ЗАЩИТА ОТ РЕГРЕССИИ: Properties НЕ должны быть в основном PATCH payload
if "properties" in payload and existing_id:
    warnings.warn(
        f"[REGRESSION GUARD] Properties обнаружены в основном PATCH payload для товара {product_number}. "
        f"Properties должны обновляться отдельным PATCH после основных полей.",
        UserWarning
    )
    del payload["properties"]  # Удаляем из основного payload
```

### Guard 3: Валидация Properties в shopware_client.py

**Место:** Новый метод `update_product_properties()`

**Проверка:**
```python
def update_product_properties(self, product_id: str, property_option_ids: List[str]) -> bool:
    """
    Обновляет properties товара через PATCH /api/product/{id}.
    
    ВАЖНО: Требует исследования поведения Shopware 6.7:
    - Если properties read-only → использовать associations
    - Если properties append → DELETE старых перед PATCH
    - Если properties replace → PATCH напрямую
    """
    # Валидация формата
    if not all(isinstance(pid, str) and pid for pid in property_option_ids):
        raise ValueError("property_option_ids must be non-empty strings")
    
    payload = {
        "properties": [{"id": pid} for pid in property_option_ids]
    }
    
    # TODO: Исследовать, нужен ли associations-подход
    # TODO: Исследовать, нужно ли DELETE старых перед PATCH
    
    self._request("PATCH", f"/api/product/{product_id}", json=payload)
    return True
```

---

## 6. Критические вопросы для исследования

### Вопрос 1: Properties при PATCH - read-only?

**Эксперимент:**
1. Создать товар с properties: `[{"id": "option_1"}]`
2. PATCH товар с новыми properties: `{"properties": [{"id": "option_2"}]}`
3. Проверить результат:
   - Если properties = `[option_1, option_2]` → append
   - Если properties = `[option_2]` → replace
   - Если properties = `[option_1]` → read-only (не сохранилось)

**Ожидаемый результат:**
- Определить поведение Shopware 6.7
- Выбрать правильный подход (associations / DELETE+CREATE / replace)

### Вопрос 2: Properties через associations?

**Эксперимент:**
1. Если properties read-only при прямом PATCH
2. Попробовать associations-подход:
   ```
   PATCH /api/product/{id}
   {
     "properties": [
       {"id": "option_1"},
       {"id": "option_2"}
     ]
   }
   ```
3. Проверить, сохраняются ли properties

**Ожидаемый результат:**
- Если associations работают → использовать их
- Если нет → использовать DELETE+CREATE

### Вопрос 3: Variants нужны?

**Вопрос:**
- Нужны ли variants (parent/child products) для проекта?
- Если да → создать отдельный pipeline
- Если нет → оставить как есть (только первый вариант)

**Ожидаемый результат:**
- Решение о необходимости variants pipeline

---

## 7. План реализации

### Этап 1: Исследование (БЕЗ кода)

**Задачи:**
1. ✅ Создать тестовый скрипт для проверки Properties при PATCH
2. ✅ Проверить поведение Shopware 6.7:
   - Properties read-only?
   - Properties append или replace?
   - Нужен ли associations-подход?
3. ✅ Определить, нужны ли variants

**Результат:**
- Отчет о поведении Properties при PATCH
- Решение о необходимости variants

### Этап 2: Реализация Properties UPDATE

**Задачи:**
1. ✅ Реализовать метод `update_product_properties()` в `shopware_client.py`
2. ✅ Добавить логику DELETE старых properties (если append)
3. ✅ Добавить логику PATCH новых properties
4. ✅ Добавить guards от регрессий

**Результат:**
- Properties обновляются корректно при UPDATE
- Guards защищают от регрессий

### Этап 3: Реализация Variants (если нужны)

**Задачи:**
1. ✅ Создать pipeline для parent products
2. ✅ Создать pipeline для child products
3. ✅ Реализовать `configuratorSettings`
4. ✅ Добавить guards от регрессий

**Результат:**
- Variants работают корректно
- Parent/child структура создается правильно

### Этап 4: Тестирование

**Задачи:**
1. ✅ Тест CREATE с properties
2. ✅ Тест UPDATE с properties
3. ✅ Тест DELETE старых properties
4. ✅ Тест variants (если реализованы)

**Результат:**
- Все тесты проходят
- Properties pipeline считается каноническим и закрытым

---

## 8. Аналогия с Image Pipeline

### Image Pipeline (завершен)

**Проблема:**
- `coverId` был read-only при прямом PATCH
- Решение: associations.cover `{"cover": {"id": "..."}}`

**Порядок UPDATE:**
1. PATCH основных полей
2. PATCH customFields
3. DELETE старых product_media
4. CREATE новых product_media
5. PATCH cover (associations.cover)

**Guards:**
- Проверка формата cover (associations, не прямое поле)
- Предупреждение при обнаружении прямого `coverId`

### Properties Pipeline (план)

**Проблема:**
- Properties могут быть read-only при PATCH
- Properties могут append, а не replace
- Решение: требует исследования

**Порядок UPDATE (предположительный):**
1. PATCH основных полей
2. PATCH customFields
3. DELETE старых product_media
4. CREATE новых product_media
5. PATCH cover (associations.cover)
6. **DELETE старых properties (если append)**
7. **PATCH новых properties (или associations.properties)**

**Guards:**
- Проверка формата properties `[{"id": "..."}]`
- Предупреждение при обнаружении properties в основном PATCH
- Валидация в `update_product_properties()`

---

## 9. Вывод

**Текущее состояние:**
- ✅ Properties работают для CREATE
- ❌ Properties НЕ обновляются при UPDATE
- ❌ Variants не реализованы

**Риски (аналогично coverId):**
- Properties могут быть read-only при PATCH
- Properties могут append, а не replace
- Нужен associations-подход для properties (если read-only)

**Следующие шаги:**
1. **Исследование Properties при PATCH** (критично)
2. Реализация Properties UPDATE pipeline
3. Реализация Variants pipeline (если нужны)
4. Тестирование и фиксация

**План готов к реализации после исследования.**




