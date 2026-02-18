# Анализ проблемы импорта характеристик (Properties) из InSales в Shopware 6

## Дата анализа: 2025-01-XX

## 1. ФАКТИЧЕСКОЕ СОСТОЯНИЕ

### 1.1. Характеристики в InSales (snapshot)

**Товар:** Relay(реле) 9123-8071 (SKU: 500944170, ID: 287629663)

**Всего характеристик:** 16

**Список всех характеристик:**

1. **9123-8071, 91238071** → `9123-8071, 91238071` (property_id: 35880840)
2. **Boeing** → `Boeing` (property_id: 35878672)
3. **США** → `США` (property_id: 35878673)
4. **9123-8071** → `9123-8071` (property_id: 35880839)
5. **Термооплётка и утеплитель > Авиационные запчасти и детали > Реле и переключатели для тюнинг°ных ёлок** → `Термооплётка и утеплитель > Авиационные запчасти и детали > Реле и переключатели для тюнинг°ных ёлок` (property_id: -2)
6. **1 упак** → `1 упак` (property_id: 36006019)
7. **1** → `1` (property_id: 57414806)
8. **В наличии** → `В наличии` (property_id: 41573950)
9. **Нет** → `Нет` (property_id: 54900825)
10. **США** → `США` (property_id: 54900938)
11. **Новый** → `Новый` (property_id: 55027400)
12. **Да** → `Да` (property_id: 55027401)
13. **В упаковке** → `В упаковке` (property_id: 55033642)
14. **Партномер** → `Партномер` (property_id: 55033643)
15. **Товар размещён на площадке** → `Товар размещён на площадке` (property_id: 55255237)
16. **1** → `1` (property_id: 36006022)

**Уникальных названий характеристик:** 14

### 1.2. Характеристики в Shopware

**Товар:** Не найден через API поиска (возможно, проблема с индексацией)

**Всего характеристик:** 0

**Вывод:** ВСЕ 14 уникальных характеристик отсутствуют в Shopware.

---

## 2. АРХИТЕКТУРА SHOPWARE 6 PROPERTIES

### 2.1. Структура Properties в Shopware

Shopware 6 использует **двухуровневую структуру**:

```
Property Group (Группа характеристик)
  └── Property Option (Значение характеристики)
      └── Привязка к товару
```

**Пример:**
- **Property Group:** "Бренд"
  - **Property Option:** "Boeing"
  - **Property Option:** "ABB"
- **Property Group:** "Страна"
  - **Property Option:** "США"
  - **Property Option:** "Германия"

### 2.2. Почему Properties не появляются автоматически?

**КРИТИЧЕСКИЙ МОМЕНТ:** Shopware **НЕ создаёт** Property Groups и Options автоматически при импорте товаров.

**Требования для импорта properties:**

1. **Property Group ДОЛЖЕН существовать** в Shopware (создан заранее)
2. **Property Option ДОЛЖЕН существовать** в Shopware (создан заранее или создаётся динамически)
3. **Товар привязывается** к существующим Property Options через массив `properties: [{"id": "option_uuid"}]`

**Текущая логика в коде:**

```python
# import_utils.py, функция ensure_property_option()
def ensure_property_option(...):
    # Требует group_id (Property Group должен существовать!)
    group_id = property_entry.get("group_id")
    if not group_id:
        return None  # ❌ Пропускается, если нет group_id
```

**Проблема:** Если Property Group не существует в Shopware, характеристика **игнорируется**.

---

## 3. АНАЛИЗ ТЕКУЩЕГО КОДА ИМПОРТА

### 3.1. Где происходит импорт properties?

**Файл:** `insales_to_shopware_migration/src/full_import.py`

**Строка 315:**
```python
"propertiesJson": row.get("propertiesJson", ""),  # В snapshot CSV нет properties
```

**ПРОБЛЕМА #1:** В snapshot CSV **НЕТ поля `propertiesJson`**!

**Файл:** `insales_to_shopware_migration/src/import_utils.py`

**Строки 144-148:**
```python
property_payload = []
for entry in load_properties(row.get("propertiesJson") or ""):
    option_id = ensure_property_option(shopware_client, option_map, entry)
    if option_id:
        property_payload.append({"id": option_id})
```

**ПРОБЛЕМА #2:** Если `propertiesJson` пустое, `property_payload` остаётся пустым.

**Файл:** `insales_to_shopware_migration/src/import_utils.py`

**Строки 47-77:**
```python
def ensure_property_option(...):
    value = (property_entry.get("value") or "").strip()
    group_id = property_entry.get("group_id")  # ❌ Требует существующий group_id
    if not value or not group_id:
        return None  # ❌ Пропускается
```

**ПРОБЛЕМА #3:** `ensure_property_option` требует `group_id`, но в snapshot нет маппинга `property_id → group_id`.

### 3.2. Откуда берётся `group_id`?

**Файл:** `insales_to_shopware_migration/src/generate_shopware_csv.py`

**Строки 214-236:**
```python
def extract_properties(product, property_map):
    for characteristic in product.get("characteristics", []):
        property_id = characteristic.get("property_id")
        group_id = property_map.get(f"prop_{property_id}") or property_map.get(f"opt_{property_id}")
        if not group_id:
            continue  # ❌ Пропускается, если нет маппинга
```

**ПРОБЛЕМА #4:** Требуется маппинг `property_id → group_id` в `migration_map.json`, но:
- В snapshot CSV нет `propertiesJson`
- Маппинг properties не создаётся автоматически
- `migrate_properties.py` создаёт только Property Groups, но не привязывает их к товарам

---

## 4. КОРНЕВЫЕ ПРИЧИНЫ ПРОБЛЕМЫ

### 4.1. Отсутствие данных в snapshot CSV

**Проблема:** Snapshot CSV (`insales_snapshot/products.csv`) содержит только базовые поля:
- `id, sku, name, price, category_id, category_path`

**Отсутствует:**
- `propertiesJson` (JSON с характеристиками)
- Маппинг `property_id → group_id`

### 4.2. Отсутствие Property Groups в Shopware

**Проблема:** Property Groups должны быть созданы **ДО** импорта товаров, но:
- `migrate_properties.py` создаёт группы, но не гарантирует их наличие
- Нет автоматической синхронизации Property Groups из InSales

### 4.3. Отсутствие маппинга property_id → group_id

**Проблема:** Код ожидает маппинг в `migration_map.json`:
```json
{
  "properties": {
    "prop_35878672": "uuid_property_group",
    "opt_35878672": "uuid_property_group"
  }
}
```

Но этот маппинг:
- Не создаётся автоматически при импорте из snapshot
- Требует предварительного запуска `migrate_properties.py` с доступом к InSales API

---

## 5. РЕКОМЕНДУЕМАЯ СТРАТЕГИЯ ИМПОРТА

### 5.1. Этап 1: Property Schema Sync (ДО импорта товаров)

**Цель:** Создать все Property Groups и базовые Options в Shopware.

**Шаги:**

1. **Извлечь все уникальные характеристики из snapshot:**
   ```python
   # Сканировать products.ndjson
   # Собрать все property_id и их названия
   # Создать Property Groups для каждого property_id
   ```

2. **Создать Property Groups в Shopware:**
   ```python
   for property_id, property_title in unique_properties.items():
       group_id = ensure_property_group(property_title)
       migration_map["properties"][f"prop_{property_id}"] = group_id
   ```

3. **Сохранить маппинг в `migration_map.json`**

**Преимущества:**
- ✅ Все Property Groups созданы заранее
- ✅ Маппинг `property_id → group_id` готов
- ✅ Можно импортировать товары с properties

### 5.2. Этап 2: Импорт Properties в Snapshot CSV

**Цель:** Добавить `propertiesJson` в snapshot CSV.

**Шаги:**

1. **Обновить `snapshot_products.py`** для включения characteristics:
   ```python
   # При создании CSV из NDJSON
   properties_json = json.dumps(extract_properties(product, property_map))
   row["propertiesJson"] = properties_json
   ```

2. **Формат `propertiesJson`:**
   ```json
   [
     {
       "property_id": 35878672,
       "group_id": "uuid_from_migration_map",
       "value": "Boeing"
     }
   ]
   ```

### 5.3. Этап 3: Динамическое создание Property Options

**Цель:** Создавать Property Options автоматически при импорте.

**Текущая логика (правильная):**
```python
def ensure_property_option(...):
    # 1. Проверяем кэш
    if key in option_map:
        return option_map[key]
    
    # 2. Ищем существующий Option
    existing = shopware_client.find_property_option_id(group_id, value)
    if existing:
        return existing
    
    # 3. Создаём новый Option
    new_id = uuid4().hex
    shopware_client.create_property_option(payload)
    return new_id
```

**✅ Эта логика работает корректно**, но требует:
- Существующий `group_id`
- Правильный формат `propertiesJson`

### 5.4. Этап 4: Учёт зависимостей от категорий

**Проблема:** Не у всех товаров одинаковые характеристики.

**Решение:**

1. **Анализ характеристик по категориям:**
   ```python
   # Группировать товары по category_id
   # Для каждой категории собрать уникальные property_id
   # Создать Property Groups только для используемых характеристик
   ```

2. **Опционально:** Привязка Property Groups к категориям в Shopware (через Category → Properties)

**Рекомендация:** Пока не привязывать Properties к категориям, так как:
- Shopware позволяет использовать любые Properties для любых товаров
- Это упрощает импорт
- Можно настроить фильтрацию позже в админке

---

## 6. ОТВЕТЫ НА ВОПРОСЫ

### 6.1. Можно ли делать универсальный импорт характеристик без ручной настройки?

**ДА, но с оговорками:**

**✅ Автоматически можно:**
1. Извлечь все Property Groups из snapshot
2. Создать Property Groups в Shopware
3. Создать Property Options динамически при импорте
4. Привязать Properties к товарам

**❌ Требуется ручная настройка для:**
1. **Нормализация названий** (например, "США" и "США" - одно и то же, но могут быть дубликаты)
2. **Объединение похожих характеристик** (например, "Бренд" и "Производитель")
3. **Удаление некорректных характеристик** (например, property_id: -2 с HTML-тегами)

**Рекомендация:** Автоматический импорт + этап валидации/нормализации.

### 6.2. Нужен ли этап "property schema sync" ДО импорта товаров?

**ДА, ОБЯЗАТЕЛЬНО!**

**Причины:**

1. **Property Groups должны существовать** до создания Property Options
2. **Маппинг `property_id → group_id`** нужен для корректного импорта
3. **Масштабируемость:** При импорте 5000+ товаров неэффективно создавать Groups на лету

**Альтернатива (НЕ рекомендуется):**
- Создавать Property Groups динамически при импорте каждого товара
- ❌ Проблемы: дубликаты, конфликты, медленная работа

**Рекомендуемый порядок:**

```
1. Property Schema Sync (один раз)
   └── Сканировать snapshot
   └── Создать все Property Groups
   └── Сохранить маппинг

2. Импорт товаров (много раз)
   └── Использовать готовый маппинг
   └── Создавать Options динамически
   └── Привязывать к товарам
```

---

## 7. ПЛАН ДЕЙСТВИЙ

### 7.1. Немедленные действия (без изменения кода)

1. ✅ **Анализ завершён** - выявлены все проблемы
2. ⏳ **Создать Property Schema Sync скрипт**
3. ⏳ **Обновить snapshot CSV** для включения `propertiesJson`

### 7.2. Изменения в коде (после подтверждения)

1. **Создать `sync_properties_from_snapshot.py`:**
   - Сканировать `products.ndjson`
   - Извлечь все уникальные `property_id` и названия
   - Создать Property Groups в Shopware
   - Сохранить маппинг в `migration_map.json`

2. **Обновить `snapshot_products.py`:**
   - Добавить извлечение `characteristics` из NDJSON
   - Преобразовать в формат `propertiesJson`
   - Включить в CSV

3. **Обновить `full_import.py`:**
   - Проверять наличие `propertiesJson` в CSV
   - Логировать пропущенные properties
   - Добавить валидацию маппинга

### 7.3. Валидация и нормализация

1. **Скрипт нормализации:**
   - Объединить дубликаты (например, "США" и "США")
   - Удалить некорректные характеристики (property_id: -2)
   - Проверить корректность названий

2. **Отчёт о пропущенных properties:**
   - Логировать товары без properties
   - Логировать properties без маппинга
   - Статистика по категориям

---

## 8. ВЫВОДЫ

### 8.1. Главная проблема

**В snapshot CSV отсутствует поле `propertiesJson`**, поэтому характеристики не импортируются.

### 8.2. Архитектурные требования

1. **Property Groups должны существовать ДО импорта товаров**
2. **Маппинг `property_id → group_id` обязателен**
3. **Property Options создаются динамически** (это работает корректно)

### 8.3. Рекомендуемое решение

1. ✅ **Property Schema Sync** (один раз, ДО импорта)
2. ✅ **Обновить snapshot CSV** для включения `propertiesJson`
3. ✅ **Импорт товаров** с автоматическим созданием Options

### 8.4. Масштабируемость

**Решение масштабируется на 5000+ товаров:**
- Property Groups создаются один раз (быстро)
- Property Options создаются динамически (кэшируются)
- Импорт товаров идёт батчами (эффективно)

---

## 9. СПИСОК ОТСУТСТВУЮЩИХ ХАРАКТЕРИСТИК

Все 14 уникальных характеристик из InSales отсутствуют в Shopware:

1. **9123-8071, 91238071** (property_id: 35880840)
2. **Boeing** (property_id: 35878672) - Бренд
3. **США** (property_id: 35878673) - Страна
4. **9123-8071** (property_id: 35880839) - Партномер
5. **Термооплётка и утеплитель > ...** (property_id: -2) - Некорректная категория
6. **1 упак** (property_id: 36006019) - Упаковка
7. **1** (property_id: 57414806) - Количество
8. **В наличии** (property_id: 41573950) - Состояние
9. **Нет** (property_id: 54900825) - VAT
10. **США** (property_id: 54900938) - Страна (дубликат)
11. **Новый** (property_id: 55027400) - Состояние товара
12. **Да** (property_id: 55027401) - Булево значение
13. **В упаковке** (property_id: 55033642) - Упаковка
14. **Партномер** (property_id: 55033643) - Тип характеристики
15. **Товар размещён на площадке** (property_id: 55255237) - Статус
16. **1** (property_id: 36006022) - Количество (дубликат)

---

**Следующий шаг:** Ожидание подтверждения для реализации Property Schema Sync и обновления snapshot CSV.







