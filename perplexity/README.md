# Perplexity Product Lookup

Независимый модуль для поиска и обогащения карточек товаров через Perplexity (OpenRouter). Код полностью изолирован внутри папки `perplexity` и не затрагивает остальную часть проекта `biretos-automation`.

## Установка

1. Создайте и активируйте виртуальное окружение (опционально):
   ```
   python -m venv .venv
   .\.venv\Scripts\activate  # Windows
   source .venv/bin/activate # macOS / Linux
   ```
2. Установите зависимости:
   ```
   pip install -r requirements.txt
   ```

## Настройка `.env`

1. Скопируйте файл `.env.example` в `.env`.
2. Заполните значение:
   ```
   OPENROUTER_API_KEY=sk-or-...
   ```
3. Ключ OpenRouter должен иметь доступ к модели `perplexity/sonar`.

## Запуск CLI

```
python -m scripts.lookup --brand ABB --pn PSR45-600-70
```

Скрипт загрузит `.env`, выполнит запрос и напечатает форматированный JSON.

> **Важно:** Запускайте как модуль (`python -m scripts.lookup`) для корректной работы импортов.

### Пример вывода

```
{
  "corrected_part_number": "PSR45-600-70",
  "model": "ABB PSR45 Softstarter",
  "product_type": "softstarter",
  "image_url": "https://example.com/psr45.jpg",
  "description": "Коммутационный модуль мягкого пуска 45 A для AC-53b нагрузок.",
  "raw": { ... полный ответ OpenRouter ... }
}
```

## Дополнительные заметки

- Модуль не использует компоненты основного проекта и может развёртываться отдельно.
- Для удобного запуска можно использовать задачу `🤖 Perplexity Lookup` из `tasks.json`.
- Любые дальнейшие улучшения (например, запись в Excel) следует реализовывать внутри текущей папки, не изменяя остальной монорепозиторий.

