"""Compare local Qwen2-VL-2B vs cloud Gemini on datasheet parsing.

Runs 10 PDF → JSON extraction through both, compares accuracy.
If local >= 70% match with Gemini — worth collecting more data for fine-tune.
"""
from __future__ import annotations

import json
import sys
import io
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
DS_DIR = ROOT / "downloads" / "datasheets_v2"
GEMINI_RESULTS = ROOT / "downloads" / "staging" / "tier_collector_output" / "datasheet_extracted.json"

# Test on 10 PDFs that Gemini successfully parsed with EAN
TEST_PNS = [
    "00020211",           # PEHA NOVA frame — EAN found
    "2CDG110146R0011",    # ABB — EAN + weight + dims
    "2CDG110177R0011",    # ABB — EAN + specs
    "3240197",            # Phoenix Contact — EAN + 12 specs
    "773111",             # PEHA — EAN + specs
    "773211",             # PEHA — EAN + 10 specs
    "775511",             # PEHA SCHUKO — EAN + 16 specs
    "1050000000",         # Weidmuller — EAN + 21 specs
    "193111",             # Pushbutton switch — EAN + 15 specs
    "902591",             # PEHA loudspeaker — EAN + 6 specs
]

PROMPT = (
    "IMPORTANT: Read ALL pages of this PDF.\n"
    "Extract product data. Return ONLY JSON:\n"
    '{"pn":"","brand":"","title":"","ean":"","specs":{}}\n'
    "Extract EAN code, title, and all technical specifications."
)


def run_local_qwen(pdf_paths: list[Path]) -> dict:
    """Run local Qwen2-VL-2B on PDFs (no fine-tune, baseline)."""
    import torch
    import fitz
    from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
    from PIL import Image
    import io as _io

    print("Loading Qwen2-VL-2B...", flush=True)

    model_id = "Qwen/Qwen2-VL-2B-Instruct"
    processor = AutoProcessor.from_pretrained(model_id, local_files_only=True, trust_remote_code=True)
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        model_id, torch_dtype=torch.bfloat16, device_map={"": 0},
        local_files_only=True, trust_remote_code=True,
    )
    model.eval()

    results = {}

    for pdf in pdf_paths:
        pn = pdf.stem
        print(f"  {pn}...", end=" ", flush=True)
        start = time.time()

        try:
            # Convert first 2 pages to images via PyMuPDF
            doc = fitz.open(str(pdf))
            images = []
            for pg_num in range(min(2, len(doc))):
                page = doc[pg_num]
                pix = page.get_pixmap(dpi=150)
                img_data = pix.tobytes("png")
                images.append(Image.open(_io.BytesIO(img_data)).convert("RGB"))
            doc.close()
            if not images:
                print("no pages")
                continue

            # Process first page (most info usually)
            img = images[0].convert("RGB")
            img.thumbnail((1024, 1024), Image.LANCZOS)

            messages = [{
                "role": "user",
                "content": [
                    {"type": "image", "image": img},
                    {"type": "text", "text": PROMPT},
                ],
            }]
            text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = processor(text=[text], images=[[img]], return_tensors="pt").to("cuda:0")

            with torch.no_grad():
                out = model.generate(**inputs, max_new_tokens=500, do_sample=False, temperature=0.1)
            raw = processor.batch_decode(
                out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True
            )[0].strip()

            # Try page 2 if page 1 didn't give EAN
            if len(images) > 1 and "ean" not in raw.lower():
                img2 = images[1].convert("RGB")
                img2.thumbnail((1024, 1024), Image.LANCZOS)
                messages2 = [{
                    "role": "user",
                    "content": [
                        {"type": "image", "image": img2},
                        {"type": "text", "text": "Extract EAN code and any other product data from this page. Return JSON."},
                    ],
                }]
                text2 = processor.apply_chat_template(messages2, tokenize=False, add_generation_prompt=True)
                inputs2 = processor(text=[text2], images=[[img2]], return_tensors="pt").to("cuda:0")
                with torch.no_grad():
                    out2 = model.generate(**inputs2, max_new_tokens=300, do_sample=False)
                raw_p2 = processor.batch_decode(
                    out2[:, inputs2["input_ids"].shape[1]:], skip_special_tokens=True
                )[0].strip()
                raw += "\n\n" + raw_p2

            elapsed = time.time() - start

            # Try parse JSON
            parsed = None
            if "```" in raw:
                parts = raw.split("```")
                for p in parts:
                    if p.startswith("json"): p = p[4:]
                    try:
                        parsed = json.loads(p.strip())
                        break
                    except Exception: continue
            if not parsed:
                try:
                    # Find { ... }
                    import re
                    m = re.search(r'\{.*?\}', raw, re.DOTALL)
                    if m:
                        parsed = json.loads(m.group())
                except Exception: pass

            if parsed:
                results[pn] = {
                    "parsed": parsed,
                    "raw": raw[:500],
                    "elapsed_sec": round(elapsed, 1),
                }
                ean = parsed.get("ean", "") if isinstance(parsed, dict) else ""
                print(f"OK ({elapsed:.1f}s) EAN={ean or '-'}")
            else:
                results[pn] = {"parsed": None, "raw": raw[:300], "elapsed_sec": round(elapsed, 1)}
                print(f"NO JSON ({elapsed:.1f}s)")

        except Exception as e:
            print(f"ERROR: {str(e)[:60]}")
            results[pn] = {"error": str(e)}

    # Clean up GPU
    del model
    del processor
    torch.cuda.empty_cache()

    return results


def compare_results(local_results: dict, gemini_results: dict) -> dict:
    """Compare local vs Gemini outputs."""
    comparison = {}

    for pn in TEST_PNS:
        gem = gemini_results.get(pn, {})
        loc = local_results.get(pn, {})
        loc_parsed = loc.get("parsed") or {}

        gem_ean = str(gem.get("ean", "")).strip()
        loc_ean = str(loc_parsed.get("ean", "")).strip() if isinstance(loc_parsed, dict) else ""

        gem_title = gem.get("title", "")[:100]
        loc_title = loc_parsed.get("title", "")[:100] if isinstance(loc_parsed, dict) else ""

        gem_specs = len(gem.get("specs", {})) if isinstance(gem.get("specs"), dict) else 0
        loc_specs = len(loc_parsed.get("specs", {})) if isinstance(loc_parsed, dict) and isinstance(loc_parsed.get("specs"), dict) else 0

        ean_match = (gem_ean and loc_ean and gem_ean.replace(" ", "") == loc_ean.replace(" ", ""))
        title_match = (gem_title and loc_title and (
            gem_title.lower()[:30] in loc_title.lower() or
            loc_title.lower()[:30] in gem_title.lower()
        ))

        comparison[pn] = {
            "gem_ean": gem_ean, "loc_ean": loc_ean, "ean_match": ean_match,
            "gem_title": gem_title, "loc_title": loc_title, "title_match": title_match,
            "gem_specs": gem_specs, "loc_specs": loc_specs,
            "local_elapsed": loc.get("elapsed_sec", 0),
        }

    return comparison


def main():
    # Load Gemini results
    gemini_all = json.loads(GEMINI_RESULTS.read_text(encoding="utf-8"))
    gemini_results = {pn: gemini_all.get(pn, {}) for pn in TEST_PNS if pn in gemini_all}
    print(f"Gemini results for {len(gemini_results)}/{len(TEST_PNS)} test PNs")

    # Get PDF paths
    pdf_paths = []
    for pn in TEST_PNS:
        p = DS_DIR / f"{pn}.pdf"
        if p.exists():
            pdf_paths.append(p)

    print(f"PDFs to test: {len(pdf_paths)}\n")

    # Run local Qwen
    print("=" * 90)
    print("LOCAL Qwen2-VL-2B (no fine-tune, baseline)")
    print("=" * 90)
    local_results = run_local_qwen(pdf_paths)

    # Compare
    comparison = compare_results(local_results, gemini_results)

    print("\n" + "=" * 90)
    print("COMPARISON: Local Qwen2-VL-2B vs Gemini 2.5 Flash")
    print("=" * 90)
    print(f"{'PN':<22} {'EAN match':<10} {'Title':<8} {'Specs (G/L)':<12} {'Time'}")
    print("-" * 70)

    ean_matches = 0
    title_matches = 0
    specs_close = 0

    for pn, c in comparison.items():
        ean_str = "YES" if c["ean_match"] else f"no ({c['loc_ean'] or '-'})"
        title_str = "YES" if c["title_match"] else "no"
        specs_str = f"{c['gem_specs']}/{c['loc_specs']}"

        if c["ean_match"]: ean_matches += 1
        if c["title_match"]: title_matches += 1
        if c['loc_specs'] >= c['gem_specs'] * 0.5: specs_close += 1

        print(f"{pn:<22} {ean_str:<10} {title_str:<8} {specs_str:<12} {c['local_elapsed']:.1f}s")

    print("-" * 70)
    n = len(comparison)
    print(f"  EAN match:    {ean_matches}/{n} ({ean_matches*100//n}%)")
    print(f"  Title match:  {title_matches}/{n} ({title_matches*100//n}%)")
    print(f"  Specs >= 50%: {specs_close}/{n} ({specs_close*100//n}%)")

    # Save
    out = ROOT / "downloads" / "training_v2" / "local_vs_gemini_comparison.json"
    out.write_text(json.dumps({
        "local_results": local_results,
        "comparison": comparison,
        "summary": {
            "ean_match_rate": ean_matches / n if n else 0,
            "title_match_rate": title_matches / n if n else 0,
            "specs_close_rate": specs_close / n if n else 0,
        },
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
