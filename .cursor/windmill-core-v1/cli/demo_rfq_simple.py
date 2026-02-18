#!/usr/bin/env python3
"""
Simplified End-to-End Demo for RFQ Pipeline (without database)

Usage:
    python demo_rfq_simple.py samples/sample_email.txt

Purpose:
    Demonstrate RFQ parsing and canonical model conversion without database dependency.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

# Add parent directory to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "ru_worker"))

from rfq_parser import parse_rfq_deterministic
from rfq_converter import convert_to_canonical


def ensure_output_dir():
    """Create output directory if it doesn't exist."""
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


def read_sample_file(filepath: str) -> str:
    """Read raw text from sample file."""
    sample_path = Path(__file__).parent.parent / filepath
    
    if not sample_path.exists():
        print(f"ERROR: Sample file not found: {sample_path}")
        sys.exit(1)
    
    with open(sample_path, 'r', encoding='utf-8') as f:
        return f.read()


def run_demo(sample_file: str) -> None:
    """Run the RFQ demo pipeline."""
    print("=" * 60)
    print("RFQ Pipeline End-to-End Demo (Simplified)")
    print("=" * 60)
    print()
    
    # Step 1: Read sample file
    print(f"Reading sample file: {sample_file}")
    raw_text = read_sample_file(sample_file)
    print(f"[OK] Loaded {len(raw_text)} characters")
    print()
    
    print("Sample text:")
    print("-" * 60)
    preview = raw_text[:200] + "..." if len(raw_text) > 200 else raw_text
    print(preview)
    print("-" * 60)
    print()
    
    # Step 2: Generate trace_id
    trace_id = uuid4()
    rfq_id = uuid4()
    print(f"Generated trace_id: {trace_id}")
    print(f"Generated rfq_id: {rfq_id}")
    print()
    
    try:
        # Step 3: Parse RFQ (deterministic only)
        print("Parsing RFQ...")
        parsed_result = parse_rfq_deterministic(raw_text)
        print("[OK] Parsing completed")
        print()
        
        # Step 4: Convert to canonical model
        print("Converting to canonical model...")
        canonical_request = convert_to_canonical(
            merged_dict=parsed_result,
            raw_text=raw_text,
            source="demo",
            request_id=rfq_id,
            created_at=datetime.now(timezone.utc)
        )
        print("[OK] Canonical model created")
        print()
        
        # Step 5: Prepare output data
        output_data = {
            "trace_id": str(trace_id),
            "rfq_id": str(rfq_id),
            "status": "DONE",
            "items_count": len(canonical_request.items),
            "part_numbers": [item.part_number for item in canonical_request.items],
            "contact": {
                "emails": canonical_request.contact.emails,
                "phones": canonical_request.contact.phones
            },
            "company": {
                "inn": canonical_request.company.inn
            },
            "parsing_metadata": canonical_request.parsing_metadata,
            "raw_text": raw_text
        }
        
        # Step 6: Save to file
        output_dir = ensure_output_dir()
        output_file = output_dir / f"demo_rfq_{trace_id}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print("[OK] Result saved to file")
        print()
        
        # Step 7: Display summary
        print("=" * 60)
        print("DEMO RESULTS")
        print("=" * 60)
        print(f"Trace ID: {trace_id}")
        print(f"Status: DONE")
        print(f"Output file: {output_file}")
        print()
        print(f"Extracted Data:")
        print(f"  - Part numbers: {len(output_data['part_numbers'])}")
        for pn in output_data['part_numbers']:
            print(f"    * {pn}")
        print(f"  - Emails: {output_data['contact']['emails']}")
        print(f"  - Phones: {output_data['contact']['phones']}")
        print(f"  - INN: {output_data['company']['inn']}")
        print()
        print("[OK] You can now open the output file to see full results")
        
    except Exception as e:
        print(f"ERROR: Pipeline failed")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    if len(sys.argv) != 2:
        print("Usage: python demo_rfq_simple.py <sample_file>")
        print("Example: python demo_rfq_simple.py samples/sample_email.txt")
        sys.exit(1)
    
    sample_file = sys.argv[1]
    run_demo(sample_file)


if __name__ == "__main__":
    main()
