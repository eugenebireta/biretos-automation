# Исправление установки cover через associations.cover

**Дата:** 2025-12-14

## Проблема

PATCH /api/product/{id} с `{"coverId": "product_media_id"}` не сохраняет coverId в БД в Shopware 6.7.5.1.

## Решение

Использование associations.cover вместо прямого поля coverId.

---

## Изменения

### 1. `src/clients/shopware_client.py`

#### Метод `set_product_cover()` (строка ~607)

**ДО:**
```python
payload = {"coverId": product_media_id}
```

**ПОСЛЕ:**
```python
payload = {
    "cover": {
        "id": product_media_id
    }
}
```

**Где используется:**
- UPDATE логика в `full_import.py` (строка ~850)
- CREATE логика через `set_product_media_and_cover()` (строка ~700)

---

## Где устанавливается cover

**UPDATE путь (full_import.py, строка ~847-853):**
```python
# ШАГ 3b: Устанавливаем coverId через PATCH /api/product/{id} с product_media.id
if first_product_media_id:
    time.sleep(0.2)
    client.set_product_cover(
        product_id=final_product_id,
        product_media_id=first_product_media_id
    )
```

**Метод:** `PATCH /api/product/{id}` с payload:
```json
{
  "cover": {
    "id": "product_media_id"
  }
}
```

**Выполняется:** После создания всех product_media, отдельным PATCH запросом.

---

## Проверка

Тест `test_cover_associations.py` подтвердил:
- ✅ coverId устанавливается сразу после PATCH
- ✅ coverId сохраняется после задержки (2 сек)
- ✅ Откат больше не происходит

---

## Результат

- ✅ coverId стабильно сохраняется
- ✅ media_count > 0
- ✅ Повторный UPDATE не сбрасывает cover
- ✅ Используется product_media.id (НЕ mediaId)
- ✅ PATCH выполняется ПОСЛЕ создания всех product_media
- ✅ НЕТ других PATCH продукта после установки cover




