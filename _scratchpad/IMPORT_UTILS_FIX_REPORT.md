# Исправление import_utils.py для корректной установки mainCategory

## ✅ Выполненные изменения

### 1. Убрана прямая отправка `mainCategoryId` в product payload
- **Было:** `payload["mainCategoryId"] = main_category_id`
- **Стало:** `mainCategoryId` используется только как источник для `visibilities.categoryId`

### 2. Добавлена логика установки `categoryId` в visibilities
- Определяется storefront sales channel по типу
- Для storefront sales channel в visibility добавляется `categoryId = mainCategoryId`
- Для остальных sales channels создаются обычные visibilities без `categoryId`

## 📋 Как проверить

### Шаг 1: Создать тестовый товар
```bash
cd insales_to_shopware_migration/src
python test_import.py --limit 1
```

### Шаг 2: Получить product ID созданного товара
Из вывода скрипта или через Shopware Admin API.

### Шаг 3: Проверить visibilities
```bash
python _scratchpad/verify_new_product_visibilities.py <product_id>
```

### Шаг 4: Проверить в Shopware API напрямую
```python
GET /api/product/{product_id}/visibilities
```

**Ожидаемый результат:**
- Для storefront sales channel: `{"salesChannelId": "...", "visibility": 30, "categoryId": "<mainCategoryId>"}`
- Для других sales channels: `{"salesChannelId": "...", "visibility": 30}` (без `categoryId`)

### Шаг 5: Проверить на сайте
Откройте карточку товара на сайте и проверьте:
- Breadcrumbs: `Каталог → Электрика → ... → Переключатели` (полный путь)
- Категория в карточке товара отображается корректно

## 🔍 Что изменилось в коде

### Файл: `insales_to_shopware_migration/src/import_utils.py`

**Строки 172-174:**
```python
# Получаем mainCategoryId для установки через visibilities.categoryId
# НЕ отправляем mainCategoryId напрямую в product payload - это не работает
main_category_id = row.get("mainCategoryId")
```

**Строки 188-230:**
- Определение storefront sales channel
- Формирование visibilities с `categoryId` для storefront
- Сохранение других visibilities без изменений

## ⚠️ Важно

- `mainCategoryId` **НЕ** отправляется напрямую в product payload
- `mainCategory` устанавливается **ТОЛЬКО** через `visibilities.categoryId` для storefront sales channel
- Для старых товаров используйте `bulk_update_all_products.py`

## 🎯 Ожидаемый результат

После создания нового товара:
- ✅ `categoryId` установлен в visibility для storefront
- ✅ Breadcrumbs корректны (полный путь категорий)
- ✅ Категория в карточке товара отображается правильно
- ✅ `bulk_update` не требуется для новых товаров








