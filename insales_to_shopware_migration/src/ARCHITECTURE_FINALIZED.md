# Архитектура Image Pipeline - Финальная фиксация

**Дата:** 2025-12-14  
**Статус:** ✅ CLOSED (ЗАКРЫТ)

---

## Канон установлен

### RULE: Shopware 6.7 cover MUST be set via associations.cover

**КРИТИЧЕСКОЕ ПРАВИЛО:** В Shopware 6.7 поле `coverId` является read-only при прямом PATCH.

#### ✅ РАЗРЕШЕНО:
```json
{
  "cover": {
    "id": "product_media_id"
  }
}
```

#### ❌ ЗАПРЕЩЕНО:
```json
{
  "coverId": "product_media_id"  // НЕ РАБОТАЕТ в Shopware 6.7!
}
```

---

## Защита от регрессий

### 1. Guard в `full_import.py` (строка ~790)

При обнаружении прямого `coverId` в payload:
- Выводится `UserWarning`
- Поле автоматически удаляется из payload
- Предотвращает случайное использование неправильного формата

### 2. Guard в `set_product_cover()` (строка ~630)

Дополнительная проверка в методе:
- Валидация `product_media_id`
- Проверка, что payload не содержит прямое поле `coverId`
- `ValueError` при нарушении правил

---

## Финальная валидация

**Тест:** `final_validation_update.py`  
**Результат:** ✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ

### Проверки:
- ✅ `media_count > 0`: True (5 media)
- ✅ `coverId установлен`: True (`019b1cd191c87182900499d201aae35a`)
- ✅ `customFields.internal_barcode сохранён`: True (`9441705`)

### Вывод:
**Image pipeline считается каноническим и закрытым**

---

## Где устанавливается cover

**Файл:** `insales_to_shopware_migration/src/full_import.py`  
**Строка:** ~847-853 (ШАГ 3b в UPDATE логике)

**Метод:** `client.set_product_cover()`  
**Реализация:** `src/clients/shopware_client.py`, строка ~607-641

**Payload:**
```json
{
  "cover": {
    "id": "product_media_id"
  }
}
```

---

## Порядок выполнения UPDATE

1. Загрузка изображений (если есть)
2. **PATCH product** (основные поля, БЕЗ customFields и coverId)
3. **PATCH product** (только customFields)
4. Удаление старых `product_media`
5. **POST product-media** (создание новых связей)
6. **PATCH product** (только cover через associations: `{"cover": {"id": product_media.id}}`)

**После установки cover НЕТ больше ни одного PATCH product**

---

## Результат

✅ **coverId стабильно сохраняется**  
✅ **media_count > 0**  
✅ **Повторный UPDATE не сбрасывает cover**  
✅ **Используется product_media.id (НЕ mediaId)**  
✅ **PATCH выполняется ПОСЛЕ создания всех product_media**  
✅ **НЕТ других PATCH product после установки cover**  
✅ **Защита от регрессий установлена**  
✅ **Документация отражает реальное поведение Shopware**  

---

## Документация

- `UPDATE_ARCHITECTURE_CHANGES.md` - обновлена с правилом associations.cover
- `COVER_ASSOCIATIONS_FIX_CONFIRMED.md` - подтверждение исправления
- `ARCHITECTURE_FINALIZED.md` - этот файл (финальная фиксация)

---

## Статус

**✅ Image pipeline CLOSED (ЗАКРЫТ)**

Повторный UPDATE не может сломать cover благодаря:
- Использованию associations.cover
- Защите от регрессий
- Каноническому порядку выполнения операций

---

## Исправление фото у существующих товаров

**ВАЖНО:** Фото у существующих товаров исправляются **ТОЛЬКО через UPDATE**, не через DELETE товара.

### Для товаров, импортированных до фиксации pipeline:

**Скрипт:** `fix_existing_products_media.py`

**Использование:**
```bash
# Для одного товара
python fix_existing_products_media.py --product-number 500944170

# Для нескольких товаров
python fix_existing_products_media.py --limit 10

# Для всех товаров
python fix_existing_products_media.py
```

**Что делает:**
1. DELETE существующие product_media (НЕ product!)
2. Загружает изображения из snapshot
3. CREATE product_media через канонический pipeline
4. Устанавливает cover через associations.cover
5. Проверяет результат (media_count > 0, coverId установлен)

**Ограничения:**
- НЕ удаляет product
- НЕ меняет SKU / productNumber
- НЕ трогает properties, prices, categories

**Правило:**
> **Old products without images must be fixed via `fix_existing_products_media.py`**

---

## Финальный статус

**Image pipeline полностью закрыт:**
- ✅ CREATE работает корректно
- ✅ UPDATE работает корректно (не ломает фото)
- ✅ Cover устанавливается через associations.cover
- ✅ Существующие товары исправляются через fix_existing_products_media.py
- ✅ Повторный импорт не ломает фото

