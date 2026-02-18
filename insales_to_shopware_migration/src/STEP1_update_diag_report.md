# Диагностика UPDATE товара и доступности InSales CDN

**Product Number:** 500944170
**Дата:** 2025-12-14 13:03:59

## InSales CDN доступность

| URL | HTTP Status | Content-Type | Content-Length | Is Image | ROOT CAUSE |
|-----|-------------|--------------|----------------|----------|------------|
| `https://static.insales-cdn.com/images/products/1/2431/570182...` | 200 | image/jpeg | 297356 | True | OK |
| `https://static.insales-cdn.com/images/products/1/2434/570182...` | 200 | image/jpeg | 248659 | True | OK |
| `https://static.insales-cdn.com/images/products/1/2438/570182...` | 200 | image/jpeg | 392362 | True | OK |

## InSales API доступность

- **Status:** 426
- **API-Usage-Limit:** 2/500

## Shopware after UPDATE

- **product_id:** `019b19e7d49172e392428aca4acb7fc2`
- **product_number:** `None`
- **media_count:** 5
- **cover_id:** `None`
- **internal_barcode:** `None`

## Финальный вывод

**ROOT CAUSE:** coverId не установлен (проблема в коде импорта).
