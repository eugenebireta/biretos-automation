"""Временный скрипт для поиска товаров с полными данными"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from clients import ShopwareClient, ShopwareConfig
from import_utils import ROOT

config = json.load(open(ROOT / "config.json", encoding="utf-8"))
client = ShopwareClient(ShopwareConfig(
    config["shopware"]["url"],
    config["shopware"]["access_key_id"],
    config["shopware"]["secret_access_key"]
))

resp = client._request("POST", "/api/search/product", json={
    "limit": 20,
    "includes": {"product": ["id"]}
})
products = resp.get("data", [])
print("Поиск товаров с productNumber:")
for p in products:
    pid = p.get("id")
    if pid:
        try:
            full = client._request("GET", f"/api/product/{pid}")
            data = full.get("data", {})
            attrs = data.get("attributes", {})
            pn = attrs.get("productNumber") or data.get("productNumber")
            if pn:
                print(f"  SKU: {pn}, ID: {pid}")
        except:
            pass

