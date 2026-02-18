from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class CDMProduct:
    product_number: str
    name: str
    description: str
    price_gross: float
    currency_id: str
    tax_id: str
    stock: int
    active: bool


def build_shopware_product_payload(cdm: CDMProduct) -> Dict[str, Any]:
    return {
        "productNumber": cdm.product_number,
        "name": cdm.name,
        "description": cdm.description,
        "active": cdm.active,
        "stock": cdm.stock,
        "taxId": cdm.tax_id,
        "price": [
            {
                "currencyId": cdm.currency_id,
                "gross": cdm.price_gross,
                "net": cdm.price_gross,
                "linked": True,
            }
        ],
    }
