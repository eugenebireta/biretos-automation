"""
Запрашивает свежий список накладных из T-Bank и сохраняет ответ в diagnostics/.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Optional

DEFAULT_URL = "https://api.tbank.ru"
OUTPUT_PATH = Path("diagnostics") / "t_bank_raw_response.json"


def load_token() -> str:
    env_path = Path(".env")
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("TBANK_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("Переменная TBANK_TOKEN не найдена в .env")


def build_url(limit: int = 20, status: Optional[str] = None) -> str:
    base = os.environ.get("TBANK_API_URL", DEFAULT_URL).rstrip("/")
    query_params: Dict[str, str] = {"limit": str(limit)}
    if status:
        query_params["status"] = status
    query = urllib.parse.urlencode(query_params)
    return f"{base}/v1/consignments?{query}"


def fetch_consignments(token: str, *, limit: int = 20, status: Optional[str] = None) -> dict:
    url = build_url(limit=limit, status=status)
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    context = ssl.create_default_context()
    with urllib.request.urlopen(req, context=context, timeout=30) as resp:
        return json.load(resp)


def main() -> None:
    parser = argparse.ArgumentParser(description="Получение свежего ответа T-Bank API.")
    parser.add_argument("--limit", type=int, default=20, help="Кол-во записей (query param limit)")
    parser.add_argument("--status", type=str, default=None, help="Фильтр status, если поддерживается API")
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="Путь для сохранения ответа (по умолчанию diagnostics/t_bank_raw_response.json)",
    )
    args = parser.parse_args()

    diagnostics_dir = Path("diagnostics")
    diagnostics_dir.mkdir(exist_ok=True)
    token = load_token()
    try:
        payload = fetch_consignments(token, limit=args.limit, status=args.status)
    except urllib.error.HTTPError as err:
        args.output.write_text(
            json.dumps(
                {
                    "error": err.reason,
                    "status": err.code,
                    "body": err.read().decode("utf-8", errors="replace"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

