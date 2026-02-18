"""Проверка налоговых ставок в Shopware"""
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

resp = client._request("POST", "/api/search/tax", json={
    "limit": 20,
    "includes": {"tax": ["id"]}
})
taxes = resp.get("data", [])
print("Налоговые ставки в Shopware:")
for t in taxes:
    tax_id = t.get("id")
    if tax_id:
        try:
            full = client._request("GET", f"/api/tax/{tax_id}")
            if isinstance(full, dict) and "data" in full:
                attrs = full["data"].get("attributes", {})
                name = attrs.get("name", "N/A")
                rate = attrs.get("taxRate", 0)
                print(f"  - {name}: {rate}% (ID: {tax_id})")
        except:
            print(f"  - N/A (ID: {tax_id})")

