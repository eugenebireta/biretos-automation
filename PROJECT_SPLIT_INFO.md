# 🔀 Разделение проектов Biretos Automation

**Дата:** 2025-11-17  
**Статус:** ✅ Разделение завершено

---

## 📦 Структура проектов

### 1. Brand Catalog Automation (изолированный проект)

**Путь:** `brand-catalog-automation/`  
**Задачи:** `brand-catalog-automation/.cursor/tasks.json`

**Функциональность:**
- Автоматизация обработки каталогов брендов
- Поиск HD-изображений через множество провайдеров
- Обогащение товаров описаниями и спецификациями
- HD-калибровка и курация источников
- Экспорт в InSales, Shopware, Excel

**Как использовать:**
```bash
# Открыть как отдельный проект
cursor brand-catalog-automation/

# Или в Cursor: File → Open Folder → brand-catalog-automation
```

📚 **Документация:** `brand-catalog-automation/DEV_NOTES_CATALOG_PROJECT.md`

---

### 2. Marketplace Automation (корневой проект)

**Путь:** `biretos-automation/` (корень)  
**Задачи:** `biretos-automation/.cursor/tasks.json` *(пока placeholder)*

**Функциональность (в разработке):**
- N8N workflows automation
- Marketplace Export (Shopware ↔ InSales)
- Health monitoring и auto-healing
- Deployment и rollback скрипты

**Статус:** Задачи будут добавлены на следующем этапе.

---

## 🎯 Зачем разделение?

### Преимущества:

1. **Изоляция контекста**  
   Brand Catalog работает независимо, без лишнего кода Marketplace.

2. **Быстрая работа Cursor**  
   Меньший scope проекта → быстрее индексация и навигация.

3. **Независимые задачи**  
   Каждый проект имеет свои `.cursor/tasks.json` без пересечений.

4. **Упрощённый deploy**  
   Brand Catalog можно деплоить отдельно на другой сервер.

---

## 🔄 Миграция задач

### Что было сделано:

✅ **Brand Catalog Automation:**
- Создан `brand-catalog-automation/.cursor/tasks.json` с 12 задачами
- Все задачи адаптированы под корень `brand-catalog-automation/`
- Удалены лишние `cd biretos-automation/brand-catalog-automation`
- Команды используют относительные пути (`scripts/`, `BrandCatalogs/`)

✅ **Корневой проект:**
- Очищен `biretos-automation/.cursor/tasks.json`
- Добавлен placeholder для будущих Marketplace задач
- Старые N8N задачи удалены (будут восстановлены позже)

❌ **Что НЕ трогалось:**
- Python-скрипты (без изменений)
- Batch-файлы (без изменений)
- Исходный код проектов
- Конфигурации и данные

---

## 📋 Список задач Brand Catalog

Теперь доступны в `brand-catalog-automation/.cursor/tasks.json`:

1. **🩺 Health Check** — проверка API ключей
2. **🆕 Setup Brand** — инициализация бренда
3. **🎨 Enrich Brand** — обогащение изображениями
4. **🎯 HD Calibration** — калибровка HD-источников
5. **🔍 Curate HD Sources** — курация источников
6. **📊 Export to Excel** — экспорт в Excel
7. **📤 Export to InSales CSV** — экспорт в CSV
8. **🛒 Export to Shopware** — экспорт в Shopware
9. **🚀 Full Pipeline** — полный pipeline
10. **📋 Catalog Deep Audit** — аудит качества
11. **🔧 Mass HD Calibration** — массовая калибровка
12. **🧪 Test System** — тестирование системы

---

## 🚀 Следующие шаги

1. ✅ **Brand Catalog изолирован** — можно работать отдельно
2. ⏳ **Marketplace tasks** — будут добавлены позже:
   - N8N AutoSync
   - N8N Watch Mode
   - Marketplace Health Check
   - Marketplace Export
   - Deploy/Rollback workflows

---

## 📞 Быстрая навигация

- **Brand Catalog:** [brand-catalog-automation/DEV_NOTES_CATALOG_PROJECT.md](brand-catalog-automation/DEV_NOTES_CATALOG_PROJECT.md)
- **Brand Catalog README:** [brand-catalog-automation/README.md](brand-catalog-automation/README.md)
- **Корневой README:** [README.md](README.md)

---

**Итог:** Brand Catalog Automation теперь полностью автономен и готов к работе! 🎉

