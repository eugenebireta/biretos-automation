"""Тест поиска налоговой ставки Standard rate"""
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

# Тест 1: Поиск через filter
print("Тест 1: Поиск через filter с type='equals':")
resp1 = client._request("POST", "/api/search/tax", json={
    "filter": [{"field": "name", "type": "equals", "value": "Standard rate"}],
    "limit": 1,
    "includes": {"tax": ["id", "name", "taxRate"]},
})
print(f"  total: {resp1.get('total')}")
print(f"  data: {resp1.get('data')}")

# Тест 2: Поиск через filter с type='contains'
print("\nТест 2: Поиск через filter с type='contains':")
resp2 = client._request("POST", "/api/search/tax", json={
    "filter": [{"field": "name", "type": "contains", "value": "Standard"}],
    "limit": 10,
    "includes": {"tax": ["id", "name", "taxRate"]},
})
print(f"  total: {resp2.get('total')}")
if resp2.get("data"):
    for t in resp2.get("data", []):
        print(f"    - {t.get('name')}: {t.get('taxRate')}% (ID: {t.get('id')})")


