"""Проверка price2 для импортированных товаров"""
import json
from pathlib import Path

snapshot = Path(__file__).resolve().parent.parent / "insales_snapshot" / "products.ndjson"
skus = ["500944238", "500944237", "500944236", "500944235", "500944234", "500944233", "500944232", "500944226", "500944225", "500944223"]

with snapshot.open("r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            product = json.loads(line)
            variants = product.get("variants", [])
            if variants:
                sku = str(variants[0].get("sku", ""))
                if sku in skus:
                    price = variants[0].get("price")
                    price2 = variants[0].get("price2")
                    print(f"SKU: {sku}, price: {price}, price2: {price2}")
        except:
            pass

