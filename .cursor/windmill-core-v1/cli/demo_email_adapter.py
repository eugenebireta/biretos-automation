#!/usr/bin/env python3
"""
Lightweight Email Adapter demo for RFQ pipeline.

Usage:
    python cli/demo_email_adapter.py <email_file.txt|email_file.eml>
"""

import json
import sys
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any, Dict, Tuple
from uuid import uuid4

# Add parent directory to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "ru_worker"))

import psycopg2

from config import get_config
from rfq_parser import parse_rfq_deterministic

try:
    from ru_worker import execute_rfq_v1_from_ocr
except ImportError:
    from ru_worker.ru_worker import execute_rfq_v1_from_ocr


def ensure_output_dir() -> Path:
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


def _extract_text_from_eml(path: Path) -> str:
    with open(path, "rb") as f:
        message = BytesParser(policy=policy.default).parse(f)

    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() != "text/plain":
                continue
            if part.get_content_disposition() == "attachment":
                continue
            content = part.get_content()
            if isinstance(content, str) and content.strip():
                return content
    else:
        content = message.get_content()
        if isinstance(content, str) and content.strip():
            return content

    raise ValueError(f"No plain text body found in: {path}")


def extract_email_body(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Email file not found: {file_path}")

    ext = path.suffix.lower()
    if ext == ".txt":
        text = path.read_text(encoding="utf-8")
    elif ext == ".eml":
        text = _extract_text_from_eml(path)
    else:
        raise ValueError("Unsupported file format. Use .txt or .eml")

    if not text.strip():
        raise ValueError("Email body is empty")
    return text


def _build_fallback_result(raw_text: str) -> Dict[str, Any]:
    deterministic = parse_rfq_deterministic(raw_text)
    inns = deterministic.get("company_identifiers", {}).get("inn", [])
    return {
        "rfq_id": str(uuid4()),
        "trace_id": str(uuid4()),
        "items_count": len(deterministic.get("candidate_part_numbers", [])),
        "sample_parts": deterministic.get("candidate_part_numbers", []),
        "emails": deterministic.get("emails", []),
        "phones": deterministic.get("phones", []),
        "inn": inns[0] if inns else None,
        "llm_used": False,
        "confidence_overall": deterministic.get("confidence_overall", 0.0),
        "confidence_breakdown": deterministic.get("confidence_breakdown", {}),
    }


def run_demo(email_file: str) -> Tuple[Path, Dict[str, Any]]:
    print("=" * 60)
    print("RFQ Email Adapter Demo")
    print("=" * 60)
    print()

    print(f"Reading email file: {email_file}")
    raw_text = extract_email_body(email_file)
    print(f"[OK] Loaded body length: {len(raw_text)}")
    print()

    conn = None
    result: Dict[str, Any]

    try:
        config = get_config()
        print("Connecting to database...")
        conn = psycopg2.connect(
            host=config.postgres_host or "localhost",
            port=config.postgres_port or 5432,
            database=config.postgres_db or "biretos_automation",
            user=config.postgres_user or "biretos_user",
            password=config.postgres_password,
        )
        print("[OK] Connected")
        print("Executing RFQ pipeline...")

        payload = {
            "text": raw_text,
            "source": "email",
            "llm_enabled": False,
        }
        result = execute_rfq_v1_from_ocr(payload, conn)
        print("[OK] Pipeline completed")
        print()
    except Exception as db_error:
        print(f"[WARN] Database pipeline unavailable: {db_error}")
        print("[INFO] Fallback to deterministic extraction mode")
        print()
        result = _build_fallback_result(raw_text)
    finally:
        if conn is not None:
            conn.close()

    output_data = {
        "trace_id": result.get("trace_id"),
        "rfq_id": result.get("rfq_id"),
        "status": "DONE",
        "items_count": result.get("items_count"),
        "part_numbers": result.get("sample_parts", []),
        "contact": {
            "emails": result.get("emails", []),
            "phones": result.get("phones", []),
        },
        "company": {
            "inn": result.get("inn"),
        },
        "parsing_metadata": {
            "llm_used": False,
        },
        "confidence_overall": result.get("confidence_overall", 0.0),
        "confidence_breakdown": result.get("confidence_breakdown", {}),
        "raw_text": raw_text,
    }

    output_dir = ensure_output_dir()
    output_file = output_dir / f"demo_email_adapter_{result.get('trace_id')}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print("[OK] Result saved to file")
    print()
    print(f"Trace ID:     {output_data['trace_id']}")
    print(f"Items count:  {output_data['items_count']}")
    print(f"Confidence:   {output_data['confidence_overall']:.4f}")
    print(f"Output file:  {output_file}")

    return output_file, output_data


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python cli/demo_email_adapter.py <email_file.txt|email_file.eml>")
        sys.exit(1)

    run_demo(sys.argv[1])


if __name__ == "__main__":
    main()

