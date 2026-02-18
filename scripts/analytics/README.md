# Analytics Scripts

Каталог содержит скрипты продвинутого анализа ассортимента и лотов. Все
оригинальные вызовы из корня проекта сохранены через совместимые шимирующие
файлы, поэтому старые команды (`python analyze_top_50_deep.py`) продолжают
работать.

| Скрипт | Назначение | Основные зависимости |
| --- | --- | --- |
| `analyze_top_50_deep.py` | Топ-50 позиций по стоимости в лотах Honeywell | `pandas`, `openpyxl` |
| `analyze_categories_deep.py` | Расширенная аналитика по категориям торгов | `pandas` |
| `analyze_extended_core.py` | Анализ расширенного "core" ассортимента | `pandas` |
| `analyze_honeywell_core.py` | Оценка ключевых позиций Honeywell | `pandas` |
| `analyze_remaining_lots.py` | Остаточные показатели по лотам | `pandas` |
| `compare_cores.py` | Сравнение двух выборок core-линий | `pandas` |
| `extract_honeywell_core.py` | Извлечение core-линий Honeywell из выгрузок | `pandas` |
| `find_global_top5.py` | Поиск глобального TOP-5 SKU по метрикам | `pandas` |
| `recalc_rubles.py` | Пересчёт стоимости лотов в рубли | `pandas` |
| `deep_analyze_14_16.py` | Глубокий анализ лотов №14 и №16 | `pandas`, `openpyxl` |

> Если потребуется добавить новую аналитику, помещайте скрипт сюда и при
> необходимости добавляйте краткое описание в таблицу.

