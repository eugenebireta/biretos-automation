#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Быстрая выгрузка (snapshot) всех товаров из InSales API.

Особенности:
- Параллельная загрузка с контролем rate limit
- Retry/backoff на 429/5xx ошибки
- Checkpoint механизм для продолжения после сбоя
- Сохранение в NDJSON и CSV форматах
- Прогресс-логирование
"""
import argparse
import csv
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from clients import InsalesClient, InsalesClientError, InsalesConfig

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
LOG = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
DEFAULT_OUTPUT_DIR = ROOT / "insales_snapshot"
CHECKPOINT_FILE = "checkpoint.json"
PROGRESS_INTERVAL = 100  # Логировать прогресс каждые N товаров


@dataclass
class Checkpoint:
    """Состояние выгрузки для продолжения."""
    last_page: int = 0
    total_pages: Optional[int] = None
    total_products: Optional[int] = None
    downloaded_count: int = 0
    failed_pages: List[int] = None
    start_time: Optional[str] = None
    
    def __post_init__(self):
        if self.failed_pages is None:
            self.failed_pages = []


class ProductSnapshotter:
    """Класс для создания snapshot товаров с параллелизмом и retry."""
    
    def __init__(
        self,
        client: InsalesClient,
        output_dir: Path,
        per_page: int = 250,
        max_workers: int = 5,
        max_retries: int = 5,
        retry_delay: float = 2.0,
        timeout: int = 30,
    ):
        self.client = client
        self.output_dir = Path(output_dir)
        self.per_page = per_page
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        
        # Создаём директорию вывода
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Файлы вывода
        self.ndjson_path = self.output_dir / "products.ndjson"
        self.csv_path = self.output_dir / "products.csv"
        self.checkpoint_path = self.output_dir / CHECKPOINT_FILE
        
        # Состояние
        self.checkpoint = self._load_checkpoint()
        self.products: List[Dict[str, Any]] = []
        self.downloaded_ids: Set[int] = set()
        self.failed_pages: List[int] = []
        self.lock = None  # Будет установлен при использовании threading
    
    def _load_checkpoint(self) -> Checkpoint:
        """Загружает checkpoint из файла."""
        if self.checkpoint_path.exists():
            try:
                with self.checkpoint_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    return Checkpoint(**data)
            except Exception as e:
                LOG.warning(f"Не удалось загрузить checkpoint: {e}. Начинаем заново.")
        return Checkpoint(start_time=datetime.now().isoformat())
    
    def _save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Сохраняет checkpoint в файл."""
        try:
            with self.checkpoint_path.open("w", encoding="utf-8") as f:
                json.dump(asdict(checkpoint), f, ensure_ascii=False, indent=2)
        except Exception as e:
            LOG.error(f"Ошибка сохранения checkpoint: {e}")
    
    def _fetch_page_with_retry(self, page: int) -> Optional[List[Dict[str, Any]]]:
        """
        Загружает страницу товаров с retry логикой.
        
        Returns:
            Список товаров или None при окончательной ошибке
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                products = self.client.get_products(page=page, per_page=self.per_page)
                if products:
                    return products
                # Пустой список означает конец данных
                return []
                
            except InsalesClientError as e:
                error_str = str(e)
                status_code = None
                
                # Извлекаем статус код из ошибки
                if "429" in error_str or "rate limit" in error_str.lower():
                    status_code = 429
                elif "500" in error_str or "502" in error_str or "503" in error_str:
                    status_code = 500
                
                if status_code in (429, 500, 502, 503):
                    # Exponential backoff для 429/5xx
                    delay = self.retry_delay * (2 ** (attempt - 1))
                    LOG.warning(
                        f"Страница {page}: попытка {attempt}/{self.max_retries}, "
                        f"ошибка {status_code}. Ожидание {delay:.1f}с..."
                    )
                    time.sleep(delay)
                else:
                    # Другие ошибки (401, 403, 404) - не retry
                    LOG.error(f"Страница {page}: ошибка {error_str}. Пропуск.")
                    return None
                    
            except Exception as e:
                LOG.error(f"Страница {page}: неожиданная ошибка: {e}")
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** (attempt - 1))
                    time.sleep(delay)
                else:
                    return None
        
        LOG.error(f"Страница {page}: исчерпаны все попытки retry")
        return None
    
    def _get_total_pages(self) -> Optional[int]:
        """Получает общее количество страниц."""
        try:
            total = self.client.get_products_count()
            if total is not None:
                return (total + self.per_page - 1) // self.per_page
        except Exception:
            pass
        return None
    
    def _save_product_ndjson(self, product: Dict[str, Any]) -> None:
        """Добавляет товар в NDJSON файл."""
        try:
            with self.ndjson_path.open("a", encoding="utf-8") as f:
                json.dump(product, f, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            LOG.error(f"Ошибка записи в NDJSON: {e}")
    
    def _extract_category_path(self, product: Dict[str, Any]) -> str:
        """Извлекает путь категории из товара."""
        category_id = product.get("category_id")
        if category_id:
            return str(category_id)
        
        # Можно попытаться получить категорию из других полей
        category_title = product.get("category_title", "")
        return category_title if category_title else ""
    
    def _extract_sku(self, product: Dict[str, Any]) -> str:
        """Извлекает SKU из товара (из первого варианта)."""
        variants = product.get("variants", [])
        if variants and len(variants) > 0:
            sku = variants[0].get("sku")
            if sku:
                return str(sku)
        return ""
    
    def _extract_price(self, product: Dict[str, Any]) -> str:
        """Извлекает цену из товара (из первого варианта)."""
        variants = product.get("variants", [])
        if variants and len(variants) > 0:
            price = variants[0].get("price")
            if price is not None:
                return str(price)
        return ""
    
    def _prepare_csv_row(self, product: Dict[str, Any]) -> Dict[str, str]:
        """Подготавливает строку CSV из товара."""
        return {
            "id": str(product.get("id", "")),
            "sku": self._extract_sku(product),
            "name": product.get("title", ""),
            "price": self._extract_price(product),
            "category_id": str(product.get("category_id", "")),
            "category_path": self._extract_category_path(product),
        }
    
    def _init_csv_file(self) -> None:
        """Инициализирует CSV файл с заголовками."""
        if not self.csv_path.exists():
            with self.csv_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["id", "sku", "name", "price", "category_id", "category_path"],
                )
                writer.writeheader()
    
    def _append_csv_row(self, row: Dict[str, str]) -> None:
        """Добавляет строку в CSV файл."""
        try:
            with self.csv_path.open("a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["id", "sku", "name", "price", "category_id", "category_path"],
                )
                writer.writerow(row)
        except Exception as e:
            LOG.error(f"Ошибка записи в CSV: {e}")
    
    def _process_products_batch(self, products: List[Dict[str, Any]]) -> None:
        """Обрабатывает batch товаров: сохраняет в NDJSON и CSV."""
        for product in products:
            product_id = product.get("id")
            if product_id in self.downloaded_ids:
                continue  # Пропускаем дубликаты
            
            self.downloaded_ids.add(product_id)
            self._save_product_ndjson(product)
            
            csv_row = self._prepare_csv_row(product)
            self._append_csv_row(csv_row)
    
    def download_all(self) -> Dict[str, Any]:
        """
        Загружает все товары с параллелизмом.
        
        Returns:
            Статистика выгрузки
        """
        LOG.info("=" * 60)
        LOG.info("НАЧАЛО ВЫГРУЗКИ ТОВАРОВ InSales")
        LOG.info("=" * 60)
        
        # Инициализация CSV
        self._init_csv_file()
        
        # Загружаем уже скачанные ID из checkpoint (если есть)
        if self.checkpoint.downloaded_count > 0:
            LOG.info(
                f"Продолжаем с checkpoint: страница {self.checkpoint.last_page + 1}, "
                f"уже скачано: {self.checkpoint.downloaded_count}"
            )
            # Загружаем уже скачанные ID из существующих файлов для защиты от дубликатов
            if self.ndjson_path.exists():
                LOG.info("Загрузка уже скачанных ID из NDJSON файла...")
                loaded_count = 0
                try:
                    with self.ndjson_path.open("r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                try:
                                    product = json.loads(line)
                                    product_id = product.get("id")
                                    if product_id:
                                        self.downloaded_ids.add(product_id)
                                        loaded_count += 1
                                except json.JSONDecodeError:
                                    continue
                    LOG.info(f"Загружено {loaded_count} ID из существующего NDJSON")
                except Exception as e:
                    LOG.warning(f"Не удалось загрузить ID из NDJSON: {e}")
        
        # Получаем общее количество страниц (если возможно)
        total_pages = self._get_total_pages()
        if total_pages:
            self.checkpoint.total_pages = total_pages
            LOG.info(f"Общее количество страниц: {total_pages}")
        
        # Определяем стартовую страницу
        start_page = self.checkpoint.last_page + 1 if self.checkpoint.last_page > 0 else 1
        
        # Если есть failed_pages, добавляем их в очередь
        pages_to_download = self.checkpoint.failed_pages.copy()
        self.checkpoint.failed_pages.clear()
        
        # Добавляем остальные страницы
        if total_pages:
            # Знаем общее количество страниц
            for page in range(start_page, total_pages + 1):
                if page not in pages_to_download:
                    pages_to_download.append(page)
            all_pages_known = True
        else:
            # Не знаем общее количество - будем загружать батчами
            LOG.info("Общее количество страниц неизвестно. Будет использоваться батч-загрузка.")
            # Для начала добавим батч страниц для параллельной загрузки
            batch_size = self.max_workers * 2  # Загружаем батчами по количеству воркеров * 2
            max_unknown_pages = 5000  # Максимум страниц если не знаем общее количество
            for page in range(start_page, min(start_page + batch_size, start_page + max_unknown_pages)):
                if page not in pages_to_download:
                    pages_to_download.append(page)
            all_pages_known = False
        
        LOG.info(f"Загрузка с параллелизмом: {self.max_workers} потоков")
        LOG.info(f"Размер страницы: {self.per_page} товаров")
        
        start_time = time.time()
        downloaded = self.checkpoint.downloaded_count
        end_of_data = False
        current_page = start_page
        
        # Используем ThreadPoolExecutor для параллельной загрузки
        while not end_of_data and (all_pages_known or current_page < start_page + 5000):
            # Определяем страницы для текущего батча
            if all_pages_known:
                batch_pages = [p for p in pages_to_download if p >= current_page]
                if not batch_pages:
                    break
            else:
                # Для неизвестного количества загружаем батч за раз
                batch_pages = []
                batch_size = self.max_workers * 2
                for _ in range(batch_size):
                    if current_page not in pages_to_download:
                        pages_to_download.append(current_page)
                    batch_pages.append(current_page)
                    current_page += 1
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Создаём задачи для текущего батча
                future_to_page = {
                    executor.submit(self._fetch_page_with_retry, page): page
                    for page in batch_pages
                }
                
                # Обрабатываем результаты батча
                batch_empty_found = False
                for future in as_completed(future_to_page):
                    if end_of_data:
                        future.cancel()
                        continue
                    
                    page = future_to_page[future]
                    try:
                        products = future.result()
                        
                        if products is None:
                            # Ошибка при загрузке
                            self.failed_pages.append(page)
                            LOG.warning(f"Страница {page}: не удалось загрузить")
                            continue
                        
                        if len(products) == 0:
                            # Конец данных
                            LOG.info(f"Страница {page}: пустой ответ (конец данных)")
                            end_of_data = True
                            batch_empty_found = True
                            continue
                        
                        # Обрабатываем товары
                        self._process_products_batch(products)
                        downloaded += len(products)
                        
                        # Обновляем checkpoint
                        self.checkpoint.last_page = max(self.checkpoint.last_page, page)
                        self.checkpoint.downloaded_count = downloaded
                        self._save_checkpoint(self.checkpoint)
                        
                        # Прогресс-лог
                        if downloaded % PROGRESS_INTERVAL == 0:
                            elapsed = time.time() - start_time
                            rate = downloaded / elapsed if elapsed > 0 else 0
                            LOG.info(
                                f"Прогресс: {downloaded} товаров скачано "
                                f"(страница {page}, ~{rate:.1f} товаров/с)"
                            )
                        
                        LOG.debug(f"Страница {page}: загружено {len(products)} товаров")
                        
                        # Если получили меньше товаров чем per_page, это может быть конец
                        if len(products) < self.per_page:
                            batch_empty_found = True
                            # Для неизвестного количества, если страница неполная, следующий батч не нужен
                            if not all_pages_known:
                                end_of_data = True
                        
                    except Exception as e:
                        LOG.error(f"Страница {page}: ошибка обработки: {e}")
                        self.failed_pages.append(page)
                
                # Если нашли пустую страницу и не знаем общее количество, проверяем следующую для уверенности
                if batch_empty_found and not all_pages_known and not end_of_data:
                    # Проверяем следующую страницу для подтверждения
                    check_page = max(batch_pages) + 1
                    check_products = self._fetch_page_with_retry(check_page)
                    if not check_products or len(check_products) == 0:
                        end_of_data = True
                        LOG.info(f"Страница {check_page}: подтверждён конец данных")
                    else:
                        # Есть ещё данные, обрабатываем
                        self._process_products_batch(check_products)
                        downloaded += len(check_products)
                        self.checkpoint.last_page = max(self.checkpoint.last_page, check_page)
                        self.checkpoint.downloaded_count = downloaded
                        self._save_checkpoint(self.checkpoint)
                
                # Обновляем текущую страницу
                if all_pages_known:
                    if batch_pages:
                        current_page = max(batch_pages) + 1
                    else:
                        break
                else:
                    # Для неизвестного количества, если достигли конца или пустой страницы, выходим
                    if end_of_data or batch_empty_found:
                        break
        
        elapsed = time.time() - start_time
        
        # Финальный checkpoint
        self.checkpoint.downloaded_count = downloaded
        self.checkpoint.failed_pages = self.failed_pages
        self._save_checkpoint(self.checkpoint)
        
        result = {
            "downloaded": downloaded,
            "failed_pages": len(self.failed_pages),
            "elapsed_seconds": elapsed,
            "rate_per_second": downloaded / elapsed if elapsed > 0 else 0,
            "output_dir": str(self.output_dir),
            "ndjson_path": str(self.ndjson_path),
            "csv_path": str(self.csv_path),
        }
        
        LOG.info("=" * 60)
        LOG.info("ВЫГРУЗКА ЗАВЕРШЕНА")
        LOG.info("=" * 60)
        LOG.info(f"Всего товаров: {downloaded}")
        LOG.info(f"Время выполнения: {elapsed:.1f}с")
        LOG.info(f"Скорость: {result['rate_per_second']:.1f} товаров/с")
        LOG.info(f"Неудачных страниц: {len(self.failed_pages)}")
        if self.failed_pages:
            LOG.warning(f"Список неудачных страниц: {self.failed_pages[:10]}...")
        LOG.info(f"Выходная директория: {self.output_dir}")
        
        return result


def load_config(config_path: Path) -> Dict[str, Any]:
    """Загружает конфигурацию из JSON файла."""
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    """Главная функция."""
    parser = argparse.ArgumentParser(
        description="Быстрая выгрузка (snapshot) всех товаров из InSales API"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help=f"Путь к config.json (по умолчанию: {CONFIG_PATH})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Директория для сохранения snapshot (по умолчанию: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=250,
        help="Количество товаров на страницу (по умолчанию: 250, максимум обычно 250)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Количество параллельных потоков (по умолчанию: 5)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Максимальное количество попыток для одной страницы (по умолчанию: 5)",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=2.0,
        help="Базовая задержка для retry в секундах (по умолчанию: 2.0)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout для HTTP запросов в секундах (по умолчанию: 30)",
    )
    parser.add_argument(
        "--reset-checkpoint",
        action="store_true",
        help="Игнорировать checkpoint и начать заново",
    )
    
    args = parser.parse_args()
    
    # Проверка конфигурации
    if not args.config.exists():
        LOG.error(f"Конфигурация не найдена: {args.config}")
        return 1
    
    config = load_config(args.config)
    insales_config = config.get("insales")
    if not insales_config:
        LOG.error("Секция 'insales' не найдена в конфигурации")
        return 1
    
    # Создание клиента
    client_config = InsalesConfig(
        host=insales_config["host"],
        api_key=insales_config["api_key"],
        api_password=insales_config["api_password"],
    )
    client = InsalesClient(client_config, timeout=args.timeout)
    
    # Создание snapshotter
    snapshotter = ProductSnapshotter(
        client=client,
        output_dir=args.output,
        per_page=args.per_page,
        max_workers=args.workers,
        max_retries=args.max_retries,
        retry_delay=args.retry_delay,
        timeout=args.timeout,
    )
    
    # Сброс checkpoint при необходимости
    if args.reset_checkpoint:
        if snapshotter.checkpoint_path.exists():
            snapshotter.checkpoint_path.unlink()
            LOG.info("Checkpoint сброшен")
        snapshotter.checkpoint = Checkpoint(start_time=datetime.now().isoformat())
    
    # Запуск выгрузки
    try:
        result = snapshotter.download_all()
        
        print("\n" + "=" * 60)
        print("РЕЗУЛЬТАТЫ ВЫГРУЗКИ")
        print("=" * 60)
        print(f"Товаров скачано: {result['downloaded']}")
        print(f"Время выполнения: {result['elapsed_seconds']:.1f}с")
        print(f"Скорость: {result['rate_per_second']:.1f} товаров/с")
        print(f"Неудачных страниц: {result['failed_pages']}")
        print(f"\nФайлы:")
        print(f"  NDJSON: {result['ndjson_path']}")
        print(f"  CSV:    {result['csv_path']}")
        print(f"\nДля продолжения запустите:")
        print(f"  python {Path(__file__).name} --config {args.config} --output {args.output}")
        
        return 0 if result['failed_pages'] == 0 else 1
        
    except KeyboardInterrupt:
        LOG.warning("\nПрервано пользователем. Прогресс сохранён в checkpoint.")
        return 130
    except Exception as e:
        LOG.error(f"Критическая ошибка: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

