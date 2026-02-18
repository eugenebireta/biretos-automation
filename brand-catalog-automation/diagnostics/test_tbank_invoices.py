"""Диагностика эндпоинта T-Bank /v1/invoices."""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_BASE_URL = "https://api.tbank.ru"
OUTPUT_FILE = Path("brand-catalog-automation") / "diagnostics" / "tbank_invoices_test.json"
ENDPOINT = "/v1/invoices?limit=3&status=paid"


def load_env_value(key: str) -> Optional[str]:
    env_path = Path(".env")
    if not env_path.exists():
        return None

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"')
    return None


def load_token() -> str:
    token = load_env_value("TBANK_TOKEN")
    if token:
        return token
    raise RuntimeError("Переменная TBANK_TOKEN не найдена в .env")


def try_parse_json(data: str) -> Optional[Any]:
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


def fetch_invoices(base_url: str, token: str) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}{ENDPOINT}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    context = ssl.create_default_context()
    entry: Dict[str, Any] = {
        "endpoint": ENDPOINT,
        "url": url,
    }

    try:
        with urllib.request.urlopen(request, context=context, timeout=30) as resp:
            body_bytes = resp.read()
            body_text = body_bytes.decode("utf-8", errors="replace")
            entry.update(
                {
                    "status": resp.status,
                    "headers": dict(resp.getheaders()),
                    "body_raw": body_text,
                    "body_json": try_parse_json(body_text),
                }
            )
    except urllib.error.HTTPError as err:
        error_body = err.read().decode("utf-8", errors="replace")
        entry.update(
            {
                "status": err.code,
                "error": err.reason,
                "body_raw": error_body,
                "body_json": try_parse_json(error_body),
            }
        )
    except urllib.error.URLError as err:
        entry.update(
            {
                "status": None,
                "error": getattr(err, "reason", str(err)),
            }
        )

    return entry


def ensure_output_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def main() -> None:
    token = load_token()
    env_base = os.environ.get("TBANK_API_URL") or load_env_value("TBANK_API_URL")
    base_url = (env_base or DEFAULT_BASE_URL).rstrip("/")
    ensure_output_dir(OUTPUT_FILE)

    print(f"[tbank-invoices] Probing {ENDPOINT} ...")
    result = fetch_invoices(base_url, token)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "result": result,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[tbank-invoices] Saved results to {OUTPUT_FILE}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"[tbank-invoices] Ошибка: {exc}", file=sys.stderr)
        sys.exit(1)

















