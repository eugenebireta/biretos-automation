# Изменения архитектуры UPDATE в Shopware 6

## Дата: 2025-12-14

## Проблема
- `coverId` не устанавливался при UPDATE
- `customFields.internal_barcode` не сохранялся при UPDATE
- Использовался Sync API (не канонический способ)

## Решение
Реализован канонический media-pipeline для Shopware 6 согласно требованиям:
1. ✅ НЕ устанавливать `coverId` через основной PATCH продукта
2. ✅ Использовать REST API вместо Sync API
3. ✅ Обновлять `customFields` отдельным PATCH
4. ✅ Не использовать `versionId`

---

## Измененные файлы

### 1. `src/clients/shopware_client.py`

#### Добавленные методы:

**`create_product_media(product_id, media_id, position)`**
- Создает `product_media` связь через `POST /api/product-media`
- Возвращает `product_media_id`
- Канонический способ Shopware 6

**`set_product_cover(product_id, product_media_id)`**
- Устанавливает `coverId` через `PATCH /api/product/{id}`
- Принимает `product_media_id` (НЕ `media_id`!)
- Выполняется отдельным запросом

**`update_product_custom_fields(product_id, custom_fields)`**
- Обновляет `customFields` через отдельный `PATCH /api/product/{id}`
- Никогда не смешивается с media/cover update

#### Измененные методы:

**`set_product_media_and_cover()`**
- Помечен как DEPRECATED
- Оставлен для обратной совместимости с CREATE логикой
- Теперь использует новые методы `create_product_media()` + `set_product_cover()`

---

### 2. `src/full_import.py`

#### Изменения в логике UPDATE (строка ~768):

**ШАГ 1: Обновление основных полей товара**
- `PATCH /api/product/{id}` с основными полями
- **Убраны** `customFields` из payload (обновляются отдельно)

**ШАГ 2: Обновление customFields**
- Отдельный `PATCH /api/product/{id}` только для `customFields`
- Выполняется через `client.update_product_custom_fields()`
- Гарантирует сохранение `internal_barcode`

**ШАГ 3: Media-pipeline (канонический способ)**
- **ШАГ 3a:** Создание `product_media` через `POST /api/product-media`
  - Для каждого изображения вызывается `client.create_product_media()`
  - Сохраняется `product_media_id` первого изображения (position=0)
- **ШАГ 3b:** Установка `coverId` через `PATCH /api/product/{id}`
  - Вызывается `client.set_product_cover()` с `product_media_id`
  - Выполняется отдельным запросом после создания всех `product_media`

#### Изменения в payload (строка ~706):
- Убрано добавление `customFields` в основной payload
- Комментарий: "НЕ добавляем customFields в payload - они будут обновлены отдельным PATCH после UPDATE"

---

## Где устанавливается cover

**До изменений:**
- `coverId` устанавливался через Sync API в `set_product_media_and_cover()`
- Не сохранялся при UPDATE

**После изменений:**
- `coverId` устанавливается в **ШАГ 3b** логики UPDATE (строка ~850)
- Вызов: `client.set_product_cover(product_id, first_product_media_id)`
- Метод: `PATCH /api/product/{id}` с `{"cover": {"id": product_media_id}}` (associations.cover)
- Выполняется **отдельным запросом** после создания всех `product_media`
- **ВАЖНО:** Используется associations.cover, НЕ прямое поле coverId

---

## Порядок выполнения UPDATE

1. Загрузка изображений (если есть)
2. **PATCH product** (основные поля, БЕЗ customFields и coverId)
3. **PATCH product** (только customFields)
4. Удаление старых `product_media`
5. **POST product-media** (создание новых связей)
6. **PATCH product** (только cover через associations: `{"cover": {"id": product_media.id}}`)

---

## Требования выполнены

✅ **1. НЕ устанавливать coverId через основной PATCH** - выполняется отдельным PATCH  
✅ **2. Канонический media-pipeline:**
   - ✅ a) Создание media через `create_media()` (без изменений)
   - ✅ b) Создание связи через `POST /api/product-media`
   - ✅ c) Установка cover через `PATCH /api/product/{id}` с `{"cover": {"id": product_media.id}}` (associations.cover)  
✅ **3. customFields обновляются отдельным PATCH**  
✅ **4. Не используется versionId**  
✅ **5. Не используется Sync API** (только для CREATE, не для UPDATE)  
✅ **6. Логика CREATE не изменена**

---

---

## RULE: Shopware 6.7 cover MUST be set via associations.cover

**КРИТИЧЕСКОЕ ПРАВИЛО:** В Shopware 6.7 поле `coverId` является read-only при прямом PATCH.

### ✅ РАЗРЕШЕНО:
```json
{
  "cover": {
    "id": "product_media_id"
  }
}
```

### ❌ ЗАПРЕЩЕНО:
```json
{
  "coverId": "product_media_id"  // НЕ РАБОТАЕТ в Shopware 6.7!
}
```

### Причина:
- Прямое поле `coverId` в PATCH payload игнорируется Shopware 6.7
- Требуется использовать формат associations: `{"cover": {"id": "..."}}`
- Это единственный способ, который сохраняет `coverId` в БД

### Защита от регрессий:
- Метод `set_product_cover()` использует только associations.cover
- Прямое использование `{"coverId": "..."}` в payload запрещено
- При обнаружении прямого `coverId` в payload → WARNING/Exception

---

## AUTONOMOUS AI RULE

**Цель:** Автономная работа ИИ с минимальным участием человека. ИИ должен работать автономно и ОСТАНАВЛИВАТЬСЯ, если нарушен канон.

### Правила работы системы

#### 1. Правило подтверждения через GET

**Любой UPDATE считается успешным ТОЛЬКО если подтверждён через GET.**

Это означает:
- После UPDATE (`set_product_cover()`, `update_product_custom_fields()`) ОБЯЗАТЕЛЬНА проверка через GET API
- Если GET не подтверждает сохранение данных (`coverId`, `customFields`) — операция считается неуспешной
- Без подтверждения через GET операция НЕ считается успешной, даже если PATCH вернул 200 OK

#### 2. Правило непроверяемого результата

**Любой непроверяемый результат = False.**

- Если результат UPDATE нельзя проверить через GET API — возвращается `False`
- Если GET API недоступен или возвращает ошибку — возвращается `False`
- Если данные не сохранились, но причина неизвестна — возвращается `False`
- Никаких предположений об успехе без подтверждения

#### 3. Обработка False / ERROR

**При `False` или `Exception`:**

- ✅ **Останавливает обработку текущего товара** — переход к следующему товару без завершения текущего
- ✅ **Логируется как FAILED** — явная запись в лог с пометкой FAILED и причиной
- ✅ **НЕ приводит к silent retry** — повторные попытки без изменения условий ЗАПРЕЩЕНЫ
- ✅ **НЕ приводит к продолжению** — обработка текущего товара прерывается, следующий товар не начинается до разрешения проблемы

#### 4. Запрет "дожатия" операций

**ИИ не «дожимает» операции молча.**

- Повторные попытки UPDATE без изменения условий ЗАПРЕЩЕНЫ
- Попытки обойти проверку через GET ЗАПРЕЩЕНЫ
- Молчаливое игнорирование `False` ЗАПРЕЩЕНО
- Любые попытки "исправить" без явного указания причины ЗАПРЕЩЕНЫ

#### 5. Подключение человека

**Человек подключается ТОЛЬКО при FAILED / ERROR.**

- При успешном UPDATE (подтверждённом через GET) человек НЕ участвует
- При `False` или `Exception` система ОСТАНАВЛИВАЕТСЯ и эскалирует к человеку
- Человек получает явное уведомление о FAILED с указанием причины
- После разрешения проблемы человеком система продолжает работу

### Принцип работы

1. **AI исполняет** — выполняет UPDATE операцию (PATCH)
2. **Guards проверяют** — проверяют результат через GET API
3. **Guards решают** — если GET подтверждает — SUCCESS, если нет — FAILED
4. **При FAILED** — остановка, логирование, эскалация к человеку
5. **Человек подключается** — только при FAILED / ERROR для разрешения проблемы

### Результат применения правил

- ✅ **ИИ работает автономно** — успешные UPDATE выполняются без участия человека
- ✅ **Ошибки всегда видимы** — все FAILED логируются явно, нет silent failures
- ✅ **Человек не участвует в нормальном потоке** — только при аномалиях (FAILED / ERROR)
- ✅ **Система детерминированна** — каждый UPDATE либо подтверждён (SUCCESS), либо отклонён (FAILED)
- ✅ **Нет silent retry** — повторные попытки без изменения условий запрещены

---

## Тестирование

После изменений необходимо проверить:
- ✅ `coverId` установлен после UPDATE
- ✅ `customFields.internal_barcode` сохранен после UPDATE
- ✅ `product_media` связи созданы корректно
- ✅ Поведение подтверждено повторной проверкой через API
- ✅ `coverId` сохраняется стабильно (нет отката)
- ✅ При неуспешном подтверждении через GET операция считается неуспешной (False/Exception)

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

## Финальный статус Image Pipeline

**✅ CLOSED (ЗАКРЫТ)**

- ✅ CREATE работает корректно
- ✅ UPDATE работает корректно (не ломает фото)
- ✅ Cover устанавливается через associations.cover
- ✅ Существующие товары исправляются через fix_existing_products_media.py
- ✅ Повторный импорт не ломает фото

