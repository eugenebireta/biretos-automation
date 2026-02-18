#!/usr/bin/env python3
"""
End-to-End Demo for RFQ Pipeline

Usage:
    python demo_rfq.py samples/sample_email.txt

Purpose:
    Demonstrate complete RFQ pipeline from raw text to structured output.
    Creates physical JSON file with results.

Flow:
    1. Read raw text from file
    2. Generate trace_id
    3. Call execute_rfq_v1_from_ocr()
    4. Save result to output/demo_rfq_<trace_id>.json
    5. Display summary
"""

import json
import os
import socket
import sys
from pathlib import Path
from uuid import uuid4

# Add parent directory to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "ru_worker"))

import psycopg2
from rfq_parser import parse_rfq_deterministic
try:
    from ru_worker import execute_rfq_v1_from_ocr
except ImportError:
    from ru_worker.ru_worker import execute_rfq_v1_from_ocr

REQUIRED_DB_ENV_KEYS = [
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
]


def ensure_output_dir():
    """Create output directory if it doesn't exist."""
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


def read_sample_file(filepath: str) -> str:
    """Read raw text from sample file."""
    path = Path(filepath)
    
    if not path.exists():
        print(f"ERROR: File not found: {filepath}")
        sys.exit(1)
    
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if not content.strip():
        print(f"ERROR: File is empty: {filepath}")
        sys.exit(1)
    
    return content


def _build_offline_result(raw_text: str) -> dict:
    """Build deterministic fallback result without database."""
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
        "price_status": "skipped",
        "price_items_total": len(deterministic.get("candidate_part_numbers", [])),
        "price_items_found": 0,
        "price_error": None,
        "price_audit": None,
    }


def _missing_db_env_keys() -> list:
    missing = []
    for key in REQUIRED_DB_ENV_KEYS:
        value = os.environ.get(key)
        if value is None or not str(value).strip():
            missing.append(key)
    return missing


def _preflight_db_socket(host: str, port: int) -> str | None:
    """Return socket error string when DB endpoint is unreachable."""
    try:
        with socket.create_connection((host, port), timeout=3):
            return None
    except OSError as exc:
        return str(exc)


def run_demo(sample_file: str) -> None:
    """
    Run end-to-end RFQ pipeline demo.
    
    Args:
        sample_file: Path to sample text file
    """
    print("=" * 60)
    print("RFQ Pipeline End-to-End Demo")
    print("=" * 60)
    print()
    
    # Read sample file
    print(f"Reading sample file: {sample_file}")
    raw_text = read_sample_file(sample_file)
    print(f"[OK] Loaded {len(raw_text)} characters")
    print()
    
    # Display sample text
    print("Sample text:")
    print("-" * 60)
    print(raw_text[:200] + ("..." if len(raw_text) > 200 else ""))
    print("-" * 60)
    print()
    
    result = None
    trace_id = None
    conn = None

    try:
        missing_db_env = _missing_db_env_keys()
        if missing_db_env:
            print("[INFO] Running in offline mode (no DB configured)")
            print()
            result = _build_offline_result(raw_text)
            trace_id = result.get("trace_id")
        else:
            db_host = os.environ["POSTGRES_HOST"].strip()
            db_port = int(os.environ["POSTGRES_PORT"].strip())
            db_name = os.environ["POSTGRES_DB"].strip()
            db_user = os.environ["POSTGRES_USER"].strip()
            db_password = os.environ["POSTGRES_PASSWORD"]

            preflight_error = _preflight_db_socket(db_host, db_port)
            if preflight_error:
                print(f"[WARN] Database connection failed: {preflight_error}")
                print("[INFO] Fallback to deterministic extraction mode")
                print()
                result = _build_offline_result(raw_text)
                trace_id = result.get("trace_id")
            else:
                # Force UTF-8 for libpq error messages before connecting.
                os.environ["PGCLIENTENCODING"] = "UTF8"
                try:
                    # Connect to database
                    print("Connecting to database...")
                    conn = psycopg2.connect(
                        host=db_host,
                        port=db_port,
                        database=db_name,
                        user=db_user,
                        password=db_password,
                        connect_timeout=5,
                    )
                    print("[OK] Connected")
                    print()

                    # Prepare payload
                    payload = {
                        "text": raw_text,
                        "source": "demo",
                        "llm_enabled": False  # Use deterministic parser only for demo
                    }

                    # Execute RFQ pipeline
                    print("Executing RFQ pipeline...")
                    result = execute_rfq_v1_from_ocr(payload, conn)
                    print("[OK] Pipeline completed successfully")
                    print()

                    trace_id = result.get("trace_id")
                except UnicodeDecodeError:
                    healthcheck_error = _preflight_db_socket(db_host, db_port)
                    if healthcheck_error:
                        real_error = f"cannot reach PostgreSQL at {db_host}:{db_port} ({healthcheck_error})"
                    else:
                        real_error = (
                            f"PostgreSQL endpoint {db_host}:{db_port} is reachable, "
                            "but authentication/startup failed (check DB credentials)."
                        )
                    print(f"[WARN] Database connection failed: {real_error}")
                    print("[INFO] Fallback to deterministic extraction mode")
                    print()

                    result = _build_offline_result(raw_text)
                    trace_id = result.get("trace_id")
                except Exception as db_error:
                    print(f"[WARN] Database connection failed: {db_error}")
                    print("[INFO] Fallback to deterministic extraction mode")
                    print()

                    result = _build_offline_result(raw_text)
                    trace_id = result.get("trace_id")

        # Prepare output
        output_data = {
            "trace_id": trace_id,
            "rfq_id": result.get("rfq_id"),
            "status": "DONE",
            "items_count": result.get("items_count"),
            "part_numbers": result.get("sample_parts", []),
            "contact": {
                "emails": result.get("emails", []),
                "phones": result.get("phones", [])
            },
            "company": {
                "inn": result.get("inn")
            },
            "parsing_metadata": {
                "llm_used": result.get("llm_used", False)
            },
            "confidence_overall": result.get("confidence_overall", 0.0),
            "confidence_breakdown": result.get("confidence_breakdown", {}),
            "price_status": result.get("price_status", "skipped"),
            "price_items_total": result.get("price_items_total", result.get("items_count", 0)),
            "price_items_found": result.get("price_items_found", 0),
            "price_error": result.get("price_error"),
            "price_audit": result.get("price_audit"),
            "raw_text": raw_text
        }

        # Save to file
        output_dir = ensure_output_dir()
        output_file = output_dir / f"demo_rfq_{trace_id}.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print("[OK] Result saved to file")
        print()

        # Display summary
        print("=" * 60)
        print("DEMO COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print()
        print(f"Trace ID:     {trace_id}")
        print(f"RFQ ID:       {result.get('rfq_id')}")
        print(f"Status:       DONE")
        print(f"Items count:  {result.get('items_count')}")
        print(f"Output file:  {output_file}")
        print(f"Confidence:   {result.get('confidence_overall', 0.0):.4f}")
        print(f"Price status: {result.get('price_status', 'skipped')}")
        print()

        # Display extracted data
        print("Extracted data:")
        print(f"  Part numbers: {result.get('sample_parts', [])}")
        print(f"  Emails:       {result.get('emails', [])}")
        print(f"  Phones:       {result.get('phones', [])}")
        print(f"  INN:          {result.get('inn')}")
        print("  Confidence breakdown:")
        for key, value in result.get("confidence_breakdown", {}).items():
            print(f"    - {key}: {value:.2f}")
        print()

        print("[OK] You can now open the output file to see full results")
        print()

    except Exception as e:
        print()
        print("=" * 60)
        print("DEMO FAILED")
        print("=" * 60)
        print()
        print(f"Error: {e}")
        print()
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        if conn is not None:
            conn.close()


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python demo_rfq.py <sample_file>")
        print()
        print("Example:")
        print("  python demo_rfq.py samples/sample_email.txt")
        print()
        sys.exit(1)
    
    sample_file = sys.argv[1]
    run_demo(sample_file)


if __name__ == "__main__":
    main()
