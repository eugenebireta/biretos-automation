"""Retry specs extraction on 257 datasheets where first Gemini pass returned empty specs.

Prior run succeeded on titles (252/302) but specs filled for only 45/302.
Root cause: generic prompt didn't push Gemini hard enough on spec tables.

This retry:
- Only runs on SKUs with existing datasheet but empty specs
- Uses a focused prompt requesting concrete fields per category
- Preserves prior extraction data (title, brand, etc.) — only fills specs block
- Writes results to datasheet_extracted.json + merges to evidence files
"""
from __future__ import annotations

import json
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.app_secrets import get_secret

ROOT = Path(__file__).resolve().parent.parent.parent
DS_DIR = ROOT / "downloads" / "datasheets_v2"
EV_DIR = ROOT / "downloads" / "evidence"
EXTRACTED = ROOT / "downloads" / "staging" / "tier_collector_output" / "datasheet_extracted.json"
TRAIN_DIR = ROOT / "downloads" / "knowledge" / "training_data" / "specs_extraction"


PROMPT = """You are parsing a product datasheet PDF. Extract technical specifications THOROUGHLY.

Return ONLY valid JSON:
{
  "specs": {"<param>": "<value>"},
  "weight_g": "<number only, e.g. 250>",
  "dimensions_mm": "<LxWxH e.g. 120x80x45>",
  "ean": "<13 digits or empty>",
  "series": "<product family>",
  "certifications": ["CE", "EN54-18", ...]
}

SPECS FIELD — include EVERY concrete technical parameter you can find:
- Electrical: voltage (V), current (A, mA), power (W), frequency (Hz)
- Physical: dimensions LxWxH, weight, housing/enclosure material, color
- Environmental: operating temperature, IP rating, humidity range
- Performance: detection range, sensitivity, response time, output type
- Interface: connector type, cable, mounting type, communication protocol
- Compliance: EN/IEC/UL standards, certifications
- Any numeric values in tables (do not skip tables!)

If datasheet has a "Technical Data" / "Specifications" / "Specifications tabulaire" / "Technische Daten" section — extract EVERY row.

Do NOT skip specs because they seem obvious. Extract literally.

If a value is truly absent, omit the key. Do NOT write "N/A" or "not specified".

Return empty specs {} ONLY if the PDF genuinely has no technical specifications (rare for datasheets).
"""


def extract_pdf_text(pdf_path: Path, max_pages: int = 20) -> str:
    """Extract text from PDF via PyMuPDF (Gemini-budget-independent)."""
    import fitz
    doc = fitz.open(str(pdf_path))
    chunks = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        chunks.append(page.get_text())
    doc.close()
    return "\n\n".join(chunks)[:15000]  # cap to keep request fast


def _load_gemini_key() -> str:
    from pathlib import Path as _P
    for p in [_P("auditor_system/config/.env.auditors"), _P("downloads/.env")]:
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.startswith("GEMINI_API_KEY="):
                    return line.split("=", 1)[1].strip()
    raise RuntimeError("GEMINI_API_KEY not found")


def main():
    import argparse
    import anthropic

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Cap number of SKUs to process")
    parser.add_argument("--apply", action="store_true", help="Merge results into evidence files")
    parser.add_argument("--model", default="claude-haiku-4-5", help="claude-haiku-4-5 | claude-sonnet-4-6 | gemini-2.5-flash | gemini-2.5-pro")
    parser.add_argument("--skus", default="", help="Comma-separated PN list (overrides auto-target selection)")
    parser.add_argument("--no-merge", action="store_true", help="Skip writing to datasheet_extracted.json (compare runs)")
    args = parser.parse_args()

    is_gemini = args.model.startswith("gemini")
    if "haiku" in args.model:
        model_tag, in_rate, out_rate = "haiku", 1.0, 5.0
    elif "sonnet" in args.model:
        model_tag, in_rate, out_rate = "sonnet", 3.0, 15.0
    elif "gemini-2.5-flash" in args.model:
        model_tag, in_rate, out_rate = "gemini_flash", 0.30, 2.50
    elif "gemini-2.5-pro" in args.model:
        model_tag, in_rate, out_rate = "gemini_pro", 1.25, 10.0
    else:
        model_tag, in_rate, out_rate = args.model, 1.0, 5.0
    TRAIN_DIR.mkdir(parents=True, exist_ok=True)

    gemini_client = None
    if is_gemini:
        from google import genai
        gemini_client = genai.Client(api_key=_load_gemini_key())
        client = None
    else:
        client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"), timeout=120.0, max_retries=3)

    extracted = json.loads(EXTRACTED.read_text(encoding="utf-8")) if EXTRACTED.exists() else {}

    # Find SKUs with datasheet PDF but empty specs
    if args.skus:
        targets = [s.strip() for s in args.skus.split(",") if s.strip()]
    else:
        targets = []
        for pn, data in extracted.items():
            if data.get("specs"):
                continue
            pdf_path = DS_DIR / f"{pn}.pdf"
            if pdf_path.exists() and "catalog" not in pn.lower():
                targets.append(pn)

    if args.limit:
        targets = targets[:args.limit]

    print(f"Retrying specs extraction on {len(targets)} SKUs with empty specs")
    print("=" * 90)

    ok = 0
    failed = 0
    specs_added = 0
    total_cost = 0.0

    for idx, pn in enumerate(targets, 1):
        pdf_path = DS_DIR / f"{pn}.pdf"
        size_kb = pdf_path.stat().st_size // 1024
        print(f"  [{idx}/{len(targets)}] {pn:<22} ({size_kb} KB)... ", end="", flush=True)

        try:
            pdf_text = extract_pdf_text(pdf_path)
            if len(pdf_text) < 200:
                print(f"SKIP: PDF text too short ({len(pdf_text)} chars, likely scan-only)")
                failed += 1
                continue

            full_prompt = f"{PROMPT}\n\n--- DATASHEET TEXT ---\n{pdf_text}"
            if is_gemini:
                # Gemini SDK doesn't expose per-call timeout — wrap in a thread with hard cap.
                import concurrent.futures
                def _gemini_call():
                    return gemini_client.models.generate_content(
                        model=args.model,
                        contents=full_prompt,
                    )
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(_gemini_call)
                    try:
                        resp = fut.result(timeout=180)
                    except concurrent.futures.TimeoutError:
                        raise RuntimeError("gemini call exceeded 180s timeout")
                raw = (resp.text or "").strip()
                usage_in = getattr(resp.usage_metadata, "prompt_token_count", 0) or 0
                usage_out = getattr(resp.usage_metadata, "candidates_token_count", 0) or 0
                import sys as _sys2
                from pathlib import Path as _Path2
                _sys2.path.insert(0, str(_Path2(__file__).resolve().parent.parent.parent))
                from orchestrator._api_cost_tracker import log_api_call as _log_api_call
                _log_api_call(__file__, args.model, getattr(resp, "usage_metadata", None))
            else:
                response = client.messages.create(
                    model=args.model,
                    max_tokens=4000,
                    messages=[{"role": "user", "content": full_prompt}],
                )
                import sys as _sys
                from pathlib import Path as _Path
                _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent.parent))
                from orchestrator._api_cost_tracker import log_api_call
                log_api_call(__file__, args.model, response.usage)
                raw = response.content[0].text.strip()
                usage_in = response.usage.input_tokens
                usage_out = response.usage.output_tokens
            if "```" in raw:
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            data = json.loads(raw)
            specs = data.get("specs", {}) or {}
            weight = data.get("weight_g", "")
            dims = data.get("dimensions_mm", "")
            series = data.get("series", "")

            # Merge — preserve existing title/brand/etc., only fill gaps
            prev = extracted.get(pn, {})
            prev["specs"] = specs
            if weight and not prev.get("weight_g"):
                prev["weight_g"] = weight
            if dims and not prev.get("dimensions_mm"):
                prev["dimensions_mm"] = dims
            if series and not prev.get("series"):
                prev["series"] = series
            if data.get("ean") and not prev.get("ean"):
                prev["ean"] = data["ean"]
            if data.get("certifications") and not prev.get("certifications"):
                prev["certifications"] = data["certifications"]

            # Provenance footprint (per 4th external reviewer 2026-04-18).
            # Every extraction records its (model, prompt_sha, pdf_sha, timestamp)
            # so downstream auditors can answer: who produced this spec, when,
            # with what model. Required for LLM regression detection.
            import hashlib as _h
            from datetime import datetime, timezone
            pdf_sha = _h.sha256(pdf_path.read_bytes()).hexdigest()
            prompt_sha_16 = _h.sha256(PROMPT.encode("utf-8")).hexdigest()[:16]
            prev["extraction_provenance"] = {
                "model_id": args.model,
                "prompt_sha_16": prompt_sha_16,
                "pdf_sha256": pdf_sha,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "specs_count": len(specs) if isinstance(specs, dict) else 0,
                "ran_via_script": "scripts/pipeline_v2/_extract_specs_retry.py",
                # Negative result reason (per 4th reviewer recommendation): if
                # specs are empty but PDF had enough text, mark as likely non-
                # datasheet. Downstream tools can then skip re-extraction until
                # a new datasheet arrives.
                "reason": ("empty_model_output" if not specs else None),
            }
            extracted[pn] = prev

            specs_count = len(specs)
            if specs_count > 0:
                specs_added += 1
            print(f"OK specs={specs_count} weight={weight or '-'} dims={dims or '-'} series={series or '-'}")
            ok += 1

            cost = (usage_in * in_rate + usage_out * out_rate) / 1_000_000
            total_cost += cost

            # Training pair dump — (pdf_text, model_output) for local-model fine-tuning.
            # One file per (pn, model) so Haiku/Sonnet/Gemini results can coexist side-by-side.
            train_file = TRAIN_DIR / f"{pn}__{model_tag}.json"
            train_file.write_text(json.dumps({
                "pn": pn,
                "model": args.model,
                "prompt": PROMPT,
                "pdf_text": pdf_text,
                "pdf_bytes": pdf_path.stat().st_size,
                "output": data,
                "usage": {
                    "input_tokens": usage_in,
                    "output_tokens": usage_out,
                    "cost_usd": round(cost, 5),
                },
            }, indent=2, ensure_ascii=False), encoding="utf-8")

        except Exception as e:
            print(f"FAIL: {str(e)[:80]}")
            failed += 1

        # Periodic save
        if idx % 20 == 0 and not args.no_merge:
            EXTRACTED.write_text(json.dumps(extracted, indent=2, ensure_ascii=False), encoding="utf-8")

    # Final save of extractions
    if not args.no_merge:
        EXTRACTED.write_text(json.dumps(extracted, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nOK: {ok}, failed: {failed}, specs newly added: {specs_added}")
    print(f"Estimated cost: ~${total_cost:.2f}")

    if args.apply:
        print("\nMerging specs into evidence files...")
        merged = 0
        for pn, data in extracted.items():
            specs = data.get("specs", {}) or {}
            prov = data.get("extraction_provenance") or {}
            ev_file = EV_DIR / f"evidence_{pn}.json"
            if not ev_file.exists():
                continue
            ev = json.loads(ev_file.read_text(encoding="utf-8"))
            fd = ev.get("from_datasheet") or {}

            # Always record extraction history (append-only), even on empty
            # result — this way "extraction ran and found nothing" is
            # distinguishable from "extraction never ran".
            history = fd.get("extraction_history") or []
            if prov and (not history or history[-1].get("extracted_at") != prov.get("extracted_at")):
                history.append(prov)
                fd["extraction_history"] = history
                fd["latest_extraction"] = prov

            # Merge: don't overwrite existing non-empty specs
            if specs and not fd.get("specs"):
                fd["specs"] = specs
                fd["specs_count"] = len(specs)
                if data.get("weight_g") and not fd.get("weight_g"):
                    fd["weight_g"] = data["weight_g"]
                if data.get("dimensions_mm") and not fd.get("dimensions_mm"):
                    fd["dimensions_mm"] = data["dimensions_mm"]
                if data.get("series") and not fd.get("series"):
                    fd["series"] = data["series"]
                if data.get("certifications") and not fd.get("certifications"):
                    fd["certifications"] = data["certifications"]
                merged += 1
            ev["from_datasheet"] = fd
            ev_file.write_text(json.dumps(ev, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Merged specs into {merged} evidence files (provenance written to all attempted)")


if __name__ == "__main__":
    main()
