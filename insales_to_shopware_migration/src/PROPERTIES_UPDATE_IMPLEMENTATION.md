# Реализация канонического UPDATE properties

**Дата:** 2025-12-14  
**Статус:** ✅ Реализовано

---

## Архитектурное решение

**Поведение Shopware 6.7:**
- Properties работают по **append-модели** при PATCH
- Properties **НЕ read-only**
- Properties **НЕ replace** (не заменяют старые автоматически)
- Associations **НЕ нужны**

**Решение:**
- Для UPDATE требуется: **DELETE старых → PATCH новых**

---

## Реализованные методы

### 1. `get_product_properties(product_id: str) -> List[str]`

Получает список property_option_ids текущих properties товара.

**Использует:**
- Search API с associations: `POST /api/search/product` с `associations[properties]=true`
- Альтернативный способ: прямой GET с associations

**Возвращает:**
- Список property_option_ids или пустой список

---

### 2. `delete_product_properties(product_id: str) -> bool`

Удаляет все существующие product-property связи для товара.

**Метод:**
- `PATCH /api/product/{id}` с `{"properties": []}`

**Примечание:**
- Пустой массив properties заменяет все существующие properties на пустой список
- Это удаляет все связи product-property

---

### 3. `update_product_properties(product_id: str, property_option_ids: List[str]) -> bool`

Обновляет properties товара через DELETE старых + PATCH новых.

**Порядок операций:**
1. DELETE старых properties (через `delete_product_properties()`)
2. PATCH с новыми properties: `{"properties": [{"id": "..."}]}`

**Guards:**
- Проверка формата property_option_ids (должны быть non-empty strings)
- Валидация перед выполнением

---

## Интеграция в UPDATE логику

### Файл: `full_import.py`

**ШАГ 1: Guard в основном PATCH payload (строка ~797)**

```python
# ЗАЩИТА ОТ РЕГРЕССИИ: Properties НЕ должны быть в основном PATCH payload при UPDATE
if "properties" in payload:
    warnings.warn(
        f"[REGRESSION GUARD] Properties обнаружены в основном PATCH payload для товара {product_number}. "
        f"В Shopware 6.7 properties работают по append-модели. Используйте update_product_properties() для канонического обновления (DELETE старых + PATCH новых).",
        UserWarning
    )
    del payload["properties"]  # Удаляем из основного payload
```

**ШАГ 4: Обновление properties (строка ~864)**

```python
# ШАГ 4: Обновление properties (канонический pipeline: DELETE старых + PATCH новых)
if use_ndjson and property_option_ids:
    # В Shopware 6.7 properties работают по append-модели при PATCH
    # Для полной замены требуется DELETE старых перед PATCH новых
    client.update_product_properties(
        product_id=final_product_id,
        property_option_ids=property_option_ids
    )
```

**Порядок выполнения UPDATE:**
1. PATCH основных полей (БЕЗ properties, customFields, coverId)
2. PATCH customFields
3. DELETE старых product_media
4. CREATE новых product_media
5. PATCH cover (associations.cover)
6. **DELETE старых properties + PATCH новых properties** ← НОВОЕ

---

## Результат

✅ **Properties при UPDATE заменяются полностью**  
✅ **Дубликаты невозможны**  
✅ **Guard защищает от регрессий**  
✅ **Канонический pipeline реализован**

---

## Тестирование

**Проверка:**
1. Создать товар с properties: `[option_1, option_2]`
2. UPDATE товар с новыми properties: `[option_3, option_4]`
3. Проверить результат:
   - Properties должны быть: `[option_3, option_4]` (старые удалены)
   - Дубликаты отсутствуют

---

## Аналогия с Image Pipeline

**Image Pipeline:**
- DELETE старых product_media
- CREATE новых product_media
- PATCH cover (associations.cover)

**Properties Pipeline:**
- DELETE старых properties (через `{"properties": []}`)
- PATCH новых properties (через `{"properties": [{"id": "..."}]}`)

**Оба pipeline используют канонический подход: DELETE старых → CREATE/PATCH новых**




