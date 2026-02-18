# Каноническая модель импорта InSales → Shopware 6

## Обзор

Данный документ фиксирует **каноническую модель** импорта товаров из InSales в Shopware 6 для проекта Biretos Automation. Модель подтверждена тестированием и должна соблюдаться во всех импортах.

## Каноническая модель Categories / Visibilities / Prices

### 1. Categories (Категории)

**Каноническое состояние:**
- `product.categories.length > 0` — товар должен быть привязан хотя бы к одной категории
- Полная цепочка категорий от root до leaf должна быть в `product.categories`
- Leaf категория определяется как самая глубокая категория в цепочке

**КРИТИЧЕСКОЕ ОГРАНИЧЕНИЕ Shopware 6 REST API:**
- **Shopware 6 REST API НЕ сохраняет `visibility.categoryId`** через `POST /api/product-visibility` или `PATCH /api/product-visibility`
- Это **системное ограничение Shopware 6**, а не баг проекта
- Breadcrumb определяется внутренней логикой storefront на основе `product.categories`
- **ПРОВЕРКА `visibility.categoryId` ЗАПРЕЩЕНА в проекте**

**Проверка Categories считается OK, если:**
1. `product.categories.length > 0`
2. Есть ровно 1 visibility с:
   - `salesChannelId == storefront`
   - `visibility == 30`

**Реализация:**
- Обновление categories: `PATCH /api/product/{id}` с `{"categories": [{"id": "..."}, ...]}`
- Проверка: `GET /api/product/{id}?associations[categories]=`

### 2. Visibilities (Видимость товара)

**Каноническое состояние:**
- Ровно 1 запись `product-visibility` для storefront sales channel
- `salesChannelId == storefront_sales_channel_id`
- `visibility == 30` (видимый в каталоге и поиске)
- `categoryId` передается в payload, но Shopware его игнорирует (см. ограничение выше)

**Реализация:**
- Создание: `POST /api/product-visibility` с `{"productId": "...", "salesChannelId": "...", "visibility": 30, "categoryId": "..."}`
- Проверка: `POST /api/search/product-visibility` с фильтром по `productId`

**ВАЖНО:** Не пытаться обновлять `categoryId` через `PATCH /api/product-visibility` — Shopware его не сохранит.

### 3. Prices (Цены)

**Каноническое состояние:**
- Ровно 1 advanced price с правилом "Marketplace Price"
- `ruleId == marketplace_rule_id` (правило "Marketplace Price")
- `quantityStart == 1`
- Цена берется из `variant.price2` из InSales

**Реализация:**
- Создание: `POST /api/product-price` с `{"productId": "...", "ruleId": "...", "quantityStart": 1, "price": [...]}`
- Проверка: `POST /api/search/product-price` с фильтром по `productId`

### 4. Другие обязательные поля

- **manufacturerNumber**: Извлекается из `product.characteristics[]` (property "Партномер", property_id=35880840)
- **ean (GTIN/EAN)**: Должен быть `NULL` / пустым
- **customFields.internal_barcode**: Штрих-код из `variant.barcode`
- **Tax**: Должен быть "Standard rate" (19%)
- **Manufacturer**: Название производителя, без дублей

## Скрипты проверки и обновления

### `verify_product_state.py`

Скрипт для проверки фактического состояния товара в Shopware 6.

**Использование:**
```bash
python src/verify_product_state.py <SKU>
```

**Ожидаемый результат:**
- 8/8 OK в детальном чеклисте
- Categories: OK (при выполнении условий из раздела "Categories" выше)

**ВАЖНО:** Скрипт **НЕ проверяет** `visibility.categoryId` — это запрещено канонической моделью.

### `force_update_canonical.py`

Скрипт для принудительного обновления товара до канонического состояния.

**Использование:**
```bash
python src/force_update_canonical.py <SKU>
```

**Выполняет:**
1. Обновление categories с учетом `navigationCategoryId` из storefront sales channel
2. Создание visibility (Storefront, visibility=30)
3. Создание marketplace price

**ВАЖНО:** Скрипт передает `categoryId` в payload visibility, но Shopware его не сохраняет — это нормально.

## История изменений

- **2024**: Зафиксирована каноническая модель после подтверждения ограничения Shopware 6 REST API
- Убрана проверка `visibility.categoryId` из всех скриптов
- Добавлены комментарии TODO-BLOCK в местах, где раньше проверялся `categoryId`

## Запрещенные практики

❌ **НЕ проверять** `visibility.categoryId` в коде  
❌ **НЕ пытаться** обновлять `visibility.categoryId` через PATCH  
❌ **НЕ добавлять** retry/workaround для сохранения `categoryId`  
❌ **НЕ считать** отсутствие `visibility.categoryId` ошибкой  

## Разрешенные практики

✅ Проверять `product.categories.length > 0`  
✅ Проверять наличие валидной visibility (Storefront, visibility=30)  
✅ Использовать `product.categories` для определения breadcrumb  
✅ Передавать `categoryId` в payload visibility (для совместимости, даже если Shopware его игнорирует)  

## Контакты

При возникновении вопросов о канонической модели обращаться к документации Shopware 6 API или к разработчикам проекта.

---

**Документ зафиксирован и не подлежит изменению без обсуждения с командой проекта.**

