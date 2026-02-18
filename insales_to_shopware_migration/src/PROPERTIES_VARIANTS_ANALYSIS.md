# Анализ текущей логики Properties и Variants

**Дата:** 2025-12-14

---

## 1. Текущая логика Properties

### CREATE путь (`full_import.py`, строка ~657)

**Код:**
```python
# Properties добавляем ТОЛЬКО для новых товаров
# При обновлении пропускаем, чтобы не накапливать дубли (Shopware добавляет, не заменяет)
if not existing_id:
    payload["properties"] = [{"id": pid} for pid in property_option_ids]
```

**Формат:**
```json
{
  "properties": [
    {"id": "option_id_1"},
    {"id": "option_id_2"}
  ]
}
```

**Процесс создания:**
1. `process_characteristics()` создает Property Groups и Options
2. Возвращает список `property_option_ids`
3. Добавляется в payload при CREATE

### UPDATE путь

**Текущее поведение:** Properties **НЕ обновляются** при UPDATE
- Комментарий: "Shopware добавляет, не заменяет"
- Риск: Невозможно удалить старые properties или заменить их

---

## 2. Текущая логика Variants

### Анализ кода

**Используется только первый вариант:**
```python
variant = product_data.get("variants", [{}])[0] if product_data.get("variants") else {}
```

**Извлекаемые данные:**
- `variant.get("sku")` → `productNumber`
- `variant.get("price")` → `price[0].gross`
- `variant.get("quantity")` → `stock`
- `variant.get("weight")` → `weight`
- `variant.get("dimensions")` → `width`, `height`, `length`
- `variant.get("barcode")` → `customFields.internal_barcode`

**Отсутствует:**
- ❌ Создание child products (variants)
- ❌ `configuratorSettings`
- ❌ `parentId` / `child` associations
- ❌ Обработка множественных вариантов

---

## 3. Сопоставление с каноном Shopware 6.7

### Product Properties

**Shopware 6.7 структура:**
```json
{
  "properties": [
    {
      "id": "property_option_id"
    }
  ]
}
```

**Важно:**
- `properties` - это Many-to-Many связь через `product_property` таблицу
- При PATCH: Shopware может **добавлять** (append), а не **заменять** (replace)
- Нужно проверить, является ли `properties` read-only при PATCH

### Product Options / ConfiguratorSettings

**Shopware 6.7 структура:**
```json
{
  "options": [
    {
      "id": "property_option_id"
    }
  ],
  "configuratorSettings": [
    {
      "id": "configurator_setting_id",
      "optionId": "property_option_id",
      "price": [{"currencyId": "...", "gross": 0, "net": 0}]
    }
  ]
}
```

**Важно:**
- `options` - для parent products (товары с вариантами)
- `configuratorSettings` - связь между parent и вариантами
- `parentId` - для child products (вариантов)

---

## 4. Выявленные риски

### Риск 1: Properties при UPDATE (аналогично coverId)

**Проблема:**
- Properties добавляются ТОЛЬКО при CREATE
- При UPDATE properties не обновляются
- Комментарий: "Shopware добавляет, не заменяет"

**Вопросы:**
- ❓ Является ли `properties` read-only при PATCH?
- ❓ Нужен ли associations-подход: `{"properties": [{"id": "..."}]}`?
- ❓ Можно ли удалить старые properties через DELETE associations?

**Аналогия с coverId:**
- Если `properties` read-only → нужен associations-подход
- Если PATCH не заменяет → нужен явный DELETE старых + CREATE новых

### Риск 2: Options / ConfiguratorSettings

**Проблема:**
- Текущий код НЕ создает variants
- Нет обработки `options` и `configuratorSettings`
- Нет parent/child структуры

**Вопросы:**
- ❓ Нужны ли variants для текущего проекта?
- ❓ Если да → нужен отдельный pipeline для parent/child products
- ❓ `configuratorSettings` может быть read-only при PATCH?

### Риск 3: Порядок операций

**Текущий порядок UPDATE:**
1. PATCH основных полей
2. PATCH customFields
3. DELETE старых product_media
4. CREATE новых product_media
5. PATCH cover (associations.cover)

**Вопрос:**
- ❓ Где должны быть properties в этом порядке?
- ❓ Нужно ли DELETE старых properties перед CREATE новых?

---

## 5. План канонического pipeline

### CREATE путь (новый товар)

**Порядок операций:**
1. ✅ Создание Property Groups (если не существуют)
2. ✅ Создание Property Options (если не существуют)
3. ✅ Создание Media entities
4. ✅ POST product с:
   - Основными полями
   - `properties: [{"id": "..."}]` (если нужны)
   - `categories: [{"id": "..."}]`
   - `manufacturerId`
5. ✅ POST product-media (создание связей)
6. ✅ PATCH product cover (associations.cover)
7. ✅ PATCH product customFields

**Защита:**
- Guard: проверка, что `properties` не содержит прямых полей (только `{"id": "..."}`)

### UPDATE путь (существующий товар)

**Порядок операций:**
1. ✅ PATCH основных полей (БЕЗ properties, customFields, coverId)
2. ✅ PATCH customFields
3. ✅ DELETE старых product_media
4. ✅ CREATE новых product_media
5. ✅ PATCH cover (associations.cover)
6. ❓ **Properties UPDATE (требует исследования):**
   - Вариант A: DELETE старых properties → CREATE новых
   - Вариант B: PATCH с associations.properties (если read-only)
   - Вариант C: Оставить как есть (только CREATE, не UPDATE)

**Защита:**
- Guard: проверка, что `properties` не в основном PATCH payload
- Guard: проверка формата properties (только `{"id": "..."}`)

### Variants pipeline (если нужен)

**Порядок операций:**
1. ✅ Создание parent product (с `options`)
2. ✅ Создание `configuratorSettings` для parent
3. ✅ Создание child products (с `parentId`)
4. ✅ Связывание child с parent через `configuratorSettings`

**Защита:**
- Guard: проверка, что `parentId` не устанавливается напрямую (если read-only)
- Guard: проверка формата `configuratorSettings`

---

## 6. Критические вопросы для исследования

### Вопрос 1: Properties при PATCH

**Эксперимент:**
- PATCH product с `{"properties": [{"id": "new_id"}]}`
- Проверить: добавляются или заменяются properties?
- Если добавляются → нужен DELETE старых перед PATCH

### Вопрос 2: Properties read-only?

**Эксперимент:**
- PATCH product с `{"properties": [...]}`
- Проверить: сохраняются ли properties?
- Если нет → нужен associations-подход: `{"properties": [{"id": "..."}]}`

### Вопрос 3: Options / ConfiguratorSettings

**Эксперимент:**
- Создать parent product с `options`
- PATCH parent с новыми `options`
- Проверить: заменяются или добавляются?
- Если read-only → associations-подход

---

## 7. Рекомендации

### Приоритет 1: Properties UPDATE

**Проблема:** Текущий код не обновляет properties при UPDATE

**Решение:**
1. Исследовать поведение PATCH с properties
2. Если read-only → использовать associations
3. Если append → DELETE старых перед PATCH
4. Если replace → оставить как есть

### Приоритет 2: Guards от регрессий

**Добавить:**
- Guard в `full_import.py`: проверка формата properties
- Guard в `full_import.py`: предупреждение, если properties в основном PATCH
- Guard в `shopware_client.py`: валидация формата properties

### Приоритет 3: Variants (если нужны)

**Решение:**
- Определить, нужны ли variants для проекта
- Если да → создать отдельный pipeline для parent/child
- Если нет → оставить как есть (только первый вариант)

---

## 8. Следующие шаги

1. ✅ **Исследование Properties при PATCH:**
   - Создать тестовый скрипт
   - Проверить поведение Shopware 6.7
   - Определить, нужен ли associations-подход

2. ✅ **Исследование Options / ConfiguratorSettings:**
   - Если variants нужны → исследовать parent/child pipeline
   - Если нет → пропустить

3. ✅ **Реализация канонического pipeline:**
   - После исследования → реализовать правильный порядок
   - Добавить guards от регрессий
   - Протестировать на реальных данных

---

## Вывод

**Текущее состояние:**
- ✅ Properties работают для CREATE
- ❌ Properties НЕ обновляются при UPDATE
- ❌ Variants не реализованы

**Риски (аналогично coverId):**
- Properties могут быть read-only при PATCH
- Нужен associations-подход для properties
- Нужен DELETE старых properties перед CREATE новых

**План:**
1. Исследовать поведение Properties при PATCH
2. Реализовать канонический pipeline с guards
3. Протестировать на реальных данных




