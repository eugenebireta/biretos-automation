"""Generate quality SEO-ready Russian product descriptions for InSales.

For each of 207 InSales READY SKUs:
- Read all available data (datasheet specs, title, description, brand, series)
- Generate 200-400 word Russian description via Gemini
- SEO-friendly, with key specs, benefits, applications
- Save to evidence as `from_datasheet.description_seo_ru`
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
CANONICAL_FILE = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "canonical_products.json"
OUT_FILE = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "descriptions_seo.json"

PROMPT = """Напиши описание товара для интернет-магазина на русском языке. ОБЯЗАТЕЛЬНО 200-400 слов.

Товар:
- Бренд: {brand}
- Артикул: {pn}
- Серия: {series}
- Название: {title}
- Описание: {description}
- Характеристики: {specs}
- EAN: {ean}
- Размеры: {dimensions}
- Вес: {weight}

ОБЯЗАТЕЛЬНАЯ структура (4 параграфа, каждый >50 слов):
1. <p>Вступление — что это за товар, бренд, серия, назначение (60-80 слов)</p>
2. <p><b>Ключевые характеристики:</b></p><ul><li>...</li></ul> (минимум 5-8 пунктов)
3. <p><b>Применение:</b> Где и как используется (60-80 слов)</p>
4. <p><b>Преимущества:</b> Почему стоит выбрать (50-70 слов)</p>

Запреты:
- НЕ обрывай на середине предложения
- НЕ пиши меньше 200 слов
- НЕ используй markdown — только HTML <p> <b> <ul> <li>
- НЕ начинай с "Представляем"

Верни ТОЛЬКО HTML, начни с <p>."""


def main():
    from google import genai as genai_new
    from google.genai import types
    from scripts.app_secrets import get_secret

    client = genai_new.Client(api_key=get_secret("GEMINI_API_KEY"))
    canonical = json.loads(CANONICAL_FILE.read_text(encoding="utf-8"))
    existing = json.loads(OUT_FILE.read_text(encoding="utf-8")) if OUT_FILE.exists() else {}

    # Filter: only InSales READY
    targets = []
    for p in canonical:
        readiness = p.get("readiness", {})
        if readiness.get("insales") != "READY":
            continue
        pn = p.get("identity", {}).get("pn", "")
        if not pn or pn in existing:
            continue
        targets.append(p)

    print(f"Generating descriptions for {len(targets)} READY SKUs")
    print("=" * 80)

    stats = {"generated": 0, "skipped": 0, "error": 0}

    for idx, p in enumerate(targets):
        identity = p.get("identity", {})
        pn = identity.get("pn", "")
        brand = identity.get("brand", "")

        # Get datasheet block
        ev_file = EV_DIR / f"evidence_{pn}.json"
        ds_block = {}
        if ev_file.exists():
            d = json.loads(ev_file.read_text(encoding="utf-8"))
            ds_block = d.get("from_datasheet", {})

        title = ds_block.get("title") or p.get("title_ru", "") or f"{brand} {pn}"
        description = (p.get("best_description_ru", "") or "")[:500]
        specs = ds_block.get("specs", {}) or p.get("specs", {})
        if isinstance(specs, dict):
            specs_str = "; ".join(f"{k}: {v}" for k, v in list(specs.items())[:15])
        else:
            specs_str = ""
        series = ds_block.get("series") or identity.get("series", "")
        ean = ds_block.get("ean", "")
        dims = ds_block.get("dimensions_mm", "")
        weight = ds_block.get("weight_g", "")

        prompt = PROMPT.format(
            brand=brand or "не указан",
            pn=pn,
            series=series or "не указана",
            title=title,
            description=description or "нет",
            specs=specs_str or "нет",
            ean=ean or "нет",
            dimensions=dims or "нет",
            weight=weight or "нет",
        )

        print(f"  [{idx+1}/{len(targets)}] {pn:<22} ({brand})... ", end="", flush=True)

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.4,
                    max_output_tokens=4000,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),  # disable thinking
                ),
            )
            text = response.text.strip() if response.text else ""

            # Clean
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
            text = text.strip()

            word_count = len(text.split())

            # If too short, mark for Claude retry later
            if word_count < 150:
                existing[pn] = {
                    "description_seo_ru": text,
                    "char_count": len(text),
                    "word_count": word_count,
                    "needs_retry": True,
                    "retry_reason": f"only {word_count} words",
                }
                stats["skipped"] += 1
                print(f"SHORT ({word_count} words) — marked for retry")
            else:
                existing[pn] = {
                    "description_seo_ru": text,
                    "char_count": len(text),
                    "word_count": word_count,
                }
                stats["generated"] += 1
                print(f"OK ({word_count} words)")

        except Exception as e:
            stats["error"] += 1
            print(f"ERROR: {str(e)[:60]}")

        if (idx + 1) % 10 == 0:
            OUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

        # Adaptive sleep based on errors
        if stats.get("error", 0) > 0 and stats["error"] % 5 == 0:
            print("  Rate limit hit — pausing 60s")
            time.sleep(60)
        else:
            time.sleep(7)  # 7 sec to stay under 10 RPM

    OUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nDone:")
    print(f"  Generated: {stats['generated']}")
    print(f"  Skipped:   {stats['skipped']}")
    print(f"  Errors:    {stats['error']}")
    print(f"  Output: {OUT_FILE}")


if __name__ == "__main__":
    main()
