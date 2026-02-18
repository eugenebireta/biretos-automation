"""Создание Price Rule для Marketplace"""
import json
from pathlib import Path
from clients import ShopwareClient, ShopwareConfig

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

with CONFIG_PATH.open() as f:
    config = json.load(f)

client = ShopwareClient(
    ShopwareConfig(
        config["shopware"]["url"],
        config["shopware"]["access_key_id"],
        config["shopware"]["secret_access_key"]
    )
)

# Ищем существующее правило
rule_id = client.find_price_rule_by_name("Marketplace Price")
if rule_id:
    print(f"Price Rule уже существует: {rule_id}")
else:
    # Создаем новое правило
    rule_id = client.create_price_rule(
        name="Marketplace Price",
        description="Price rule for Marketplace channel (from InSales price2)",
        priority=100
    )
    print(f"Price Rule создан: {rule_id}")



