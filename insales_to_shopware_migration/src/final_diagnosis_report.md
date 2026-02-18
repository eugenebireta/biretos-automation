# ДИАГНОСТИКА: Сохранение mediaFolderId и configurationId в Shopware 6.6.10.7

## Версия Shopware
**Shopware 6.6.10.7** (env: prod, debug: false)

---

## ТЕСТ 1: Создание медиа с mediaFolderId

### Payload отправлен:
```json
{
  "id": "ca13702067b447f694b2a0e468e7e5a8",
  "mediaFolderId": "01994d23ada87207aa7d8cb9994f5198"
}
```

### Response:
`null` (успешный ответ)

### Результат GET /api/media/{id}:
- **mediaFolderId в attributes: `01994d23ada87207aa7d8cb9994f5198`**
- **Ожидалось: `01994d23ada87207aa7d8cb9994f5198`**
- **Сохранилось: `True` ✅**

### Вывод:
**`mediaFolderId` СОХРАНЯЕТСЯ при создании медиа через `POST /api/media`!**

---

## ТЕСТ 2: Обновление папки с configurationId через PATCH

### Payload отправлен:
```json
{
  "id": "01994d23ada87207aa7d8cb9994f5198",
  "configurationId": "84a2b8cd802c4b9f8129629ec74263de"
}
```

### Response:
Успешный (без ошибок)

### Результат GET /api/media-folder/{id}:
- **configurationId: `None`**
- **Ожидалось: `84a2b8cd802c4b9f8129629ec74263de`**
- **Сохранилось: `False` ❌**

### Вывод:
**PATCH `/api/media-folder/{id}` НЕ сохраняет `configurationId`**

---

## ТЕСТ 3: Обновление через Sync API

### Payload отправлен:
```json
[
  {
    "entity": "media_folder_configuration",
    "action": "upsert",
    "payload": [{
      "id": "20bb6126cfd64f2aabda769faf00a6d8",
      "thumbnailSizes": [...]
    }]
  },
  {
    "entity": "media_folder",
    "action": "upsert",
    "payload": [{
      "id": "01994d23ada87207aa7d8cb9994f5198",
      "name": {"ru-RU": "Product Media", ...},
      "configurationId": "20bb6126cfd64f2aabda769faf00a6d8"
    }]
  }
]
```

### Response:
**ОШИБКА 400**: `"This value should be of type string"` для поля `name`

### Вывод:
**Sync API требует `name` как строку, а не объект с переводами**

---

## ЗАКЛЮЧЕНИЕ

### 1. mediaFolderId
- ✅ **СОХРАНЯЕТСЯ** при создании медиа через `POST /api/media` с полем `mediaFolderId` в payload
- **Проблема в реальном импорте**: Возможно, `get_product_media_folder_id()` возвращает `None` или папка не найдена

### 2. configurationId
- ❌ **НЕ СОХРАНЯЕТСЯ** через `PATCH /api/media-folder/{id}`
- ⚠️ **Sync API требует другой формат** для `name` (строка вместо объекта)

### 3. Рекомендации
1. **Для mediaFolderId**: Убедиться, что `get_product_media_folder_id()` возвращает валидный ID перед созданием медиа
2. **Для configurationId**: Использовать Sync API с правильным форматом `name` (строка) или найти альтернативный метод

---

## ПРОВЕРКА РЕАЛЬНОГО ИМПОРТА

### get_product_media_folder_id() возвращает:
- **Результат: `01994d23ada87207aa7d8cb9994f5198`** ✅
- **Тип: `<class 'str'>`**
- **None? `False`**

### Вывод:
Метод работает корректно и возвращает валидный ID папки.

---

## СЛЕДУЮЩИЕ ШАГИ

1. ✅ **mediaFolderId сохраняется** при создании медиа - проблема не в API
2. ❌ **configurationId НЕ сохраняется** через PATCH - нужен альтернативный метод
3. ⚠️ **Sync API требует формат** `name` как строка (не объект с переводами)

### Рекомендации для исправления:

#### Для mediaFolderId:
- Убедиться, что `create_media(media_folder_id=...)` вызывается с валидным ID
- Проверить, не перезаписывается ли `mediaFolderId` после создания

#### Для configurationId:
- Использовать Sync API с правильным форматом:
  ```json
  {
    "entity": "media_folder",
    "action": "upsert",
    "payload": [{
      "id": "...",
      "name": "Product Media",  // СТРОКА, не объект!
      "configurationId": "..."
    }]
  }
  ```
- Или использовать прямой SQL UPDATE (если API не позволяет)

