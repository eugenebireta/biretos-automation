"""
Утилита для безопасного анализа крупных JSON-ответов T-Bank.

Скрипт выводит только сводную информацию: тип корневого объекта,
список ключей (для dict), длину (для list) и несколько примеров.
Полный JSON в терминал не печатается.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, List


def summarize_payload(payload: Any, *, max_preview: int = 3) -> None:
    """Печатает краткую сводку без основного содержимого."""
    if isinstance(payload, dict):
        keys = list(payload.keys())
        print(f"type=dict, keys_total={len(keys)}")
        preview = ", ".join(keys[:max_preview])
        if len(keys) > max_preview:
            preview += ", ..."
        print(f"keys_preview=[{preview}]")
        for key in keys[:max_preview]:
            print(f"  key '{key}': type={type(payload[key]).__name__}")
    elif isinstance(payload, list):
        print(f"type=list, len={len(payload)}")
        for idx, item in enumerate(payload[:max_preview]):
            print(f"  item[{idx}] type={type(item).__name__}")
            if isinstance(item, dict):
                sub_keys = list(item.keys())
                preview = ", ".join(sub_keys[:max_preview])
                if len(sub_keys) > max_preview:
                    preview += ", ..."
                print(f"    keys={preview}")
    else:
        print(f"type={type(payload).__name__}")


def load_payload(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def extract_path(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if part == "":
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                idx = int(part)
            except ValueError:
                print(f"[warn] Нельзя обратиться по ключу '{part}' внутри списка")
                return None
            if idx >= len(current):
                print(f"[warn] Индекс {idx} вне диапазона списка длиной {len(current)}")
                return None
            current = current[idx]
        else:
            print(f"[warn] Путь '{path}' недоступен (тип {type(current).__name__})")
            return None
    return current


def parse_cli(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Краткий анализ JSON-ответов.")
    parser.add_argument(
        "files",
        nargs="+",
        help="Пути к JSON-файлам (можно несколько)",
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Точка входа для дополнительного анализа (например, consignments или consignments.0.items)",
    )
    parser.add_argument(
        "--preview",
        type=int,
        default=3,
        help="Максимальное число отображаемых элементов предпросмотра",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    opts = parse_cli(argv)
    if not opts.files:
        print("Укажите хотя бы один JSON-файл для анализа.")
        return 1
    for name in opts.files:
        path = Path(name).expanduser().resolve()
        if not path.exists():
            print(f"[warn] Файл не найден: {path}")
            continue
        print(f"=== {path} ===")
        payload = load_payload(path)
        summarize_payload(payload, max_preview=opts.preview)
        for raw_path in (opts.path or []):
            target = extract_path(payload, raw_path)
            if target is None:
                continue
            print(f"-- path: {raw_path}")
            summarize_payload(target, max_preview=opts.preview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

