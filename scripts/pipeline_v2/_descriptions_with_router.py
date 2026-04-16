"""Generate descriptions using AI Router (Gemini → Claude fallback).

Uses ai_router.generate_with_fallback which auto-escalates to Claude
when Gemini returns short output (<150 words).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
CANONICAL_FILE = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "canonical_products.json"
OUT_FILE = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "descriptions_seo.json"

from scripts.pipeline_v2.ai_router import generate_with_fallback

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

ОБЯЗАТЕЛЬНАЯ структура (4 параграфа):
1. <p>Вступление — что это за товар, бренд, серия, назначение (60-80 слов)</p>
2. <p><b>Ключевые характеристики:</b></p><ul><li>5-8 пунктов</li></ul>
3. <p><b>Применение:</b> Где и как используется (60-80 слов)</p>
4. <p><b>Преимущества:</b> Почему стоит выбрать (50-70 слов)</p>

Запреты:
- НЕ обрывай на середине предложения
- НЕ пиши меньше 200 слов
- НЕ используй markdown — только HTML <p> <b> <ul> <li>
- НЕ начинай с "Представляем"

Верни ТОЛЬКО HTML, начни с <p>."""


def main():
    canonical = json.loads(CANONICAL_FILE.read_text(encoding="utf-8"))
    existing = json.loads(OUT_FILE.read_text(encoding="utf-8")) if OUT_FILE.exists() else {}

    targets = []
    for p in canonical:
        if p.get("readiness", {}).get("insales") != "READY":
            continue
        pn = p.get("identity", {}).get("pn", "")
        if not pn or pn in existing:
            continue
        targets.append(p)

    print(f"Generating descriptions for {len(targets)} SKUs")
    print("Strategy: Gemini primary → Claude fallback if <150 words")
    print("=" * 80)

    stats = {"gemini_ok": 0, "claude_ok": 0, "short": 0, "failed": 0, "cost_usd": 0.0}

    for idx, p in enumerate(targets):
        identity = p.get("identity", {})
        pn = identity.get("pn", "")
        brand = identity.get("brand", "")

        ev_file = EV_DIR / f"evidence_{pn}.json"
        ds_block = {}
        if ev_file.exists():
            d = json.loads(ev_file.read_text(encoding="utf-8"))
            ds_block = d.get("from_datasheet", {})

        title = ds_block.get("title") or p.get("title_ru", "") or f"{brand} {pn}"
        description = (p.get("best_description_ru", "") or "")[:500]
        specs = ds_block.get("specs", {}) or p.get("specs", {}) or {}
        if isinstance(specs, dict):
            specs_str = "; ".join(f"{k}: {v}" for k, v in list(specs.items())[:15])
        else:
            specs_str = ""

        prompt = PROMPT.format(
            brand=brand or "не указан",
            pn=pn,
            series=ds_block.get("series") or identity.get("series", "") or "не указана",
            title=title,
            description=description or "нет",
            specs=specs_str or "нет",
            ean=ds_block.get("ean", "") or "нет",
            dimensions=ds_block.get("dimensions_mm", "") or "нет",
            weight=ds_block.get("weight_g", "") or "нет",
        )

        print(f"  [{idx+1}/{len(targets)}] {pn:<22} ({brand})... ", end="", flush=True)

        result = generate_with_fallback(
            prompt=prompt,
            min_words=150,  # triggers Claude fallback if Gemini short
            max_tokens=4000,
            temperature=0.4,
            task="description_seo",
        )

        if not result["success"]:
            stats["failed"] += 1
            print(f"FAILED: {result.get('error','')[:50]}")
            continue

        text = result["text"].strip()
        # Clean markdown
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])

        word_count = len(text.split())
        model = result["model"]
        cost = result.get("cost_usd", 0)
        stats["cost_usd"] += cost

        if word_count < 150:
            stats["short"] += 1
            existing[pn] = {
                "description_seo_ru": text,
                "word_count": word_count,
                "char_count": len(text),
                "model": model,
                "needs_manual_review": True,
            }
            print(f"SHORT ({word_count}w, {model})")
        else:
            if "claude" in model:
                stats["claude_ok"] += 1
            else:
                stats["gemini_ok"] += 1
            existing[pn] = {
                "description_seo_ru": text,
                "word_count": word_count,
                "char_count": len(text),
                "model": model,
                "cost_usd": cost,
            }
            print(f"OK ({word_count}w, {model}, ${cost:.5f})")

        if (idx + 1) % 10 == 0:
            OUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    OUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("=" * 80)
    print(f"Gemini OK:  {stats['gemini_ok']}")
    print(f"Claude OK:  {stats['claude_ok']}")
    print(f"Short:      {stats['short']}")
    print(f"Failed:     {stats['failed']}")
    print(f"Total cost: ${stats['cost_usd']:.4f}")


if __name__ == "__main__":
    main()
