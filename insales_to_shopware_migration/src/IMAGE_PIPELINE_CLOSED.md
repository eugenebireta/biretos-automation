# Image Pipeline - Статус CLOSED

**Дата:** 2025-12-14  
**Статус:** ✅ **CLOSED (ЗАКРЫТ)**

---

## Статус

**Image pipeline полностью закрыт и зафиксирован.**

Все компоненты работают корректно:
- ✅ CREATE: media → product_media → cover через associations.cover
- ✅ UPDATE: DELETE старых product_media → CREATE новых → cover через associations.cover
- ✅ Повторный импорт не ломает фото
- ✅ Защита от регрессий установлена

---

## Канонический pipeline

### CREATE путь

1. Загрузка изображений из snapshot/CDN
2. CREATE media (в ROOT, mediaFolderId = NULL)
3. POST product (с основными полями)
4. POST product-media (создание связей)
5. PATCH cover через associations.cover: `{"cover": {"id": "product_media_id"}}`
6. PATCH customFields

### UPDATE путь

1. PATCH основных полей (БЕЗ properties, customFields, coverId)
2. PATCH customFields
3. DELETE старых product_media
4. CREATE новых media (если есть новые изображения)
5. POST product-media (создание новых связей)
6. PATCH cover через associations.cover: `{"cover": {"id": "product_media_id"}}`
7. DELETE старых properties + PATCH новых properties

**После установки cover НЕТ больше ни одного PATCH product.**

---

## Исправление фото у существующих товаров

**ВАЖНО:** Фото у существующих товаров исправляются **ТОЛЬКО через UPDATE**, не через DELETE товара.

### Правило

> **Old products without images must be fixed via `fix_existing_products_media.py`**

### Скрипт: `fix_existing_products_media.py`

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
- ❌ НЕ удаляет product
- ❌ НЕ меняет SKU / productNumber
- ❌ НЕ трогает properties, prices, categories
- ✅ ТОЛЬКО media, product_media, cover

---

## Защита от регрессий

### Guards в `full_import.py`

1. **Guard для coverId (строка ~790):**
   - Запрещает прямое поле `coverId` в payload
   - Выводит `UserWarning` и удаляет из payload

2. **Guard для properties (строка ~799):**
   - Запрещает `properties` в основном PATCH payload при UPDATE
   - Выводит `UserWarning` и удаляет из payload

### Guards в `shopware_client.py`

1. **Guard в `set_product_cover()` (строка ~630):**
   - Использует только associations.cover
   - Валидация `product_media_id`

2. **Guard в `update_product_properties()` (строка ~390):**
   - Валидация формата property_option_ids
   - Проверка пустоты после DELETE
   - Сверка множеств после UPDATE

---

## Результат

✅ **Image pipeline CLOSED**  
✅ **Повторный импорт не ломает фото**  
✅ **Существующие товары исправляются через fix_existing_products_media.py**  
✅ **Защита от регрессий установлена**  
✅ **Документация отражает реальное поведение Shopware 6.7**

---

## Документация

- `ARCHITECTURE_FINALIZED.md` - финальная фиксация
- `UPDATE_ARCHITECTURE_CHANGES.md` - изменения архитектуры UPDATE
- `COVER_ASSOCIATIONS_FIX_CONFIRMED.md` - подтверждение исправления cover
- `IMAGE_PIPELINE_CLOSED.md` - этот файл (статус CLOSED)




