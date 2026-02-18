#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматический Property Schema Sync для Shopware из snapshot InSales.

Особенности:
- Читает products.ndjson
- Извлекает все characteristics
- Нормализует названия (trim, lower, дедупликация)
- Создает Property Groups в Shopware
- Сохраняет mapping в migration_map.json
- Идемпотентность (безопасный повторный запуск)
- Dry-run режим
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
SNAPSHOT_PATH = ROOT / "insales_snapshot" / "products.ndjson"
MAP_PATH = ROOT / "migration_map.json"


def load_json(path: Path, *, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Загружает JSON файл."""
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as handler:
        return json.load(handler)


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    """Сохраняет JSON файл."""
    with path.open("w", encoding="utf-8") as handler:
        json.dump(payload, handler, ensure_ascii=False, indent=2)


def normalize_property_name(name: str) -> str:
    """
    Нормализует название характеристики.
    
    - trim пробелов
    - возвращает оригинальное название (trimmed)
    """
    if not name:
        return ""
    return name.strip()


def is_valid_property_group_name(name: str) -> bool:
    """
    Проверяет, является ли название валидным для Property Group.
    
    Фильтрует:
    - только цифры
    - числа
    - длина < 2 символов
    - строки, состоящие только из цифр, пробелов, дефисов, точек, плюсов, запятых
    - строки, начинающиеся с +/- и содержащие в основном цифры
    - артикулы и коды (например, "9123-8071", "0-0-4S")
    """
    if not name:
        return False
    
    name = name.strip()
    
    # Длина < 5 символов (слишком короткие для названия Property Group)
    # Или слишком длинные (> 100 символов - скорее всего описание, а не название)
    if len(name) < 5 or len(name) > 100:
        return False
    
    # Строки, состоящие только из латинских букв и цифр без русских букв
    # (скорее всего артикулы/коды, а не названия Property Groups)
    # Названия Property Groups обычно содержат русские буквы
    if not re.search(r'[а-яА-Я]', name):
        # Если нет русских букв, пропускаем только если это явно название (длинное, с пробелами)
        if len(name) < 15 or ' ' not in name:
            return False
        # Или если это известные названия на английском (например, "Brand", "Country")
        known_english_names = {'brand', 'country', 'color', 'size', 'material', 'manufacturer'}
        if name.lower().strip() not in known_english_names:
            return False
    
    # Только цифры, пробелы, дефисы, точки, плюсы, минусы, запятые
    if re.match(r'^[\d\s\-\+\.\,]+$', name):
        return False
    
    # Строки, начинающиеся с +/- и содержащие в основном цифры и символы
    if re.match(r'^[\+\-][\d\s\-\+\.\,]+$', name):
        return False
    
    # Попытка распознать как число (float или int)
    try:
        # Убираем пробелы и пробуем преобразовать
        clean_name = name.replace(' ', '').replace(',', '.')
        float(clean_name)
        # Если успешно преобразовано в число - это не название
        return False
    except ValueError:
        pass
    
    # Артикулы и коды: если больше 50% символов - цифры, дефисы, точки, запятые
    # и есть хотя бы одна цифра - скорее всего это артикул/код, а не название
    digit_symbol_count = len(re.findall(r'[\d\-\+\.\,]', name))
    if digit_symbol_count > len(name) * 0.5 and re.search(r'\d', name):
        # Но пропускаем, если есть буквы (русские или латинские)
        if not re.search(r'[а-яА-Яa-zA-Z]', name):
            return False
    
    # Строки, начинающиеся с цифр (скорее всего артикулы/коды, а не названия Property Groups)
    # Названия Property Groups обычно не начинаются с цифр
    if re.match(r'^\d', name):
        return False
    
    # Строки, начинающиеся с "-" или "+" и содержащие в основном цифры
    if re.match(r'^[\+\-]', name):
        # Если после +/- идут в основном цифры и символы - это значение, а не название
        rest = name[1:].strip()
        if re.match(r'^[\d\s\-\+\.\,]+$', rest):
            return False
        # Если после +/- идет число - это значение
        try:
            float(rest.replace(',', '.').split()[0])
            return False
        except (ValueError, IndexError):
            pass
    
    # Строки с запятыми, содержащие артикулы и коды (например, "AT400318, 0501 331 636")
    # Названия Property Groups обычно не содержат запятые с артикулами
    if ',' in name:
        # Если содержит запятые и много цифр/латинских букв - скорее всего список артикулов
        parts = [p.strip() for p in name.split(',')]
        # Если большинство частей - артикулы (начинаются с букв/цифр, короткие)
        code_like_parts = sum(1 for p in parts if re.match(r'^[A-Z0-9]', p) and len(p) < 15)
        if code_like_parts > len(parts) * 0.3:  # Более строгий фильтр - 30% вместо 50%
            return False
        # Если первая часть - артикул (начинается с латинских букв и цифр)
        if parts and re.match(r'^[A-Z0-9]+', parts[0]) and len(parts[0]) < 20:
            return False
    
    # Строки, содержащие паттерны значений (например, "55мм", "100П", "x25x20", "/1")
    # Названия Property Groups обычно не содержат такие паттерны
    if re.search(r'\d+[ммММ]', name) or re.search(r'\d+[Пп]', name) or re.search(r'[xхХ]\d+', name) or re.search(r'/\d+', name):
        return False
    
    # Строки с паттернами значений типа "±1.5 мм", "АПШ 5.132.039", "24kV"
    if re.search(r'[±]\d+', name) or re.search(r'\d+\.\d+\.\d+', name) or re.search(r'\d+[kVкВКВ]', name):
        return False
    
    # Строки со слэшами (пути категорий, например "Автозапчасти/Запчасти для грузовых автомобилей")
    # Названия Property Groups обычно не содержат слэши
    if '/' in name:
        return False
    
    # Строки со скобками, содержащими числа (например, "DN 100 (4 дюйма)") - это значения
    if re.search(r'\([^)]*\d+[^)]*\)', name):
        return False
    
    # Строки, содержащие паттерны типа "DN 100", "PL7-C20" - это значения с размерами/параметрами
    if re.search(r'\b[A-Z]{2,}\s+\d+', name) or re.search(r'\b[A-Z]+\d+[-]\w+', name):
        return False
    
    # Строки, начинающиеся с латинских букв (скорее всего артикулы/коды, а не названия Property Groups)
    # Названия Property Groups обычно начинаются с русских букв
    # Например: "BH-AV", "DIL M(c)9-01", "HGH25CAH", "DSP процессор", "KVM-переключатель"
    if re.match(r'^[A-Z]', name):
        russian_letters = len(re.findall(r'[а-яА-Я]', name))
        # Пропускаем только если содержит достаточно русских букв (минимум 15)
        # и не содержит артикулов/кодов
        if russian_letters < 15:
            return False
        # Если содержит дефисы, цифры или скобки - скорее всего артикул
        if '-' in name or re.search(r'\d', name) or '(' in name:
            return False
    
    # Строки, содержащие дефисы и цифры (артикулы типа "А63-М", "Ант-370")
    # Названия Property Groups обычно не содержат такие паттерны
    if '-' in name and re.search(r'\d', name):
        # Пропускаем только если достаточно длинное и содержит много русских букв
        russian_letters = len(re.findall(r'[а-яА-Я]', name))
        total_letters = len(re.findall(r'[а-яА-Яa-zA-Z]', name))
        if russian_letters < 10 or total_letters < 15:
            return False
    
    # Очень короткие строки с дефисами (например, "А63-М") - скорее всего артикулы
    if len(name) < 10 and '-' in name:
        return False
    
    # Строки, где цифр больше, чем букв (скорее всего значения, а не названия)
    digit_count = len(re.findall(r'\d', name))
    letter_count = len(re.findall(r'[а-яА-Яa-zA-Z]', name))
    if digit_count > letter_count:
        return False
    
    # Строки, содержащие паттерны артикулов (например, "001351", "0041-1092BAC")
    # Если начинается с нулей и цифр, и длина короткая - скорее всего артикул
    if re.match(r'^0+\d+[\-\s]', name) and len(name) < 20:
        return False
    
    # Строки с запятыми и артикулами (например, "001351, Yale, Atlet")
    # Если начинается с цифр и содержит запятую - скорее всего список артикулов
    if re.match(r'^\d+.*,', name):
        letter_count = len(re.findall(r'[а-яА-Яa-zA-Z]', name))
        if letter_count < 10:  # Мало букв - скорее всего артикулы
            return False
    
    # Строки, содержащие паттерны типа "004408, 200x25mm, 4614020037"
    # Много цифр и дефисов, мало букв
    digit_count = len(re.findall(r'\d', name))
    letter_count = len(re.findall(r'[а-яА-Яa-zA-Z]', name))
    if digit_count > letter_count * 2 and letter_count < 5:
        return False
    
    return True


def normalize_for_comparison(name: str) -> str:
    """
    Нормализует название для сравнения (дедупликация).
    
    - trim
    - lower()
    """
    if not name:
        return ""
    return name.strip().lower()


def extract_unique_property_names(snapshot_path: Path) -> Tuple[Dict[str, str], Dict[str, int], Dict[str, list]]:
    """
    Извлекает уникальные названия характеристик из products.ndjson.
    
    Returns:
        Tuple of:
        - Dict[normalized_name -> original_name]
        - Dict[original_name -> count]
        - Dict[normalized_name -> list of variants]
        Например: ({"страна производства": "Страна производства"}, {"Страна производства": 10}, {"страна производства": ["Страна", "Страна производства"]})
    """
    property_names: Dict[str, str] = {}
    property_counts: Dict[str, int] = defaultdict(int)
    all_variants: Dict[str, list] = defaultdict(list)
    
    if not snapshot_path.exists():
        print(f"[ERROR] Файл snapshot не найден: {snapshot_path}")
        return property_names, property_counts, all_variants
    
    print(f"[INFO] Чтение snapshot: {snapshot_path}")
    products_count = 0
    characteristics_count = 0
    
    with snapshot_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            
            try:
                product = json.loads(line)
                products_count += 1
                
                # Извлекаем characteristics
                characteristics = product.get("characteristics", []) or product.get("properties", [])
                
                for char in characteristics:
                    characteristics_count += 1
                    
                    # Получаем название Property Group ТОЛЬКО из title или name
                    # НИКОГДА не используем value, permalink и другие поля
                    prop_title = (
                        char.get("title") or 
                        char.get("name") or 
                        ""
                    )
                    
                    if not prop_title:
                        continue
                    
                    # Жёсткий фильтр: пропускаем невалидные названия
                    if not is_valid_property_group_name(prop_title):
                        continue
                    
                    # Нормализуем для сравнения
                    normalized = normalize_for_comparison(prop_title)
                    
                    if not normalized:
                        continue
                    
                    # Сохраняем оригинальное название (trimmed)
                    original = normalize_property_name(prop_title)
                    property_counts[original] += 1
                    
                    # Если уже есть такое название (нормализованное), выбираем более длинное
                    # или оставляем первое встреченное
                    if normalized not in property_names:
                        property_names[normalized] = original
                        all_variants[normalized] = [original]
                    else:
                        # Добавляем вариант если его еще нет
                        if original not in all_variants[normalized]:
                            all_variants[normalized].append(original)
                        # Если новое название длиннее, используем его
                        if len(original) > len(property_names[normalized]):
                            property_names[normalized] = original
            
            except json.JSONDecodeError as e:
                # Пропускаем некорректные строки
                continue
            except Exception as e:
                # Пропускаем строки с ошибками
                continue
    
    print(f"[INFO] Обработано товаров: {products_count}")
    print(f"[INFO] Найдено характеристик: {characteristics_count}")
    print(f"[INFO] Уникальных Property Groups: {len(property_names)}")
    
    return property_names, property_counts, all_variants


def deduplicate_property_names(property_names: Dict[str, str]) -> Dict[str, str]:
    """
    Убирает дубликаты на основе нормализации.
    
    Например: "Страна" и "Страна производства" могут быть одинаковыми группами.
    Пока оставляем простую логику - если normalized совпадает, это дубликат.
    """
    # Уже сделано в extract_unique_property_names через normalize_for_comparison
    return property_names


def sync_property_groups(
    client: ShopwareClient,
    property_names: Dict[str, str],
    mapping: Dict[str, Any],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Синхронизирует Property Groups в Shopware.
    
    Args:
        client: Shopware клиент
        property_names: Dict[normalized_name -> original_name]
        mapping: Текущий mapping (будет обновлен)
        dry_run: Если True, только логирует без создания
    
    Returns:
        Обновленный mapping
    """
    property_groups = mapping.setdefault("property_groups", {})
    
    created_count = 0
    existing_count = 0
    skipped_count = 0
    
    print("\n" + "=" * 80)
    print("СИНХРОНИЗАЦИЯ PROPERTY GROUPS")
    print("=" * 80)
    if dry_run:
        print("[DRY-RUN MODE] Изменения не будут сохранены")
    print()
    
    # Сортируем для консистентного вывода
    sorted_names = sorted(property_names.items(), key=lambda x: x[1])
    
    for normalized, original_name in sorted_names:
        # Проверяем, есть ли уже в mapping
        if original_name in property_groups:
            existing_uuid = property_groups[original_name]
            # Проверяем, существует ли в Shopware
            if not dry_run:
                existing = client.find_property_group_by_name(original_name)
                if existing and existing == existing_uuid:
                    print(f"[SKIP] '{original_name}' -> {existing_uuid} (уже в mapping)")
                    existing_count += 1
                    continue
                elif existing and existing != existing_uuid:
                    # Обновляем mapping если UUID изменился
                    property_groups[original_name] = existing
                    print(f"[UPDATE] '{original_name}' -> {existing} (UUID обновлен)")
                    existing_count += 1
                    continue
        
        # Ищем существующую группу в Shopware
        if not dry_run:
            existing_uuid = client.find_property_group_by_name(original_name)
            if existing_uuid:
                property_groups[original_name] = existing_uuid
                print(f"[FOUND] '{original_name}' -> {existing_uuid} (существует в Shopware)")
                existing_count += 1
                continue
        
        # Создаем новую группу
        new_uuid = uuid4().hex
        
        payload = {
            "id": new_uuid,
            "name": original_name,
            "filterable": True,
            "displayType": "text",
            "sortingType": "alphanumeric",
            "translations": {
                "ru-RU": {
                    "name": original_name,
                }
            },
        }
        
        if dry_run:
            print(f"[DRY-RUN] Создал бы: '{original_name}' -> {new_uuid}")
        else:
            try:
                client.create_property_group(payload)
                property_groups[original_name] = new_uuid
                print(f"[CREATE] '{original_name}' -> {new_uuid}")
                created_count += 1
            except Exception as e:
                print(f"[ERROR] Не удалось создать '{original_name}': {e}")
                skipped_count += 1
                continue
    
    print("\n" + "=" * 80)
    print("РЕЗУЛЬТАТЫ")
    print("=" * 80)
    print(f"Создано: {created_count}")
    print(f"Найдено существующих: {existing_count}")
    print(f"Ошибок: {skipped_count}")
    print(f"Всего обработано: {len(property_names)}")
    
    # Обновляем timestamp
    mapping["last_updated"] = datetime.now(timezone.utc).isoformat()
    
    return mapping


def build_shopware_client(cfg: Dict[str, Any]) -> ShopwareClient:
    """Создает Shopware клиент из конфигурации."""
    shopware_cfg = ShopwareConfig(
        url=cfg["shopware"]["url"],
        access_key_id=cfg["shopware"]["access_key_id"],
        secret_access_key=cfg["shopware"]["secret_access_key"],
    )
    return ShopwareClient(shopware_cfg)


def main() -> int:
    """Главная функция."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    
    parser = argparse.ArgumentParser(
        description="Автоматический Property Schema Sync для Shopware из snapshot InSales"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help=f"Путь к config.json (по умолчанию: {CONFIG_PATH})",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=SNAPSHOT_PATH,
        help=f"Путь к products.ndjson (по умолчанию: {SNAPSHOT_PATH})",
    )
    parser.add_argument(
        "--map",
        type=Path,
        default=MAP_PATH,
        help=f"Путь к migration_map.json (по умолчанию: {MAP_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry-run режим (не создает Property Groups, только логирует)",
    )
    
    args = parser.parse_args()
    
    # Проверка файлов
    if not args.config.exists():
        print(f"[ERROR] Конфигурация не найдена: {args.config}")
        return 1
    
    if not args.snapshot.exists():
        print(f"[ERROR] Snapshot не найден: {args.snapshot}")
        return 1
    
    # Загрузка конфигурации
    try:
        config = load_json(args.config)
    except Exception as e:
        print(f"[ERROR] Не удалось загрузить конфигурацию: {e}")
        return 1
    
    # Загрузка mapping
    mapping = load_json(
        args.map,
        default={
            "categories": {},
            "properties": {},
            "products": {},
            "property_groups": {},
            "last_updated": None,
        },
    )
    
    # Извлечение уникальных Property Groups
    print("=" * 80)
    print("ИЗВЛЕЧЕНИЕ ХАРАКТЕРИСТИК ИЗ SNAPSHOT")
    print("=" * 80)
    property_names, property_counts, all_variants = extract_unique_property_names(args.snapshot)
    
    if not property_names:
        print("[WARNING] Не найдено ни одной характеристики в snapshot")
        return 0
    
    # Дедупликация
    property_names = deduplicate_property_names(property_names)
    
    print(f"\n[INFO] Уникальных Property Groups после дедупликации: {len(property_names)}")
    
    # Поиск дубликатов
    duplicates = {k: v for k, v in all_variants.items() if len(v) > 1}
    
    print("\n" + "=" * 80)
    print("СПИСОК PROPERTY GROUPS")
    print("=" * 80)
    print(f"\nВсего уникальных групп: {len(property_names)}\n")
    
    # В dry-run выводим только топ-20 по алфавиту
    sorted_names = sorted(property_names.items(), key=lambda x: x[1])
    display_count = min(20, len(sorted_names)) if args.dry_run else len(sorted_names)
    
    for i, (normalized, original) in enumerate(sorted_names[:display_count], 1):
        count = property_counts.get(original, 0)
        variants = all_variants.get(normalized, [])
        is_duplicate = len(variants) > 1
        
        marker = " [ДУБЛИКАТ]" if is_duplicate else ""
        print(f"{i:3d}. {original} (встречается: {count} раз){marker}")
        
        if is_duplicate:
            print(f"     Варианты: {', '.join(variants)}")
    
    if display_count < len(sorted_names):
        print(f"\n... и ещё {len(sorted_names) - display_count} групп (показаны первые {display_count})")
    
    if duplicates:
        print("\n" + "=" * 80)
        print("ДУБЛИКАТЫ (нормализованные названия совпадают)")
        print("=" * 80)
        print(f"\nНайдено {len(duplicates)} групп с дубликатами:\n")
        for normalized, variants in sorted(duplicates.items(), key=lambda x: x[0])[:10]:
            print(f"  '{normalized}' -> варианты:")
            for variant in variants:
                count = property_counts.get(variant, 0)
                print(f"    - '{variant}' ({count} раз)")
        if len(duplicates) > 10:
            print(f"\n... и ещё {len(duplicates) - 10} групп с дубликатами")
    
    # Создание Shopware клиента
    try:
        client = build_shopware_client(config)
    except Exception as e:
        print(f"[ERROR] Не удалось создать Shopware клиент: {e}")
        return 1
    
    # Синхронизация
    try:
        updated_mapping = sync_property_groups(
            client=client,
            property_names=property_names,
            mapping=mapping,
            dry_run=args.dry_run,
        )
    except Exception as e:
        print(f"[ERROR] Ошибка синхронизации: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Сохранение mapping
    if not args.dry_run:
        try:
            save_json(args.map, updated_mapping)
            print(f"\n[OK] Mapping сохранен в: {args.map}")
        except Exception as e:
            print(f"[ERROR] Не удалось сохранить mapping: {e}")
            return 1
    else:
        print(f"\n[DRY-RUN] Mapping не сохранен (dry-run режим)")
    
    print("\n" + "=" * 80)
    print("ЗАВЕРШЕНО")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

