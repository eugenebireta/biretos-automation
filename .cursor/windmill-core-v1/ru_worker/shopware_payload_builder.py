from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


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
    media_ids: Optional[List[str]] = None
    attributes: Optional[Dict[str, Any]] = None


def build_shopware_product_payload(cdm: CDMProduct) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
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
    if cdm.attributes:
        payload["customFields"] = dict(cdm.attributes)

    if cdm.media_ids:
        payload["media"] = [
            {"mediaId": media_id, "position": idx + 1}
            for idx, media_id in enumerate(cdm.media_ids)
        ]
        payload["coverId"] = cdm.media_ids[0]

    return payload
