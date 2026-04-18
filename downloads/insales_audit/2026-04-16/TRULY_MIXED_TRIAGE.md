# Triage Report: 4 SKUs classified `truly_mixed_prices`

**Status**: NOT migrated to Shopware bundles (excluded from auto-migration).
**Reason**: "Цена продажи" varies per variant in a non-systematic way AND mp_price in marketplace column has irregular pattern.

Owner decision Q4: "ручной разбор" — manual review of each before migration.

---

## 1. pid `285896849` — Дополнительный шильдик ABB OMFB72

**Issue**: lot=10 has price=1231р (other lots: 69-121р). mp_price jumps from 836р (lot=5) to **21177р (lot=10)** — **opposite direction of bulk discount**. Almost certainly a data-entry typo.

```
lot=1  stock=59  price=121р   mp=455.7   per-unit mp: 455
lot=2  stock=1   price=69р    mp=484.6   per-unit mp: 242
lot=3  stock=1   price=69р    mp=601.9   per-unit mp: 201
lot=4  stock=1   price=69р    mp=719.2   per-unit mp: 180
lot=5  stock=1   price=69р    mp=836.5   per-unit mp: 167
lot=10 stock=1   price=1231р  mp=21177р  per-unit mp: 2118  ← typo
```

**Recommended migration**:
- Base: lot=1 with **price=121р** (or rebuild from 69р × 1.75 + 250 = 370р formula?)
- Bundles: apply formula `mp = 121 × 1.75 × lot_size + 250` for lots 2/3/4/5/10
- Drop the anomalous lot=10 price, use formula
- Note: owner needs to confirm which variant is the "reference price" (lot=1 121р OR lot=2-5 69р)

**Total stock (interpretation A)**: 59×1 + 1×2 + 1×3 + 1×4 + 1×5 + 1×10 = **83 pieces**

---

## 2. pid `287626395` — Клемма винтовая Weidmuller ZPE 2.5

**Issue**: lot=1 price=140р, lots 2-5 all 340р (suspicious — maybe 340 is per-pack-of-something), lot=10 price=840р. mp_price pattern also irregular: 488, 1406, 1984, 2562, 3140, **14530** (lot=10, huge jump).

```
lot=1  stock=3  price=140р  mp=488    per-unit mp: 488
lot=2  stock=1  price=340р  mp=1406   per-unit mp: 703   ← double per-unit
lot=3  stock=1  price=340р  mp=1984   per-unit mp: 661
lot=4  stock=0  price=340р  mp=2562   per-unit mp: 641
lot=5  stock=0  price=340р  mp=3140   per-unit mp: 628
lot=10 stock=0  price=840р  mp=14530р per-unit mp: 1453  ← typo
```

**Recommended migration**:
- Base: lot=1 with price=140р
- Bundles: formula `mp = 140 × 1.75 × lot_size + 250`
- Owner needs to confirm 340р for lot=2-5 is valid or also typo

**Total stock**: 3×1 + 1×2 + 1×3 = **8 pieces**

---

## 3. pid `446790857` — Лампа накаливания МН6.3 Е10/13

**Issue**: Only 2 variants. lot=1 price=200р, lot=3 price=500р (not 600 = 3×200).

```
lot=1 stock=4 price=200р  mp=590    per-unit mp: 590
lot=3 stock=0 price=500р  mp=2800   per-unit mp: 933  ← inverse (per-unit grew)
```

**Recommended migration**:
- Base: lot=1 with price=200р
- Bundle: lot=3 with formula `mp = 200 × 1.75 × 3 + 250 = 1300р` (not 2800р — that's inverted)

**Total stock**: 4×1 = **4 pieces**

---

## 4. pid `466262515` — Лампа накаливания рудничная Тэлз Р 3,75

**Issue**: This one is ALMOST uniform — lot=1 price=40р, lots 2-100 all 50р. mp_price actually follows a clean bulk-discount curve (per-unit: 318 → 88 → 87 as lot grows). This SKU could have been migrated automatically if the classifier had been less strict.

```
lot=1   stock=499  price=40р  mp=318    per-unit mp: 318  ← base reference
lot=2   stock=0    price=50р  mp=420    per-unit mp: 210
lot=3   stock=0    price=50р  mp=505    per-unit mp: 168
lot=4   stock=0    price=50р  mp=590    per-unit mp: 148
lot=5   stock=0    price=50р  mp=675    per-unit mp: 135
lot=10  stock=0    price=50р  mp=1100   per-unit mp: 110
lot=30  stock=9    price=50р  mp=2800   per-unit mp: 93
lot=100 stock=9    price=50р  mp=8750   per-unit mp: 87  ← healthy bulk discount
```

**Recommended migration**:
- Base: lot=1 with **price=40р** (owner's reference price from lot=1)
- Bundles: formula `mp = 40 × 1.75 × lot_size + 250` for lots 2,3,4,5,10,30,100
- Total stock: 499×1 + 9×30 + 9×100 = **1,669 pieces** (high-volume item)

**This is the one most worth migrating** — 499 pieces of lot=1 stock, and the pricing curve is already correct. Just need to override Цена inconsistency.

---

## Summary

| pid | name | total_pieces | action |
|---|---|---:|---|
| 285896849 | ABB OMFB72 | 83 | manual: fix lot=10 typo, migrate |
| 287626395 | Weidmuller ZPE 2.5 | 8 | manual: confirm 340р is valid, migrate |
| 446790857 | Лампа МН6.3 | 4 | manual: fix lot=3 inversion, migrate |
| **466262515** | **Лампа Тэлз Р 3,75** | **1669** | **READY** — migrate with lot=1 40р base |

**Recommendation for owner**:
1. Fix Цена продажи inconsistencies in InSales for the 4 SKUs (5 minutes in admin)
2. Re-run `insales_lot_audit.py` — after the fixes, they'll classify as `uniform_price_lots × linear_discount`
3. Add them to next migration batch via `--pids`

OR (faster): I write a custom `shopware_bundle_manual_triage.py` that takes per-pid override for "base reference price" and migrates these 4 with the corrections above. Say the word.
