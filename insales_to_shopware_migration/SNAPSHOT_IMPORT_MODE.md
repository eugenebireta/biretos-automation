# Режим импорта из SNAPSHOT

## Обзор

Система импорта переведена в режим **SNAPSHOT-only** - полное отключение InSales API и использование только локальных файлов snapshot для импорта товаров в Shopware.

## Изменения

### 1. Защита от использования InSales API

**Файл**: `src/clients/insales_client.py`

- При попытке создать `InsalesClient` в режиме `snapshot` выбрасывается `RuntimeError`
- Режим контролируется через переменную окружения `INSALES_SOURCE` или аргумент CLI `--source`
- Защита срабатывает при любом импорте или использовании `InsalesClient`

```python
# Защита в InsalesClient.__init__
if _SNAPSHOT_MODE:
    raise RuntimeError(
        "InSales API отключён в режиме SNAPSHOT. "
        "Используйте локальные файлы из insales_snapshot/ для импорта."
    )
```

### 2. Импорт только из Snapshot CSV

**Файл**: `src/full_import.py`

**Изменения:**
- По умолчанию используется `--source snapshot`
- CSV читается из `insales_snapshot/products.csv`
- Поддержка формата snapshot CSV (id, sku, name, price, category_id, category_path)
- Автоматическое преобразование полей snapshot в формат для Shopware

**CLI аргументы:**
```bash
--source {snapshot,api}    # Источник данных (по умолчанию: snapshot)
--csv PATH                 # Путь к CSV (по умолчанию: snapshot CSV)
--limit N                  # Ограничение количества товаров
--dry-run-products         # Режим проверки без изменений
--timeout SECONDS          # Timeout для Shopware API (по умолчанию: 10s)
```

### 3. Timeout для Shopware API

**Файл**: `src/clients/shopware_client.py`

- Timeout по умолчанию изменён с 30s на **10s**
- Можно переопределить через `--timeout` аргумент
- Логирование каждого API вызова Shopware через `LOG.info`

### 4. Dry-run режим

- Полностью безопасный режим без сетевых запросов для создания товаров
- В dry-run не проверяется существование товаров (для скорости)
- Только вывод информации о товарах и категориях

## Использование

### Быстрый импорт 10 товаров (dry-run)

```bash
cd insales_to_shopware_migration/src
python full_import.py --source snapshot --limit 10 --dry-run-products
```

### Реальный импорт из snapshot

```bash
python full_import.py --source snapshot --limit 100
```

### Импорт всех товаров из snapshot

```bash
python full_import.py --source snapshot
```

### Использование API режима (если нужно)

```bash
# Установить переменную окружения
export INSALES_SOURCE=api

# Или через CLI
python full_import.py --source api --csv output/products_import.csv
```

## Структура Snapshot CSV

Snapshot CSV имеет следующие поля:
- `id` - ID товара из InSales
- `sku` - SKU товара (используется как productNumber)
- `name` - Название товара
- `price` - Цена товара
- `category_id` - ID категории
- `category_path` - Путь категории

Система автоматически преобразует эти поля в формат, ожидаемый Shopware:
- `sku` → `productNumber`
- `category_id` → `categoryIds` (с проверкой leaf-категории)
- `price` → используется для создания цены в валюте Shopware
- `stock` → по умолчанию 0 (в snapshot нет данных о складе)
- `active` → по умолчанию 1 (товар активен)

## Гарантии безопасности

✅ **Категории не трогаются** - импортируются только товары
✅ **Только leaf-категории** - товары импортируются только в листовые категории
✅ **mainCategoryId обязателен** - всегда устанавливается при создании/обновлении товара
✅ **InSales API отключён** - никаких обращений к InSales при `--source snapshot`
✅ **Быстрые таймауты** - 10s timeout предотвращает зависания
✅ **Dry-run безопасен** - полная проверка без изменений

## Проверка работы

1. **Тест защиты InSales API:**
```bash
python -c "import os; os.environ['INSALES_SOURCE']='snapshot'; from clients import InsalesClient, InsalesConfig; InsalesClient(InsalesConfig('test','key','pass'))"
# Должна быть ошибка: RuntimeError: InSales API отключён в режиме SNAPSHOT
```

2. **Тест dry-run импорта:**
```bash
python full_import.py --source snapshot --limit 10 --dry-run-products
# Должно пройти быстро без сетевых запросов для создания товаров
```

3. **Тест реального импорта:**
```bash
python full_import.py --source snapshot --limit 5
# Должен импортировать 5 товаров в Shopware
```

## Обратная совместимость

- Режим `--source api` сохранён для обратной совместимости
- Если `--source api`, система использует старую логику с InSales API
- По умолчанию используется `--source snapshot` для безопасности







