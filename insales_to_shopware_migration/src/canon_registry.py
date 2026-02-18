from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from clients import ShopwareClient, ShopwareClientError
from import_utils import ROOT, load_json, save_json


LOG = logging.getLogger(__name__)
CANON_MAP_PATH = ROOT / "canon_map.json"


class CanonRegistryError(RuntimeError):
    """Р‘СЂРѕСЃР°РµС‚СЃСЏ РїСЂРё РЅРµРІРѕР·РјРѕР¶РЅРѕСЃС‚Рё СЂР°Р·СЂРµС€РёС‚СЊ РєР°РЅРѕРЅРёС‡РµСЃРєРёР№ РёРґРµРЅС‚РёС„РёРєР°С‚РѕСЂ."""


class CanonRegistry:
    """Р•РґРёРЅС‹Р№ СЂРµРµСЃС‚СЂ РєР°РЅРѕРЅРёС‡РµСЃРєРёС… РїСЂРѕРёР·РІРѕРґРёС‚РµР»РµР№ Рё РїСЂР°РІРёР»."""

    def __init__(self, client: ShopwareClient, path: Optional[Path] = None) -> None:
        self._client = client
        self._path = path or CANON_MAP_PATH
        self._data = self._load()

    def get_canonical_manufacturer_id(self, name: str) -> str:
        normalized = self._normalize(name)
        if not normalized:
            raise CanonRegistryError("Manufacturer name cannot be empty")

        cached_id = self._data["manufacturers"].get(normalized)
        if cached_id and self._entity_exists("product-manufacturer", cached_id):
            return cached_id

        resolved_id = self._resolve_manufacturer_id(name)
        if not resolved_id:
            raise CanonRegistryError(f"Unable to resolve manufacturer '{name}'")

        self._set_manufacturer(normalized, resolved_id, original_name=name)
        return resolved_id

    def get_canonical_rule_id(self, name: str) -> str:
        normalized = self._normalize(name)
        if not normalized:
            raise CanonRegistryError("Rule name cannot be empty")

        cached_id = self._data["rules"].get(normalized)
        if cached_id and self._entity_exists("rule", cached_id):
            return cached_id

        resolved_id = self._resolve_rule_id(name)
        if not resolved_id:
            raise CanonRegistryError(f"Unable to resolve rule '{name}'")

        self._set_rule(normalized, resolved_id, original_name=name)
        return resolved_id

    def ensure_marketplace_rule(self) -> str:
        return self.get_canonical_rule_id("Marketplace Price")

    def set_canonical_manufacturer(self, name: str, manufacturer_id: str) -> None:
        normalized = self._normalize(name)
        if not normalized or not manufacturer_id:
            raise CanonRegistryError("Both name and manufacturer_id are required")
        self._set_manufacturer(normalized, manufacturer_id, original_name=name)

    def set_canonical_rule(self, name: str, rule_id: str) -> None:
        normalized = self._normalize(name)
        if not normalized or not rule_id:
            raise CanonRegistryError("Both name and rule_id are required")
        self._set_rule(normalized, rule_id, original_name=name)

    def _load(self) -> Dict[str, Dict[str, str]]:
        default_payload = {
            "manufacturers": {},
            "rules": {},
            "metadata": {"version": "1.0", "last_updated": None},
        }

        if not self._path.exists():
            save_json(self._path, default_payload)
            return default_payload

        payload = load_json(self._path, default=default_payload)
        payload.setdefault("manufacturers", {})
        payload.setdefault("rules", {})
        payload.setdefault("metadata", {"version": "1.0", "last_updated": None})
        return payload

    def _save(self) -> None:
        self._data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        save_json(self._path, self._data)

    def _normalize(self, name: str) -> str:
        if not name:
            return ""
        return " ".join(name.strip().split()).casefold()

    def _entity_exists(self, entity: str, entity_id: str) -> bool:
        try:
            self._client._request("GET", f"/api/{entity}/{entity_id}")
            return True
        except ShopwareClientError:
            return False
        except Exception:
            return False

    def _resolve_manufacturer_id(self, name: str) -> Optional[str]:
        existing_id = self._client.find_manufacturer_by_name_normalized(name)
        if existing_id:
            return existing_id
        try:
            return self._client.create_manufacturer_if_missing(name)
        except Exception as exc:
            LOG.error("[CanonRegistry] Failed to create manufacturer '%s': %s", name, exc)
            return None

    def _resolve_rule_id(self, name: str) -> Optional[str]:
        existing_id = self._client.find_rule_by_name_normalized(name)
        if existing_id:
            return existing_id
        try:
            return self._client.create_rule_if_missing(name)
        except Exception as exc:
            LOG.error("[CanonRegistry] Failed to create rule '%s': %s", name, exc)
            return None

    def _set_manufacturer(self, normalized: str, manufacturer_id: str, *, original_name: str) -> None:
        if self._data["manufacturers"].get(normalized) == manufacturer_id:
            return
        LOG.info("[CanonRegistry] Update manufacturer mapping '%s' -> %s", original_name, manufacturer_id)
        self._data["manufacturers"][normalized] = manufacturer_id
        self._save()

    def _set_rule(self, normalized: str, rule_id: str, *, original_name: str) -> None:
        if self._data["rules"].get(normalized) == rule_id:
            return
        LOG.info("[CanonRegistry] Update rule mapping '%s' -> %s", original_name, rule_id)
        self._data["rules"][normalized] = rule_id
        self._save()
