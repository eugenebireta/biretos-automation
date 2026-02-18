from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from clients import InsalesClient, InsalesClientError, InsalesConfig

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
LOG = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
SNAPSHOT_DIR = ROOT / "insales_snapshot"
CATEGORIES_WITH_PATHS_PATH = SNAPSHOT_DIR / "categories_with_paths.json"
CATEGORY_ID_TO_PATH_PATH = SNAPSHOT_DIR / "category_id_to_path.json"

# Максимальное количество попыток при ошибках
MAX_RETRIES = 5
# Базовое время ожидания при retry (секунды)
BASE_BACKOFF = 1.0
# Максимальное время ожидания (секунды)
MAX_BACKOFF = 60.0


def load_config(path: Path) -> Dict[str, Any]:
    """Загружает конфигурацию из JSON файла."""
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open("r", encoding="utf-8") as handler:
        return json.load(handler)


def retry_with_backoff(
    func,
    *args,
    max_retries: int = MAX_RETRIES,
    base_backoff: float = BASE_BACKOFF,
    max_backoff: float = MAX_BACKOFF,
    **kwargs,
) -> Any:
    """
    Выполняет функцию с повторными попытками и экспоненциальным backoff.
    
    Обрабатывает:
    - 429 (Too Many Requests)
    - 5xx (Server Errors)
    - InsalesClientError с соответствующими кодами
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except InsalesClientError as e:
            # Получаем статус код из исключения
            status_code = getattr(e, "status_code", None)
            
            # Если статус код не доступен, пытаемся извлечь из сообщения
            if status_code is None:
                error_msg = str(e)
                # Формат: "Insales API error 429: ..."
                parts = error_msg.split()
                for i, part in enumerate(parts):
                    if part.isdigit() and i > 0:
                        try:
                            status_code = int(part)
                            break
                        except ValueError:
                            continue
            
            # Проверяем, нужно ли повторять попытку
            should_retry = False
            if status_code:
                if status_code == 429:  # Too Many Requests
                    should_retry = True
                    # Вычисляем время ожидания с экспоненциальным backoff
                    wait_time = min(base_backoff * (2 ** attempt), max_backoff)
                    LOG.warning(
                        f"Rate limit (429) на попытке {attempt + 1}/{max_retries}. "
                        f"Ожидание {wait_time:.1f} сек..."
                    )
                    time.sleep(wait_time)
                elif 500 <= status_code < 600:  # Server Errors
                    should_retry = True
                    wait_time = min(base_backoff * (2 ** attempt), max_backoff)
                    LOG.warning(
                        f"Server error ({status_code}) на попытке {attempt + 1}/{max_retries}. "
                        f"Ожидание {wait_time:.1f} сек..."
                    )
                    time.sleep(wait_time)
            
            if not should_retry or attempt == max_retries - 1:
                # Не повторяем или это последняя попытка
                raise
            
            last_exception = e
            
        except Exception as e:
            # Для других исключений не повторяем
            raise
    
    # Если дошли сюда, значит все попытки исчерпаны
    if last_exception:
        raise last_exception
    raise RuntimeError("Все попытки исчерпаны")


def fetch_all_collections_with_retry(
    client: InsalesClient, per_page: int = 250
) -> List[Dict[str, Any]]:
    """
    Получает все категории через InSales API с поддержкой пагинации и retry.
    
    Логирует прогресс каждые 50 категорий.
    """
    all_collections: List[Dict[str, Any]] = []
    page = 1
    total_fetched = 0
    
    LOG.info("Начинаем получение категорий из InSales API...")
    
    while True:
        try:
            # Используем retry для каждого запроса
            chunk = retry_with_backoff(
                client.get_collections,
                page=page,
                per_page=per_page,
            )
            
            if not chunk:
                LOG.info(f"Страница {page} пуста, завершаем получение")
                break
            
            all_collections.extend(chunk)
            total_fetched += len(chunk)
            
            # Логируем прогресс каждые 50 категорий
            if total_fetched % 50 == 0 or len(chunk) < per_page:
                LOG.info(f"Получено категорий: {total_fetched} (страница {page}, в чанке: {len(chunk)})")
            
            # Если получили меньше чем per_page, значит это последняя страница
            if len(chunk) < per_page:
                LOG.info(f"Последняя страница получена. Всего категорий: {total_fetched}")
                break
            
            page += 1
            
            # Небольшая задержка между запросами для избежания rate limit
            time.sleep(0.3)
            
        except InsalesClientError as e:
            LOG.error(f"Ошибка API при получении страницы {page}: {e}")
            raise
        except Exception as e:
            LOG.error(f"Неожиданная ошибка при получении страницы {page}: {e}")
            raise
    
    LOG.info(f"Всего получено категорий: {len(all_collections)}")
    return all_collections


def build_category_tree(collections: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """
    Строит словарь категорий по ID для быстрого доступа.
    
    Возвращает словарь: {category_id: category_data}
    """
    category_map: Dict[int, Dict[str, Any]] = {}
    
    for collection in collections:
        cat_id = collection.get("id")
        if cat_id is None:
            LOG.warning(f"Категория без ID пропущена: {collection.get('title', 'Unknown')}")
            continue
        
        category_map[cat_id] = {
            "id": cat_id,
            "parent_id": collection.get("parent_id"),
            "title": collection.get("title", ""),
        }
    
    return category_map


def build_full_path(
    category_id: int,
    category_map: Dict[int, Dict[str, Any]],
    cache: Optional[Dict[int, str]] = None,
) -> str:
    """
    Восстанавливает полный путь категории от корня.
    
    Формат: "Каталог > Электрика > Щитовое оборудование > Переключатели"
    
    Использует кэш для оптимизации.
    """
    if cache is None:
        cache = {}
    
    # Проверяем кэш
    if category_id in cache:
        return cache[category_id]
    
    # Получаем категорию
    category = category_map.get(category_id)
    if not category:
        # Если категория не найдена, возвращаем только ID
        path = f"Unknown({category_id})"
        cache[category_id] = path
        return path
    
    title = category.get("title", f"Category_{category_id}")
    parent_id = category.get("parent_id")
    
    # Если это корневая категория (нет parent_id)
    if parent_id is None:
        path = title
        cache[category_id] = path
        return path
    
    # Рекурсивно получаем путь родителя
    parent_path = build_full_path(parent_id, category_map, cache)
    
    # Формируем полный путь
    path = f"{parent_path} > {title}"
    cache[category_id] = path
    return path


def process_categories(collections: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Обрабатывает категории и строит полные пути.
    
    Возвращает:
    - Список категорий с полными путями
    - Словарь mapping: {category_id: full_path}
    """
    LOG.info("Строим дерево категорий...")
    category_map = build_category_tree(collections)
    LOG.info(f"Построено {len(category_map)} категорий в дереве")
    
    LOG.info("Восстанавливаем полные пути для всех категорий...")
    path_cache: Dict[int, str] = {}
    categories_with_paths: List[Dict[str, Any]] = []
    category_id_to_path: Dict[str, str] = {}
    
    processed = 0
    for collection in collections:
        cat_id = collection.get("id")
        if cat_id is None:
            continue
        
        # Восстанавливаем полный путь
        full_path = build_full_path(cat_id, category_map, path_cache)
        
        # Формируем запись для categories_with_paths.json
        category_entry = {
            "id": cat_id,
            "parent_id": collection.get("parent_id"),
            "title": collection.get("title", ""),
            "full_path": full_path,
        }
        categories_with_paths.append(category_entry)
        
        # Формируем mapping для category_id_to_path.json
        category_id_to_path[str(cat_id)] = full_path
        
        processed += 1
        if processed % 50 == 0:
            LOG.info(f"Обработано категорий с путями: {processed}/{len(collections)}")
    
    LOG.info(f"Всего обработано категорий: {processed}")
    return categories_with_paths, category_id_to_path


def save_results(
    categories_with_paths: List[Dict[str, Any]],
    category_id_to_path: Dict[str, str],
) -> None:
    """Сохраняет результаты в JSON файлы."""
    # Создаем директорию если её нет
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Сохраняем categories_with_paths.json
    LOG.info(f"Сохраняем категории с путями в {CATEGORIES_WITH_PATHS_PATH}")
    with CATEGORIES_WITH_PATHS_PATH.open("w", encoding="utf-8") as f:
        json.dump(categories_with_paths, f, ensure_ascii=False, indent=2)
    
    # Сохраняем category_id_to_path.json
    LOG.info(f"Сохраняем mapping категорий в {CATEGORY_ID_TO_PATH_PATH}")
    with CATEGORY_ID_TO_PATH_PATH.open("w", encoding="utf-8") as f:
        json.dump(category_id_to_path, f, ensure_ascii=False, indent=2)
    
    LOG.info("Результаты успешно сохранены")


def main() -> int:
    """Основная функция скрипта."""
    parser = argparse.ArgumentParser(
        description="Создает snapshot категорий InSales с восстановлением полных путей"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help="Путь к config.json",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=250,
        help="Количество категорий на странице (по умолчанию 250)",
    )
    args = parser.parse_args()
    
    # Убеждаемся, что режим не SNAPSHOT (иначе InsalesClient не будет работать)
    if os.getenv("INSALES_SOURCE", "").lower() == "snapshot":
        LOG.warning(
            "INSALES_SOURCE=snapshot обнаружен. "
            "Временно устанавливаем INSALES_SOURCE=api для работы с API"
        )
        os.environ["INSALES_SOURCE"] = "api"
    
    try:
        # Загружаем конфигурацию
        LOG.info(f"Загружаем конфигурацию из {args.config}")
        config = load_config(args.config)
        
        # Создаем клиент InSales
        insales_cfg = InsalesConfig(
            host=config["insales"]["host"],
            api_key=config["insales"]["api_key"],
            api_password=config["insales"]["api_password"],
        )
        client = InsalesClient(insales_cfg)
        
        # Получаем все категории
        collections = fetch_all_collections_with_retry(client, per_page=args.per_page)
        
        if not collections:
            LOG.error("Не получено ни одной категории. Проверьте подключение к API.")
            return 1
        
        # Обрабатываем категории и строим пути
        categories_with_paths, category_id_to_path = process_categories(collections)
        
        # Сохраняем результаты
        save_results(categories_with_paths, category_id_to_path)
        
        # Выводим статистику
        LOG.info("=" * 60)
        LOG.info("SNAPSHOT КАТЕГОРИЙ УСПЕШНО СОЗДАН")
        LOG.info("=" * 60)
        LOG.info(f"Всего категорий: {len(categories_with_paths)}")
        LOG.info(f"Файл с категориями: {CATEGORIES_WITH_PATHS_PATH}")
        LOG.info(f"Файл с mapping: {CATEGORY_ID_TO_PATH_PATH}")
        LOG.info("=" * 60)
        
        return 0
        
    except FileNotFoundError as e:
        LOG.error(f"Ошибка: {e}")
        return 1
    except InsalesClientError as e:
        LOG.error(f"Ошибка InSales API: {e}")
        return 1
    except Exception as e:
        LOG.exception(f"Неожиданная ошибка: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

