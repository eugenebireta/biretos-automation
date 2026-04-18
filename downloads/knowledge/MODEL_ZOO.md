# Local Model Zoo — Biretos Automation

**Updated:** 2026-04-18
**Hardware:** 2× RTX 3090 (24GB each)
**Base encoder:** `intfloat/multilingual-e5-large` (1024-dim)
**Fine-tuned encoder:** `encoder_biretos_v1` (contrastive on ~18k B2B pairs, 95% val recall@1)

## Encoder routing (production default: v1 / base)

Per retrain comparison (2026-04-18) on shop_data holdout:

| Task | v1 (base) | v2 (biretos) | Δ val | OOD finding |
|---|---|---|---|---|
| ozon_classifier | 96.3% | 99.7% | +3.4% | v2 degrades OOD — use v1 |
| type_classifier | 95.8% | 100.0% | +4.2% | v2 degrades OOD — use v1 |
| brand_classifier | 98.9% | 91.9% | -7.0% | v1 |
| country_classifier | 91.8% | 79.7% | -12.2% | v1 |

**Key OOD finding (2026-04-18, measured on 370 B2B niche SKUs):**
- v1↔v2 top-1 agreement only **14%** (ozon) / **9%** (type)
- v2 top-1 confidence dropped: ozon 0.65→0.54, type 0.62→0.44
- SKUs above 0.70 threshold: ozon 160→108 (-33%), type 139→37 (-73%)
- Fine-tuned encoder overfit shop_data semantic space → loses discriminative signal on niche B2B (thermostats, relays, valves)

`scripts.local_inference` defaults to **v1 for all tasks** on OOD production catalogs.
Use `predict_ozon_v2()` / `predict_type_v2()` explicitly for shop_data-adjacent inputs.

## Classifiers (40)

| Model | Classes | Train | Val | Accuracy | Encoder |
|---|---|---|---|---|---|
| `type_classifier_v2` | 69 | 2963 | 330 | **100.0%** | biretos |
| `attr_brand_v1` | 5 | 329 | 37 | **100.0%** | base |
| `attr_Комплектация_v1` | 3 | 597 | 67 | **100.0%** | base |
| `attr_Мощность_Вт_v1` | 8 | 362 | 41 | **100.0%** | base |
| `attr_Название_цвета_v1` | 3 | 59 | 7 | **100.0%** | base |
| `attr_Напряжение_питания_В_v1` | 9 | 311 | 35 | **100.0%** | base |
| `attr_Сила_света_мкд_v1` | 3 | 105 | 12 | **100.0%** | base |
| `attr_Сила_тока_mA_v1` | 4 | 129 | 15 | **100.0%** | base |
| `attr_Тип_цоколя_v1` | 7 | 426 | 48 | **100.0%** | base |
| `ozon_classifier_v2` | 63 | 2653 | 295 | **99.7%** | biretos |
| `attr_GoodsSubType_v1` | 5 | 2619 | 291 | **99.7%** | base |
| `attr_ElectricsType_v1` | 5 | 1202 | 134 | **99.3%** | base |
| `attr_ElectricsSubType_v1` | 9 | 1107 | 124 | **99.2%** | base |
| `brand_classifier_v1` | 43 | 3399 | 378 | **98.9%** | base |
| `attr_GoodsType_v1` | 9 | 2851 | 317 | **98.4%** | base |
| `attr_Единиц_в_одном_товаре_v1` | 5 | 3690 | 411 | **98.3%** | base |
| `attr_category_v1` | 5 | 2903 | 323 | **98.1%** | base |
| `attr_Свет_v1` | 3 | 462 | 52 | **98.1%** | base |
| `attr_Гарантия_v1` | 4 | 3620 | 403 | **97.0%** | base |
| `attr_Коммерческий_тип_v1` | 5 | 624 | 70 | **95.7%** | base |
| `attr_ТН_ВЭД_коды_ЕАЭС_v1` | 26 | 2461 | 274 | **95.3%** | base |
| `attr_Коробка_v1` | 3 | 4152 | 462 | **94.6%** | base |
| `attr_type_v1` | 69 | 2963 | 330 | **93.6%** | base |
| `attr_color_v1` | 9 | 821 | 92 | **93.5%** | base |
| `color_classifier_v1` | 9 | 821 | 92 | **93.5%** | base |
| `category_classifier_v2` | 88 | 927 | 103 | **92.2%** | base |
| `country_classifier_v1` | 13 | 3526 | 392 | **91.8%** | base |
| `attr_material_v1` | 4 | 211 | 24 | **91.7%** | base |
| `attr_DeviceType_v1` | 3 | 157 | 18 | **88.9%** | base |
| `attr_country_v1` | 13 | 3365 | 374 | **86.4%** | base |
| `category_classifier` | 88 | ? | ? | **85.3%** | base |
| `reranker_v1` | ? | ? | ? | **80.0%** | base |
| `attr_Номинальное_напряжение_В_v1` | 4 | 158 | 18 | **77.8%** | base |
| `attr_Количество_полюсов_v1` | 3 | 117 | 13 | **76.9%** | base |
| `attr_Количество_клавиш_v1` | 3 | 101 | 12 | **75.0%** | base |
| `attr_Сертификаты_v1` | 5 | 818 | 91 | **69.2%** | base |
| `attr_Poles_v1` | 3 | 85 | 10 | **60.0%** | base |
| `attr_Количество_модулей_v1` | 3 | 91 | 11 | **45.5%** | base |

Deprecated (kept for reference): `ozon_classifier_v1` (96.3%, base), `type_classifier_v1` (95.8%, base), `brand_classifier_v2` (91.9%, biretos — v1 wins), `country_classifier_v2` (79.7%, biretos — v1 wins).

## Retrieval indexes (2)

| Name | Items | Embeddings size |
|---|---|---|
| `title` | 5959 | 23.3 MB |
| `description` | 3928 | 15.3 MB |

Retrieval uses base encoder (not biretos) — generic similarity is more robust on open-domain queries.

## Marketplace schema coverage

| Source | Count | Path |
|---|---|---|
| Ozon description categories × types | 119 mapped | `downloads/marketplace_schemas/ozon/attributes/` |
| Ozon dict enum values | 1780 dicts / ~204k values | `downloads/marketplace_schemas/ozon/dict_values/` |
| WB subjects (full tree) | 8009 | `downloads/marketplace_schemas/wb/subject_base_flat.json` |
| WB characteristics (per subject) | 7957 / 8009 (99.4%) | `downloads/marketplace_schemas/wb/characteristics/` |

52 WB subjects returned errors (likely deprecated or permission-gated).

## Usage

```python
from scripts.local_inference import (
    predict_brand, predict_ozon, predict_type,
    predict_country, predict_color, predict_insales_category,
    retrieve_title, retrieve_description,
    hybrid_ozon_predict,
)

predict_brand('Honeywell D 20.672 датчик температуры')   # → [('Honeywell', 0.99)]  base encoder
predict_ozon('Рамка 2-местная PEHA NOVA 00020211', k=3)  # biretos encoder
predict_type('Клапан регулирующий Honeywell V5011R1000') # biretos encoder
retrieve_title('датчик температуры промышленный', k=5)   # base encoder
```

## Cost / break-even

- Base encoder load-once (1.1 GB VRAM), heads are 500 KB–4 MB each.
- Haiku API: ~$0.003-0.005 per SKU per classification task.
- Local inference: ~0 ms after warm load, $0.
- Break-even vs Haiku-per-SKU: reached at ~100 SKUs processed.

## Hybrid safety pattern

For Ozon mapping with high confidence + Haiku agreement:
```python
result = hybrid_ozon_predict(text, haiku_prediction=haiku_label, confidence_threshold=0.7)
# {"accept": True/False, "local_top1": ..., "local_conf": ...}
```
Veto gate: disagreement with Haiku → SKIP (per AI-Audit 2026-04-17 `ozon-sibling-fallback`).
