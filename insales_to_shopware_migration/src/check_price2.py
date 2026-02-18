"""Проверка price2 в snapshot"""
import json
from pathlib import Path

snapshot = Path(__file__).resolve().parent.parent / "insales_snapshot" / "products.ndjson"

test_skus = ["500944170", "500944171", "500944177", "500944178", "500944203", 
             "500944207", "500944219", "500944220", "500944221", "500944222"]

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
                if sku in test_skus:
                    price = variants[0].get("price")
                    price2 = variants[0].get("price2")
                    print(f"SKU: {sku}, price: {price}, price2: {price2}")
        except:
            pass



