#!/usr/bin/env python3
"""
DR Prompt Generator — generates Deep Research prompts for uncovered SKUs.

CRITICAL RULES:
1. Product hints come from seed_name + assembled_title in evidence files.
2. Reference price comes from our_price_raw (Excel) — passed to DR as validation anchor.
3. Never use expected_category — it is known to be systematically wrong.
4. product_type from Excel is TRUSTED and used for hints.

Data field reliability (evidence files):
  TRUSTED: seed_name, our_price_raw, brand, content.product_type, content.site_placement
  DERIVED: assembled_title (simplified, less info than seed_name)
  UNRELIABLE: expected_category (DO NOT USE as product hint)

Usage:
    python scripts/dr_prompt_generator.py [--version v3] [--force]

Outputs to: research_queue/dr_prompts/{version}/
"""

import json
import glob
import os
import sys
from datetime import datetime
from collections import defaultdict

# === CONFIGURATION ===

EVIDENCE_DIR = "downloads/evidence"
OUTPUT_DIR = "research_queue/dr_prompts"
BATCH_SIZES = {
    "chatgpt": 30,
    "gemini": 20,
    "claude": 30,
}

# === PRODUCT FAMILY CLASSIFICATION ===
# Based on assembled_title keywords → English hint for DR prompt

FAMILY_RULES = [
    # PEHA electrical accessories — most critical to get right
    (lambda t: "PEHA AURA" in t and "Рамка" in t, "PEHA AURA frame"),
    (lambda t: "PEHA AURA" in t and "Клавиша" in t, "PEHA AURA rocker switch"),
    (lambda t: "PEHA AURA" in t and "Вставка" in t, "PEHA AURA insert"),
    (lambda t: "PEHA AURA" in t and "Розетка" in t, "PEHA AURA socket"),
    (lambda t: "PEHA NOVA" in t and "Рамка" in t, "PEHA NOVA frame"),
    (lambda t: "PEHA NOVA" in t and "Клавиша" in t, "PEHA NOVA rocker switch"),
    (lambda t: "PEHA NOVA" in t and "Вставка" in t, "PEHA NOVA insert"),
    (lambda t: "PEHA NOVA" in t and "Центральная накладка" in t, "PEHA NOVA center plate"),
    (lambda t: "PEHA DIALOG" in t and "Рамка" in t, "PEHA DIALOG frame"),
    (lambda t: "PEHA DIALOG" in t and "Клавиша" in t, "PEHA DIALOG rocker switch"),
    (lambda t: "PEHA DIALOG" in t and "Вставка" in t, "PEHA DIALOG insert"),
    (lambda t: "PEHA DIALOG" in t and "Розетка" in t, "PEHA DIALOG socket"),
    (lambda t: "PEHA COMPACTA" in t and "Рамка" in t, "PEHA COMPACTA frame"),
    (lambda t: "PEHA" in t and "Кнопка" in t, "PEHA push button"),
    (lambda t: "PEHA" in t, "PEHA electrical accessory"),

    # Esser / fire safety
    (lambda t: "Транспондер" in t, "Esser transponder"),
    (lambda t: "Извещатель" in t, "fire detector"),
    (lambda t: "Усилитель" in t and ("580" in t or "Esser" in t), "Esser PA amplifier"),
    (lambda t: "Громкоговоритель" in t, "PA speaker/horn"),

    # PPE / safety equipment
    (lambda t: "Беруши" in t, "earplugs (PPE)"),
    (lambda t: "Привязь" in t, "safety harness (PPE)"),
    (lambda t: "Наушники" in t, "hearing protection (PPE)"),

    # HVAC / valves / actuators
    (lambda t: "Клапан" in t, "valve"),
    (lambda t: "Привод" in t and "PEHA" not in t, "actuator"),
    (lambda t: "Термостат" in t, "thermostat"),
    (lambda t: "Инвертор" in t, "HVAC inverter"),
    (lambda t: "Мотор" in t, "valve actuator motor"),
    (lambda t: "Мультисенсор" in t, "multisensor"),

    # BMS / Trend / Saia-Burgess
    (lambda t: "FX808" in t, "Trend BMS module"),
    (lambda t: "PCD" in t, "Saia-Burgess PLC module"),

    # Cameras / security
    (lambda t: "Камера" in t, "IP camera"),
    (lambda t: "Монитор" in t, "monitor"),

    # IT / networking
    (lambda t: "Медиаконвертер" in t, "media converter"),
    (lambda t: "Шасси" in t, "rack chassis"),
    (lambda t: "Сетевая карта" in t, "network card"),
    (lambda t: "Оптический кросс" in t, "fiber patch panel"),
    (lambda t: "Свитч" in t, "network switch"),
    (lambda t: "Док-станция" in t, "docking station"),
    (lambda t: "Видеокарта" in t, "graphics card"),

    # Power / electrical
    (lambda t: "Источник питания" in t, "power supply"),
    (lambda t: "Блок питания" in t, "power supply unit"),
    (lambda t: "Трансформатор" in t, "transformer"),
    (lambda t: "Клеммный блок" in t, "terminal block"),
    (lambda t: "Клемма" in t, "terminal"),
    (lambda t: "Предохранитель" in t, "fuse"),

    # Computing / peripherals
    (lambda t: "Принтер" in t, "printer"),
    (lambda t: "Рабочая станция" in t, "workstation"),
    (lambda t: "Плеер" in t, "media player"),
    (lambda t: "Процессорный блок" in t, "CPU module"),

    # Sensors / detectors
    (lambda t: "Датчик" in t, "sensor"),
    (lambda t: "Газоанализатор" in t, "gas detector"),
    (lambda t: "Индикатор" in t, "indicator"),

    # Misc
    (lambda t: "Кабель" in t, "cable"),
    (lambda t: "Пигтейл" in t, "fiber pigtail"),
    (lambda t: "Заглушка" in t, "blank plate"),
    (lambda t: "Зарядное устройство" in t, "charger"),
    (lambda t: "Рукоять" in t, "pistol grip handle"),
    (lambda t: "Коннектор" in t, "connector"),
    (lambda t: "Основание" in t, "detector base"),
    (lambda t: "Монтажный корпус" in t, "mounting box"),
    (lambda t: "Корпус" in t, "enclosure"),
    (lambda t: "Панель" in t, "panel"),
    (lambda t: "Шкаф" in t, "rack cabinet"),
    (lambda t: "Набор" in t, "kit"),
    (lambda t: "Считыватель" in t, "card reader"),
    (lambda t: "Соединение" in t, "connector"),
    (lambda t: "Модуль" in t, "module"),
    (lambda t: "Расширение" in t, "expansion module"),
    (lambda t: "Органайзер" in t, "cable organizer"),
    (lambda t: "Конвертер" in t, "converter"),
    (lambda t: "Адаптер" in t, "adapter"),
    (lambda t: "Канал" in t, "channel module"),
    (lambda t: "Телефон" in t, "IP phone"),
    (lambda t: "Устройство" in t, "device"),
    (lambda t: "База" in t, "charging base"),
]


def detect_real_brand(assembled_title: str, pn: str, main_brand: str = "Honeywell") -> str | None:
    """
    Detect if a SKU's real searchable brand differs from the catalog's main brand.
    Returns the real brand name if found, or None if main_brand is correct.

    Rule: if assembled_title starts with a brand name that is NOT the main brand,
    return that brand. This enables 'subbrand + PN' search in prompts.

    This is GENERIC — works for any catalog, not just Honeywell.
    """
    # Known subbrand/OEM patterns: first word(s) of assembled_title
    KNOWN_SUBBRANDS = [
        "PEHA", "Esser", "Moxa", "Dell", "Phoenix Contact",
        "Allied Telesis", "Eaton", "Redapt", "Axiomtek",
        "Trend", "Saia-Burgess", "Notifier", "Morley",
        "Howard Leight", "Intermec", "Datamax",
    ]
    title_upper = assembled_title.upper()
    for brand in KNOWN_SUBBRANDS:
        if brand.upper() in title_upper:
            return brand
    # Generic: if assembled_title starts with a capitalized word that isn't the main brand
    words = assembled_title.split()
    if words and words[0][0].isupper() and words[0].lower() != main_brand.lower():
        candidate = words[0]
        # Skip common Russian words and product type words
        SKIP = {"Рамка","Клапан","Датчик","Привод","Модуль","Блок","Кабель","Терминал",
                "Монитор","Принтер","Шкаф","Панель","Корпус","Набор","Устройство",
                "Зарядное","Заглушка","Источник","Свитч","Коннектор","Адаптер"}
        if candidate not in SKIP and len(candidate) > 2:
            return candidate
    return None


def classify_product(assembled_title: str, pn: str) -> str:
    """
    Derive English product hint from assembled_title.
    NEVER uses expected_category.
    """
    for rule_fn, hint in FAMILY_RULES:
        if rule_fn(assembled_title):
            return hint
    # Fallback: use the Russian type word from assembled_title
    # assembled_title format: "Тип Brand PN" or "Тип серия Brand, PN"
    first_word = assembled_title.split()[0] if assembled_title else ""
    return f"Honeywell {first_word}" if first_word else "Honeywell device"


def group_by_family(skus: list) -> dict:
    """Group SKUs by product family for smarter batching."""
    families = defaultdict(list)
    for sku in skus:
        hint = sku["hint"]
        # Group into broader families
        if "PEHA" in hint:
            family = "PEHA electrical"
        elif hint in ("earplugs (PPE)", "safety harness (PPE)", "hearing protection (PPE)"):
            family = "PPE safety"
        elif hint in ("valve", "actuator", "thermostat", "HVAC inverter", "valve actuator motor", "multisensor"):
            family = "HVAC/valves"
        elif "Trend BMS" in hint or "Saia-Burgess" in hint:
            family = "BMS controllers"
        elif hint in ("fire detector", "Esser transponder", "Esser PA amplifier", "PA speaker/horn", "detector base"):
            family = "Fire safety/PA"
        elif hint in ("IP camera", "monitor"):
            family = "Security/video"
        elif hint in ("power supply", "power supply unit", "transformer", "terminal block", "terminal", "fuse"):
            family = "Power/electrical"
        else:
            family = "Other"
        families[family].append(sku)
    return dict(families)


def load_uncovered_skus(gap_mode: str = None) -> list:
    """Load evidence files and return SKUs needing DR data.

    Args:
        gap_mode: None = truly uncovered (no DR at all).
                  "no_image" = has DR but missing dr_image_url.
                  "no_price" = has DR but missing dr_price.
                  "no_title" = has DR but missing deep_research.title_ru.
                  "no_desc"  = has DR but missing deep_research.description_ru.
                  "weak"     = any of the above gaps.
    """
    files = glob.glob(os.path.join(EVIDENCE_DIR, "evidence_*.json"))
    uncovered = []

    for f in files:
        basename = os.path.basename(f)
        if "-----" in basename or "---." in basename:
            continue

        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        pn = data.get("pn", "")
        if not pn:
            continue

        # Check actual DR data fields (fixed: was checking wrong keys)
        dr = data.get("deep_research", {})
        has_dr = bool(dr or data.get("dr_price") or data.get("dr_image_url") or data.get("dr_category"))

        if gap_mode is None:
            # Original mode: only truly uncovered SKUs
            if has_dr:
                continue
        else:
            # Gap mode: find SKUs WITH DR but missing specific fields
            if not has_dr:
                continue  # Skip truly uncovered — they need full DR, not gap fill
            has_image = bool(data.get("dr_image_url"))
            has_price = bool(data.get("dr_price"))
            has_title = bool(dr.get("title_ru"))
            has_desc = bool(dr.get("description_ru"))

            if gap_mode == "no_image" and has_image:
                continue
            elif gap_mode == "no_price" and has_price:
                continue
            elif gap_mode == "no_title" and has_title:
                continue
            elif gap_mode == "no_desc" and has_desc:
                continue
            elif gap_mode == "weak" and has_image and has_price and has_title and has_desc:
                continue

        title = data.get("assembled_title", "")
        seed_name = data.get("content", {}).get("seed_name", "") or data.get("name", "")
        our_price_raw = data.get("our_price_raw", "")
        product_type = data.get("content", {}).get("product_type", "")
        subbrand = data.get("subbrand", "")
        pn_variants = data.get("pn_variants", [])
        identity_level = data.get("identity_level", "")
        existing_desc = data.get("content", {}).get("description", "")

        # SAFETY CHECK: Verify we're using assembled_title, not expected_category
        expected_cat = data.get("expected_category", "")
        hint = classify_product(title, pn)
        main_brand = data.get("brand", "Honeywell") or "Honeywell"
        real_brand = detect_real_brand(title, pn, main_brand)

        # Cross-check: warn if hint contradicts title
        if "PEHA" in title and "PEHA" not in hint:
            print(f"  WARNING: {pn} has PEHA in title but hint={hint}", file=sys.stderr)
            hint = "PEHA electrical accessory"  # Force correct

        # Build rich description from seed_name (more descriptive than assembled_title)
        excel_description = seed_name if seed_name != title else ""

        # Format reference price
        ref_price = ""
        if our_price_raw and str(our_price_raw).strip():
            ref_price = str(our_price_raw).replace(",", ".").strip()

        uncovered.append({
            "pn": pn,
            "assembled_title": title,
            "seed_name": seed_name,
            "excel_description": excel_description,
            "ref_price_rub": ref_price,
            "product_type": product_type,
            "subbrand": subbrand,
            "pn_variants": pn_variants,
            "identity_level": identity_level,
            "existing_desc": existing_desc[:100] if existing_desc else "",
            "expected_category_DO_NOT_USE": expected_cat,  # Kept for audit trail only
            "hint": hint,
            "main_brand": main_brand,  # Catalog's primary brand (from evidence 'brand' field)
            "real_brand": real_brand,  # None if main brand is correct search term
        })

    # Sort: weak identity first (need more research), then by hint (groups similar products)
    identity_priority = {"weak": 0, "": 1, "strong": 2}
    uncovered.sort(key=lambda x: (identity_priority.get(x.get("identity_level", ""), 1), x["hint"], x["pn"]))
    return uncovered


def generate_chatgpt_prompt(batch: list, batch_num: int) -> str:
    """Generate ChatGPT Deep Research prompt (Gray Market Analyst role)."""
    rows = []
    for i, sku in enumerate(batch, 1):
        excel_desc = sku.get("excel_description", "") or sku.get("seed_name", "")
        ref_price = sku.get("ref_price_rub", "") or ""
        subbrand = sku.get("subbrand", "")
        hint_col = sku["hint"]
        if subbrand and subbrand.lower() not in hint_col.lower():
            hint_col = f"{hint_col} ({subbrand})"
        variants = sku.get("pn_variants", [])
        alias_note = f" [also: {', '.join(variants[:3])}]" if variants else ""
        rows.append(f"| {i} | {sku['pn']}{alias_note} | {hint_col} | {excel_desc} | {ref_price} |")

    table = "\n".join(rows)
    count = len(batch)

    # Detect product families in this batch for context hints
    families = set(s["hint"] for s in batch)
    has_peha = any("PEHA" in h for h in families)
    has_fire = any(h in ("fire detector", "Esser transponder", "Esser PA amplifier", "PA speaker/horn") for h in families)
    has_valves = any(h in ("valve", "actuator", "thermostat") for h in families)
    has_ppe = any("PPE" in h for h in families)

    search_tips = []
    # Generic subbrand tips — auto-detected from real_brand field
    from collections import defaultdict as _dd2
    brand_to_pns_g = _dd2(list)
    for s in batch:
        rb = s.get("real_brand")
        if rb:
            brand_to_pns_g[rb].append(s["pn"])

    # Derive catalog brand from batch (use most common main_brand, fallback to "Honeywell")
    from collections import Counter as _Counter
    catalog_brand_g = _Counter(s.get("main_brand", "Honeywell") for s in batch).most_common(1)[0][0]
    for rb, pns in brand_to_pns_g.items():
        if rb != catalog_brand_g:
            search_tips.append(f'- {rb}: search "{rb} {{PN}}" — NEVER "{catalog_brand_g} {{PN}}" for these items')

    if has_peha:
        search_tips.append("- PEHA codes with dots (010130.10): suffix .10/.20 is color variant, search without it too")
        search_tips.append("- Unit-price PEHA sources: watt24.com, heiz24.de, alles-mit-stecker.de (avoid Conrad/voelkner — pack prices)")
    if has_fire:
        search_tips.append("- Esser 58xxxx = PA speakers/amplifiers; 80xxxx = IQ8 detectors")
    if has_valves:
        search_tips.append('- V5xxx/ML6xxx Honeywell HVAC: radwell.com, emoteek.net, IndiaMART')
        search_tips.append("- N05xxx/N10xxx/S05xxx/S10xxx: Honeywell valve actuators")
    if has_ppe:
        search_tips.append('- PPE items: Amazon, Grainger, safety equipment suppliers')
    if not search_tips:
        search_tips.append('- Try "{PN}" in quotes on Google, eBay, Radwell, IndiaMART, AliExpress')
        search_tips.append("- Try subbrand + PN if product has a known subbrand")

    tips_text = "\n".join(search_tips)

    return f"""You are a Senior Procurement Intelligence Analyst specializing in Gray Market and Industrial Surplus sourcing for Honeywell ecosystem parts. Your job is to find real, purchasable prices that normal search engines miss.

## Context

These {count} part numbers are from Honeywell sub-brands: Esser (fire safety), PEHA (electrical switches), Morley-IAS (fire detection), Honeywell Building Technologies (HVAC), and others. Many are European market items.

## Key search tricks for these specific parts

{tips_text}

## {count} Part Numbers (with reference data from our database)

| # | PN | Expected Type | Excel Description | Ref Price (RUB) |
|---|-----|--------------|-------------------|-----------------|
{table}

"Excel Description" is our internal product name — use it to identify the product correctly.
"Ref Price (RUB)" is our reference purchase price — use it to validate prices you find.

## What I need back

Two markdown tables:

### Table 1 — Product data (ALL {count} rows)

| # | PN | Price | Currency | Price_Type | Source URL | Category | Image URL | Alias | Specs | Notes |
|---|-----|-------|----------|-----------|-----------|----------|-----------|-------|-------|-------|

- Price: the actual number you found, or "not found"
- Price_Type: distributor / surplus / gray_market / list_price
- Source URL: the actual page where you saw the price (not a search results page)
- Category: short English name like "smoke detector", "PA amplifier", "valve actuator"
- Image URL: direct link to a product photo if you found one
- Alias: if the product is listed under a different part number on any site
- Specs: voltage, dimensions, protocol, anything technical — semicolon separated
- Notes: condition, unit of measure, series name, anything useful

### Table 2 — Every URL you visited (for training our local AI)

| # | PN | URL | Page_Type | Has_Price | Has_Specs | Has_Photo | Domain |
|---|-----|-----|-----------|-----------|-----------|-----------|--------|

Even for "not found" PNs, list the 1-3 URLs you actually checked. This helps us train our automated search crawler to know where to look for each type of product.

Page_Type values: distributor, manufacturer, datasheet_pdf, marketplace, catalog, forum

## Important

- Never invent or guess prices
- Surplus/gray market prices are welcome — just label them
- Any currency is fine (EUR, USD, GBP, RUB, CHF, etc.)
- Photos are high priority
- Every PN must appear in both tables
"""


def generate_gemini_prompt(batch: list, batch_num: int) -> str:
    """Generate Gemini Deep Research prompt (v8-table: SHORT prompt, table-first, no narrative).

    IMPORTANT: Gemini has two modes. Long/rich prompts trigger 'analytics mode' which
    produces narrative without parseable tables. Short prompts trigger 'table mode' which
    gives structured data with prices, URLs, photos. We want TABLE MODE for catalog enrichment.
    Keep this prompt SHORT. Do NOT add Excel descriptions or reference prices here.
    """
    rows = []
    for i, sku in enumerate(batch, 1):
        rows.append(f"| {i} | {sku['pn']} | {sku['hint']} |")

    table = "\n".join(rows)
    count = len(batch)

    # Detect families for context block
    families = set(s["hint"] for s in batch)
    has_peha = any("PEHA" in h for h in families)
    has_fire = any(h in ("fire detector", "Esser transponder", "Esser PA amplifier", "PA speaker/horn") for h in families)
    has_valves = any(h in ("valve", "actuator", "thermostat") for h in families)
    has_ppe = any("PPE" in h for h in families)
    has_bms = any("BMS" in h or "PLC" in h for h in families)

    context_lines = []
    if has_peha:
        context_lines.append("- **PEHA by Honeywell** -- German electrical installation (frames, switches, sockets, inserts). Suffix `.10`=white, `.20`=cream. Search: ebay.de, conrad.de, voelkner.de, electropara.ru")
    if has_fire:
        context_lines.append("- **Esser by Honeywell** -- Fire detection (detectors, transponders, PA speakers). Codes 80xxxx, 58xxxx. Search: brandmelde-shop.de, tinko.ru, fireshield.co.uk")
    if has_valves:
        context_lines.append("- **Honeywell Building Tech** -- HVAC valves (V5xxx), actuators (ML6xxx, N05xxx), thermostats (T7xxx). Search: carrier.com, radwell.com, indiamart.com, prolinkpro.ru")
    if has_bms:
        context_lines.append("- **Trend / Saia-Burgess** -- BMS controllers (FX808xxx), PLCs (PCD2/3/7). Search: trendcontrols.com, saia-burgess.com, distrelec.com")
    if has_ppe:
        context_lines.append("- **Honeywell Safety / Howard Leight** -- PPE: ear plugs, harnesses, gas detectors. Search: grainger.com, amazon.com, rsgroup.com")
    if not context_lines:
        context_lines.append("- Various Honeywell sub-brands. Search: eBay, Radwell, IndiaMART, Conrad.de, specialist suppliers")

    context_text = "\n".join(context_lines)

    return f"""Research {count} industrial part numbers. Fill the table below with real data from the internet.

| # | PN | Product Hint |
|---|-----|-------------|
{table}

## Search instructions

{context_text}

- Google each PN in quotes: `"PN"`
- Then try: `"PN" datasheet`, `"PN" price`
- If nothing found: try without suffix (.10, -RU) or add brand prefix
- Check eBay (ebay.de, ebay.com) for photos and pricing
- Check Russian sources: vseinstrumenti.ru, lemanapro.ru, etm.ru, tinko.ru

## Output: ONE table with ALL {count} rows

| Part Number | Brand | Product Name (Russian) | Description (Russian, 3-5 sentences) | Category | Price | Currency | Price Source URL | Photo URL | Datasheet PDF URL | Key Specs (param: value; param: value) | Certifications | EAN/GTIN |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

Rules:
- Every PN MUST have a row, even if price = "Not found"
- NEVER invent prices. "Not found" is better than a guess
- Description: 3-5 sentences in Russian about what this product is, how it works, where it's used
- Product Name must be in Russian
- Any currency accepted (EUR, USD, RUB, GBP, CHF)
- Surplus/eBay photos are acceptable
- Key Specs SHOULD include: dimensions (mm), weight (kg), IP rating where available
"""


def generate_claude_prompt(batch: list, batch_num: int) -> str:
    """Generate Claude Deep Research prompt (contextual/personal style)."""
    rows = []
    for i, sku in enumerate(batch, 1):
        hint_col = sku["hint"]
        # For PEHA items, seed_name/excel_description from xlsx is unreliable
        # (labels like "Детектор пламени" for frames). Use assembled_title instead.
        if "PEHA" in hint_col:
            excel_desc = sku.get("assembled_title", "") or sku.get("excel_description", "")
        else:
            excel_desc = sku.get("excel_description", "") or sku.get("seed_name", "")
        ref_price = sku.get("ref_price_rub", "") or ""
        subbrand = sku.get("subbrand", "")
        if subbrand and subbrand.lower() not in hint_col.lower():
            hint_col = f"{hint_col} ({subbrand})"
        variants = sku.get("pn_variants", [])
        alias_note = f" [also: {', '.join(variants[:3])}]" if variants else ""
        rows.append(f"| {i} | {sku['pn']}{alias_note} | {hint_col} | {excel_desc} | {ref_price} |")

    table = "\n".join(rows)
    count = len(batch)

    # Detect product families for personalized context
    families = set(s["hint"] for s in batch)
    has_peha = any("PEHA" in h for h in families)
    has_fire = any(h in ("fire detector", "Esser transponder", "Esser PA amplifier", "PA speaker/horn") for h in families)
    has_valves = any(h in ("valve", "actuator") for h in families)

    family_context = []
    # Generic subbrand detection — works for ANY catalog
    # Group SKUs by their real_brand to generate per-brand search instructions
    from collections import defaultdict as _dd
    brand_to_pns = _dd(list)
    for s in batch:
        rb = s.get("real_brand")
        if rb:
            brand_to_pns[rb].append(s["pn"])

    # Derive catalog brand from batch (use most common main_brand, fallback to "Honeywell")
    from collections import Counter as _Counter2
    catalog_brand = _Counter2(s.get("main_brand", "Honeywell") for s in batch).most_common(1)[0][0]

    if brand_to_pns:
        for rb, pns in brand_to_pns.items():
            example_pn = pns[0]
            family_context.append(
                f'Items with brand **{rb}**: search as "{rb} {{PN}}" (e.g. "{rb} {example_pn}"). '
                f'**Do NOT search "{catalog_brand} {{PN}}" for these — they are indexed under {rb}, not {catalog_brand}.**'
            )

    if has_peha:
        # Extra PEHA-specific search sites
        family_context.append('**PEHA** search sites: ebay.de, conrad.de, voelkner.de, watt24.com, pehastore.de, heiz24.de, elektroversand.de. Single-unit price sources: watt24.com, heiz24.de, alles-mit-stecker.de (avoid Conrad/voelkner pack prices >200 EUR).')
    if has_fire:
        family_context.append('**Esser** search sites: brandmelde-shop.de, tinko.ru, fireshield.co.uk, walde.ee.')
    if has_valves:
        family_context.append('**Honeywell HVAC** valves/actuators: emoteek.net, automa.net, radwell.com, indiamart.com.')
    if not family_context:
        family_context.append(f"These are from various {catalog_brand} sub-brands. Search on eBay, Radwell, IndiaMART, AliExpress, Conrad.de, specialist suppliers.")

    context_text = "\n".join(f"- {c}" for c in family_context)

    return f"""I need you to research market prices for {count} industrial part numbers from the {catalog_brand} ecosystem. These are components used in building automation, fire safety, HVAC, and electrical installations.

## Who I am and why this matters

I'm building a product catalog for an industrial parts reseller. I need real-world prices from any source — official distributors, eBay surplus, gray market dealers, anything. Even a "refurbished for $50" finding is valuable. I also need photos, technical specs, and alternative part numbers (aliases) to build our database.

## About these specific parts

{context_text}

## Key search tricks

- Codes ending in .10/.20 are color variants — search without the suffix too
- Suffix -RU means Russian market version — try without it
- Suffix -L3 means kit/set — try without it
- Many codes have aliases under different sub-brand names
- Try: "{{PN}}" in quotes, sub-brand + PN, PN without leading zeros

## {count} Part Numbers (with reference data from our database)

| # | PN | Expected Type | Excel Description | Ref Price (RUB) |
|---|-----|--------------|-------------------|-----------------|
{table}

"Excel Description" is our internal product name — use it to identify the product correctly.
"Ref Price (RUB)" is our reference purchase price — use it to validate prices you find.

## What I need back

Two markdown tables:

### Table 1 — Product data (ALL {count} rows)

| # | PN | Price | Currency | Price_Type | Source URL | Category | Image URL | Alias | Specs | Notes |
|---|-----|-------|----------|-----------|-----------|----------|-----------|-------|-------|-------|

- Price: the actual number you found, or "not found"
- Price_Type: distributor / surplus / gray_market / list_price
- Source URL: the actual page where you saw the price (not a search results page)
- Category: short English name like "smoke detector", "PA amplifier", "PEHA frame"
- Image URL: direct link to a product photo if you found one
- Alias: if the product is listed under a different part number on any site
- Specs: voltage, dimensions, protocol, anything technical — semicolon separated
- Notes: condition, unit of measure, series name, anything useful

### Table 2 — Every URL you visited (for training our local AI)

| # | PN | URL | Page_Type | Has_Price | Has_Specs | Has_Photo | Domain |
|---|-----|-----|-----------|-----------|-----------|-----------|--------|

Even for "not found" PNs, list the 1-3 URLs you actually checked. This helps us train our automated search crawler.

Page_Type values: distributor, manufacturer, datasheet_pdf, marketplace, catalog, forum

## Important

- Never invent or guess prices
- Surplus/gray market prices are welcome — just label them
- Any currency is fine (EUR, USD, GBP, RUB, CHF, etc.)
- Photos are high priority
- Every PN must appear in both tables
"""


def make_batches(skus: list, batch_size: int) -> list:
    """Split SKU list into batches, trying to keep product families together."""
    # Group by family first
    families = group_by_family(skus)

    # Flatten back in family order
    ordered = []
    for family_name in sorted(families.keys()):
        ordered.extend(families[family_name])

    # Split into batches
    batches = []
    for i in range(0, len(ordered), batch_size):
        batches.append(ordered[i:i + batch_size])
    return batches


def verify_hints(skus: list) -> list:
    """
    SAFETY: Verify that no PEHA product is labeled as a sensor/detector/valve.
    Returns list of warnings.
    """
    warnings = []
    for sku in skus:
        title = sku["assembled_title"]
        hint = sku["hint"]

        # PEHA items must have PEHA in hint
        if "PEHA" in title and "PEHA" not in hint:
            warnings.append(f"PEHA MISLABEL: {sku['pn']} title='{title}' hint='{hint}'")

        # Fire-related hints should not appear for PEHA items
        if "PEHA" in title and any(w in hint.lower() for w in ("sensor", "detector", "fire", "esser")):
            warnings.append(f"PEHA AS FIRE: {sku['pn']} title='{title}' hint='{hint}'")

    return warnings


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate DR prompts from evidence files")
    parser.add_argument("--version", default="v3", help="Prompt version (default: v3)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing prompts")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be generated")
    parser.add_argument("--gaps", choices=["no_image", "no_price", "no_title", "no_desc", "weak"],
                        default=None, help="Target specific quality gaps instead of uncovered SKUs")
    args = parser.parse_args()

    gap_label = f" (gap: {args.gaps})" if args.gaps else ""
    print(f"Loading SKUs from {EVIDENCE_DIR}{gap_label}...")
    skus = load_uncovered_skus(gap_mode=args.gaps)
    print(f"Found {len(skus)} SKUs needing DR{gap_label}")

    if not skus:
        print("No uncovered SKUs found. Nothing to generate.")
        return

    # SAFETY: Verify all hints
    warnings = verify_hints(skus)
    if warnings:
        print("\n=== HINT VERIFICATION WARNINGS ===", file=sys.stderr)
        for w in warnings:
            print(f"  {w}", file=sys.stderr)
        if not args.force:
            print("\nAborting. Fix warnings or use --force.", file=sys.stderr)
            sys.exit(1)

    # Show family breakdown
    families = group_by_family(skus)
    print("\nProduct family breakdown:")
    for family, members in sorted(families.items()):
        print(f"  {family}: {len(members)} SKUs")

    # Generate for each platform
    output_dir = os.path.join(OUTPUT_DIR, args.version)
    os.makedirs(output_dir, exist_ok=True)

    for platform, generator in [
        ("chatgpt", generate_chatgpt_prompt),
        ("gemini", generate_gemini_prompt),
        ("claude", generate_claude_prompt),
    ]:
        batch_size = BATCH_SIZES[platform]
        batches = make_batches(skus, batch_size)
        print(f"\n{platform.upper()}: {len(batches)} batches of {batch_size}")

        for i, batch in enumerate(batches, 1):
            filename = f"{platform}_batch{i}_{len(batch)}skus.txt"
            filepath = os.path.join(output_dir, filename)

            if os.path.exists(filepath) and not args.force:
                print(f"  SKIP {filename} (exists, use --force)")
                continue

            prompt = generator(batch, i)

            if args.dry_run:
                print(f"  WOULD WRITE {filename} ({len(batch)} SKUs, {len(prompt)} chars)")
                # Show first 3 hints for verification
                for sku in batch[:3]:
                    print(f"    {sku['pn']}: {sku['hint']}  (from: {sku['assembled_title'][:50]})")
                if len(batch) > 3:
                    print(f"    ... and {len(batch) - 3} more")
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(prompt)
                print(f"  WROTE {filename} ({len(batch)} SKUs)")

    # Write generation manifest
    manifest = {
        "generated_at": datetime.now().isoformat(),
        "version": args.version,
        "total_uncovered": len(skus),
        "source_fields": [
            "assembled_title (product hint derivation)",
            "seed_name (Excel description — passed to DR as context)",
            "our_price_raw (Excel reference price — passed to DR as validation anchor)",
            "brand",
            "NEVER expected_category",
        ],
        "families": {k: len(v) for k, v in families.items()},
        "batches": {},
    }
    for platform in ("chatgpt", "gemini", "claude"):
        batch_size = BATCH_SIZES[platform]
        batches = make_batches(skus, batch_size)
        manifest["batches"][platform] = {
            "count": len(batches),
            "batch_size": batch_size,
            "files": [f"{platform}_batch{i+1}_{len(b)}skus.txt" for i, b in enumerate(batches)],
        }

    manifest_path = os.path.join(output_dir, "generation_manifest.json")
    if not args.dry_run:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        print(f"\nManifest written to {manifest_path}")

    print(f"\nDone. {len(skus)} SKUs across {sum(len(make_batches(skus, BATCH_SIZES[p])) for p in BATCH_SIZES)} total batches.")
    print("VERIFICATION: All hints derived from assembled_title. expected_category was NOT used.")


if __name__ == "__main__":
    main()
