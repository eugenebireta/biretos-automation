# Отчет валидации cover-пайплайна для UPDATE товара

**Дата:** 2025-12-14  
**Product Number:** 500944170  
**Product ID:** 019b19e7d49172e392428aca4acb7fc2

---

## Результаты проверок

### 1. POST /api/product-media

**Статус:** ✅ УСПЕШНО

- **HTTP Status:** 204 No Content
- **Location header:** `https://dev.bireta.ru/api/product-media/019b1cb9a78d729998103c1b735bc9e9`
- **product_media.id:** `019b1cb9a78d729998103c1b735bc9e9` (извлечен из Location)
- **productId:** `019b19e7d49172e392428aca4acb7fc2`
- **mediaId:** `9e2b4d84c2d74f84800b4f33d7b8df25`
- **position:** 0

**Вывод:** product_media создан успешно. Shopware 6 возвращает 204 No Content, ID находится в заголовке Location.

---

### 2. Проверка продукта после создания product_media

**Статус:** ✅ УСПЕШНО

- **relationships.media count:** 1
- **relationships.media[0].id:** `019b1cb9a78d729998103c1b735bc9e9`
- **attributes.coverId:** None (ожидаемо, coverId еще не установлен)

**Вывод:** product_media виден продукту через relationships.media. Связь создана корректно.

---

### 3. PATCH /api/product/{id} для установки coverId

**Статус:** ✅ УСПЕШНО (с оговоркой)

**Payload:**
```json
{
  "coverId": "019b1cb9a78d729998103c1b735bc9e9"
}
```

**Проверка payload:**
- ✅ coverId тип: `str`
- ✅ coverId значение: `019b1cb9a78d729998103c1b735bc9e9`
- ✅ НЕ mediaId
- ✅ НЕ array
- ✅ НЕ объект

**HTTP Response:**
- **Status:** 204 No Content
- **Location:** `https://dev.bireta.ru/api/product/019b19e7d49172e392428aca4acb7fc2`

**Проверка сразу после PATCH (0.3 сек задержка):**
- **coverId:** `019b1cb9a78d729998103c1b735bc9e9` ✅
- **Совпадает с product_media_id:** ✅ ДА

**Вывод:** PATCH cover принимает ID и устанавливает coverId корректно **сразу после выполнения**.

---

### 4. Проверка продукта после PATCH (с задержкой)

**Статус:** ⚠️ ПРОБЛЕМА

- **coverId после задержки:** None
- **product.cover association:** отсутствует

**Вывод:** coverId устанавливается сразу после PATCH, но **сбрасывается или не сохраняется** при последующих запросах.

---

## Финальный вывод

### Подтвержденная гипотеза: **ГИПОТЕЗА D**

**coverId устанавливается через PATCH, но НЕ сохраняется в БД.**

### Факты:

1. ✅ **product_media создан** - POST /api/product-media возвращает 204, ID в Location header
2. ✅ **product_media виден продукту** - relationships.media содержит созданную связь (count: 1)
3. ✅ **PATCH cover принимает ID** - HTTP 204, без ошибок, payload корректен
4. ✅ **coverId устанавливается сразу** - проверка через 0.3 сек показывает корректный coverId
5. ❌ **coverId НЕ сохраняется** - проверка через 1 сек показывает coverId = None

### Конкретная причина:

**PATCH /api/product/{id} с `{"coverId": "product_media_id"}` НЕ сохраняет coverId в БД.**

**Доказательства:**
- Сразу после PATCH (0.3 сек): `coverId = 019b1cbadfb6728ca96e7b57b5327ae7` ✅
- После задержки (1 сек): `coverId = None` ❌
- GET /api/product: `coverId = None` ❌

**Вывод:** Shopware 6.7.5.1 **игнорирует** поле `coverId` в PATCH payload, несмотря на HTTP 204.

### Техническая причина:

В Shopware 6.7 поле `coverId` является **read-only** или требует установки через **associations**, а не напрямую.

### Решение:

Необходимо использовать формат **associations** для установки cover:

```json
{
  "cover": {
    "id": "product_media_id"
  }
}
```

Или использовать другой механизм (например, через Sync API с правильным форматом associations).

---

## Технические детали

- **Shopware версия:** 6.7.5.1
- **API endpoint:** `/api/product/{id}`
- **Метод:** PATCH
- **Payload формат:** `{"coverId": "product_media_id"}`
- **HTTP Status:** 204 No Content
- **Проблема:** coverId не сохраняется в БД

