# Отчет: Диагностика доступности InSales CDN и API

**Дата:** 1765714248.6601787

**Товар:** SKU=500944170

## Проверка изображений

### Изображение 1

- **URL:** https://static.insales-cdn.com/images/products/1/2431/570182015/521677569__7_.jpg
- **HEAD Status:** 200
- **HEAD Content-Type:** image/jpeg
- **GET Status:** 200
- **GET Content-Type:** image/jpeg
- **GET Content-Length:** 297356
- **First 16 bytes (hex):** ffd8ffe000104a464946000101010048
- **Verdict:** IMAGE

### Изображение 2

- **URL:** https://static.insales-cdn.com/images/products/1/2434/570182018/521677569__6_.jpg
- **HEAD Status:** 200
- **HEAD Content-Type:** image/jpeg
- **GET Status:** 200
- **GET Content-Type:** image/jpeg
- **GET Content-Length:** 248659
- **First 16 bytes (hex):** ffd8ffe000104a464946000101010048
- **Verdict:** IMAGE

### Изображение 3

- **URL:** https://static.insales-cdn.com/images/products/1/2438/570182022/521677569__4_.jpg
- **HEAD Status:** 200
- **HEAD Content-Type:** image/jpeg
- **GET Status:** 200
- **GET Content-Type:** image/jpeg
- **GET Content-Length:** 392362
- **First 16 bytes (hex):** ffd8ffe000104a464946000101010048
- **Verdict:** IMAGE

## Проверка InSales API

- **Shop Domain:** myshop-bsu266.myinsales.ru
- **API Status:** 426
- **API-Usage-Limit:** 1/500

## Вывод

**Фотографии доступны на CDN, проблема в коде импорта**
