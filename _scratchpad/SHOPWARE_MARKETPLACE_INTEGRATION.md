# Интеграция Shopware с Яндекс.Маркет и Wildberries

## Статус готовности данных

✅ **Shopware готов для интеграции с маркетплейсами:**

1. **Категории** - товары привязаны ко всем категориям из цепочки
2. **Properties (характеристики)** - все свойства товаров сохранены
3. **Медиа (фото)** - изображения товаров доступны через Media API
4. **Видимость** - товары привязаны к Sales Channels

## API Endpoints для экспорта

### Получение товаров
```
GET /api/product
GET /api/product/{id}
```

### Получение категорий с иерархией
```
GET /api/category
GET /api/category/{id}
```

### Получение свойств (properties)
```
GET /api/property-group
GET /api/property-group-option
```

### Получение медиа
```
GET /api/media/{id}
```

## Формат данных для экспорта

### Яндекс.Маркет (YML)

Требуемые поля:
- `name` - название товара
- `price` - цена
- `currencyId` - валюта (RUB)
- `categories` - массив категорий
- `properties` - характеристики
- `media` - изображения
- `description` - описание

Пример структуры:
```json
{
  "id": "product_id",
  "productNumber": "498271720",
  "name": "Переключатель ABB чёрный с фиксацией",
  "price": [{"currencyId": "b7d2554b0ce847cd82f3ac9bd1c0dfca", "gross": 455.00}],
  "categories": [
    {"id": "0f1349cbb19741a6ad4732f0949f9052"},
    {"id": "ca30b284b1f44a6c996a99d5edac0e0b"}
  ],
  "properties": [
    {"id": "property_option_id_1"},
    {"id": "property_option_id_2"}
  ],
  "media": [
    {"id": "media_id_1"}
  ]
}
```

### Wildberries API

Требуемые поля:
- `vendorCode` - артикул (productNumber)
- `name` - название
- `price` - цена
- `categoryId` - категория (нужен маппинг на категории WB)
- `characteristics` - характеристики (из properties)
- `photos` - фото (из media)

## Маппинг категорий

**Важно:** Категории Shopware нужно маппить на категории маркетплейсов:

1. **Яндекс.Маркет** - использует свою систему категорий
2. **Wildberries** - использует subjectId из их справочника

Рекомендация: создать таблицу маппинга:
- Shopware Category ID → Яндекс.Маркет Category ID
- Shopware Category ID → Wildberries Subject ID

## Следующие шаги

1. ✅ Данные в Shopware готовы (категории, properties, медиа)
2. ⏳ Создать скрипт экспорта в YML для Яндекс.Маркет
3. ⏳ Создать скрипт экспорта в формат Wildberries API
4. ⏳ Настроить маппинг категорий
5. ⏳ Настроить синхронизацию остатков и цен

## Полезные ссылки

- Shopware API Documentation: https://developer.shopware.com/docs/guides/integrations-api/
- Яндекс.Маркет API: https://yandex.ru/support/marketplace/
- Wildberries API: https://openapi.wildberries.ru/








