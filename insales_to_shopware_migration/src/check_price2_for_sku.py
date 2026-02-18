"""Проверка price2 для конкретного SKU"""
import json
from pathlib import Path

snapshot = Path(__file__).resolve().parent.parent / "insales_snapshot" / "products.ndjson"

sku_to_check = "500944238"

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
                if sku == sku_to_check:
                    price = variants[0].get("price")
                    price2 = variants[0].get("price2")
                    print(f"SKU: {sku}")
                    print(f"price: {price}")
                    print(f"price2: {price2}")
                    print(f"price2 is not None: {price2 is not None}")
                    print(f"price2 > 0: {price2 is not None and float(price2) > 0 if price2 is not None else False}")
                    break
        except:
            pass

