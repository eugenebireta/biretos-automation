# Исправление: mainCategory через visibilities

## Проблема

В Shopware 6 `mainCategory` товара задаётся **ТОЛЬКО** через `visibilities` с полем `categoryId`, а не напрямую через поле `mainCategoryId` в product payload.

## Решение

Обновлён `bulk_update_all_products.py` для правильной установки `mainCategory` через `visibilities`.

## Изменения

### 1. Определение Storefront Sales Channel

- ✅ В начале скрипта определяется `STOREFRONT_SALES_CHANNEL_ID`
- ✅ Поиск Sales Channel типа "Storefront" через API
- ✅ FATAL ERROR, если storefront не найден

### 2. Преобразование mainCategoryId → visibilities

Для каждого товара:
- ✅ Получение существующих visibilities через `/api/product/{id}/visibilities`
- ✅ Поиск visibility для storefront sales channel
- ✅ Если найдена: обновление `categoryId` (сохранение `visibility` level)
- ✅ Если не найдена: создание новой visibility с `categoryId = mainCategoryId`
- ✅ Сохранение всех других visibilities без изменений

### 3. Обновление payload

- ✅ `mainCategoryId` **НЕ отправляется** в product payload
- ✅ Отправляется только обновлённый список `visibilities`
- ✅ Формат: `{"id": productId, "visibilities": [...]}`

### 4. Валидация

- ✅ Проверка: `mainCategoryId` должен входить в `categories` товара
- ✅ ERROR, если `mainCategoryId` отсутствует в categories
- ✅ WARNING, если API вернул 200, но visibility не изменилась

### 5. Логирование

Для каждого товара:
- ✅ `[OK] productNumber → mainCategory set via visibility (updated/created)`
- ✅ `[SKIP] productNumber → mainCategory already correct`
- ✅ `[FAIL] productNumber → reason`

## Структура visibility

```json
{
  "salesChannelId": "<storefront_id>",
  "visibility": 30,
  "categoryId": "<mainCategoryId>"
}
```

## Ожидаемый результат

После выполнения:
- ✅ `mainCategory` товара корректно задан через visibility
- ✅ Breadcrumbs в карточке товара станут глубокими
- ✅ Категория в карточке: `Каталог → Электрика → … → Переключатели`
- ✅ Навигация и SEO станут корректными

## Архитектурные правила (соблюдены)

- ❌ НЕ отправляется `mainCategoryId` напрямую в product payload
- ❌ НЕ удаляются существующие visibilities
- ❌ НЕ трогаются категории товара
- ✅ Используется `mainCategoryId` ТОЛЬКО как источник для `visibilities.categoryId`








