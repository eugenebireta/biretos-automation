#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
from pathlib import Path
from clients import ShopwareClient, ShopwareConfig

config_path = Path(__file__).parent.parent / "config.json"
with config_path.open(encoding="utf-8") as f:
    config = json.load(f)

sw = config["shopware"]
client = ShopwareClient(ShopwareConfig(sw["url"], sw["access_key_id"], sw["secret_access_key"]))

product_id = "019b1958a54b726c81a9d01ab4652826"
cover_id = "fc164f4bb8154c5493ee7cbaefa82a69"

r = client._request("GET", f"/api/product/{product_id}/media")
data = r.get("data", [])

print(f"Всего записей в product_media: {len(data)}")

found = []
for pm in data:
    pm_attrs = pm.get("attributes", {})
    media_id = pm_attrs.get("mediaId") or pm.get("mediaId")
    if media_id == cover_id:
        found.append(pm)

print(f"Записей с coverId ({cover_id}): {len(found)}")

if found:
    print("\nНайденные записи:")
    for f in found[:3]:
        pm_attrs = f.get("attributes", {})
        print(f"  Product-Media ID: {f.get('id')}")
        print(f"    Position: {pm_attrs.get('position')}")
        print(f"    IsCover: {pm_attrs.get('isCover')}")
else:
    print("\n[КРИТИЧЕСКАЯ ПРОБЛЕМА] Нет записи в product_media с coverId!")
    print("  Это означает, что coverId установлен, но связь product_media отсутствует.")




