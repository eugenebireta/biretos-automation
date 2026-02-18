from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from canon_registry import CanonRegistry
from clients import ShopwareClient, ShopwareConfig
from import_utils import ROOT, load_json

REPORTS_DIR = ROOT / "_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = ROOT / "config.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_text(path: Path, lines: List[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handler:
        json.dump(payload, handler, ensure_ascii=False, indent=2)


@dataclass
class GroupStats:
    normalized: str
    display_name: str
    winner_id: str
    winner_usage: int
    loser_ids: List[str]
    products_rebound: int = 0
    prices_rebound: int = 0
    deleted_entities: List[str] = None
    errors: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "normalized": self.normalized,
            "display_name": self.display_name,
            "winner_id": self.winner_id,
            "winner_usage": self.winner_usage,
            "loser_ids": self.loser_ids,
            "products_rebound": self.products_rebound,
            "prices_rebound": self.prices_rebound,
            "deleted_entities": self.deleted_entities or [],
            "errors": self.errors or [],
        }


class EntityNormalizer:
    def __init__(self, client: ShopwareClient, registry: CanonRegistry, dry_run: bool) -> None:
        self.client = client
        self.registry = registry
        self.dry_run = dry_run

    def normalize_manufacturers(self, limit: Optional[int] = None) -> Dict[str, Any]:
        manufacturers = self._fetch_paginated(
            endpoint="/api/search/product-manufacturer",
            include_fields=["id", "name", "createdAt"],
        )
        groups = self._group_by_normalized_name(manufacturers)
        duplicates = [g for g in groups if len(g["items"]) > 1]
        duplicates.sort(key=lambda g: (-len(g["items"]), g["normalized"]))
        if limit is not None:
            duplicates = duplicates[: limit]

        stats: List[GroupStats] = []
        total_rebound = 0
        total_deleted = 0

        for group in duplicates:
            group_stats = self._process_manufacturer_group(group)
            stats.append(group_stats)
            total_rebound += group_stats.products_rebound
            total_deleted += len(group_stats.deleted_entities or [])

        return {
            "dry_run": self.dry_run,
            "groups_total": len(groups),
            "groups_with_duplicates": len(duplicates),
            "products_rebound": total_rebound,
            "entities_deleted": total_deleted,
            "details": [item.to_dict() for item in stats],
        }

    def normalize_rules(
        self,
        limit: Optional[int] = None,
        rule_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        rules = self._fetch_paginated(
            endpoint="/api/search/rule",
            include_fields=["id", "name", "createdAt"],
        )
        groups = self._group_by_normalized_name(rules, target_name=rule_name)
        duplicates = [g for g in groups if len(g["items"]) > 1]
        duplicates.sort(key=lambda g: (-len(g["items"]), g["normalized"]))
        if limit is not None:
            duplicates = duplicates[: limit]

        stats: List[GroupStats] = []
        total_rebound = 0
        total_deleted = 0

        for group in duplicates:
            group_stats = self._process_rule_group(group)
            stats.append(group_stats)
            total_rebound += group_stats.prices_rebound
            total_deleted += len(group_stats.deleted_entities or [])

        return {
            "dry_run": self.dry_run,
            "groups_total": len(groups),
            "groups_with_duplicates": len(duplicates),
            "prices_rebound": total_rebound,
            "entities_deleted": total_deleted,
            "details": [item.to_dict() for item in stats],
        }

    def _process_manufacturer_group(self, group: Dict[str, Any]) -> GroupStats:
        entries = group["items"]
        display_name = group["display_name"]
        normalized = group["normalized"]

        for entry in entries:
            entry["usage"] = self._count_products_by_manufacturer(entry["id"])

        entries.sort(key=lambda e: (-e["usage"], e.get("createdAt") or ""))
        winner = entries[0]
        losers = entries[1:]

        stats = GroupStats(
            normalized=normalized,
            display_name=display_name,
            winner_id=winner["id"],
            winner_usage=winner["usage"],
            loser_ids=[entry["id"] for entry in losers],
            deleted_entities=[],
            errors=[],
        )

        for loser in losers:
            rebound_ids = self._collect_product_ids_by_manufacturer(loser["id"])
            stats.products_rebound += len(rebound_ids)
            if not self.dry_run:
                for product_id in rebound_ids:
                    try:
                        self.client._request("PATCH", f"/api/product/{product_id}", json={"manufacturerId": winner["id"]})
                    except Exception as exc:
                        stats.errors.append(f"РћС€РёР±РєР° РїРµСЂРµРїСЂРёРІСЏР·РєРё {product_id}: {exc}")

            if not self.dry_run:
                remaining = self._count_products_by_manufacturer(loser["id"])
                if remaining == 0:
                    try:
                        self.client._request("DELETE", f"/api/product-manufacturer/{loser['id']}")
                        stats.deleted_entities.append(loser["id"])
                    except Exception as exc:
                        stats.errors.append(f"РћС€РёР±РєР° СѓРґР°Р»РµРЅРёСЏ manufacturer {loser['id']}: {exc}")
            else:
                stats.deleted_entities.append(loser["id"])

        if not self.dry_run:
            self.registry.set_canonical_manufacturer(display_name or normalized, winner["id"])

        return stats

    def _process_rule_group(self, group: Dict[str, Any]) -> GroupStats:
        entries = group["items"]
        display_name = group["display_name"]
        normalized = group["normalized"]

        for entry in entries:
            entry["usage"] = self._count_prices_by_rule(entry["id"])

        entries.sort(key=lambda e: (-e["usage"], e.get("createdAt") or ""))
        winner = entries[0]
        losers = entries[1:]

        stats = GroupStats(
            normalized=normalized,
            display_name=display_name,
            winner_id=winner["id"],
            winner_usage=winner["usage"],
            loser_ids=[entry["id"] for entry in losers],
            deleted_entities=[],
            errors=[],
        )

        for loser in losers:
            prices = self._fetch_product_prices_by_rule(loser["id"])
            stats.prices_rebound += len(prices)

            for price in prices:
                price_id = price.get("id")
                product_id = price.get("productId")
                quantity_start = price.get("quantityStart") or 1
                price_data = price.get("price")
                if not product_id or not price_data:
                    continue

                if self.dry_run:
                    continue

                try:
                    if price_id:
                        try:
                            self.client._request("DELETE", f"/api/product-price/{price_id}")
                        except Exception:
                            pass
                    payload = {
                        "productId": product_id,
                        "ruleId": winner["id"],
                        "quantityStart": quantity_start,
                        "price": price_data,
                    }
                    self.client._request("POST", "/api/product-price", json=payload)
                except Exception as exc:
                    stats.errors.append(f"РћС€РёР±РєР° РїРµСЂРµРїСЂРёРІСЏР·РєРё price {price_id or 'N/A'}: {exc}")

            if not self.dry_run:
                remaining = self._count_prices_by_rule(loser["id"])
                if remaining == 0:
                    try:
                        self.client._request("DELETE", f"/api/rule/{loser['id']}")
                        stats.deleted_entities.append(loser["id"])
                    except Exception as exc:
                        stats.errors.append(f"РћС€РёР±РєР° СѓРґР°Р»РµРЅРёСЏ rule {loser['id']}: {exc}")
            else:
                stats.deleted_entities.append(loser["id"])

        if not self.dry_run:
            self.registry.set_canonical_rule(display_name or normalized, winner["id"])

        return stats

    def _fetch_paginated(self, *, endpoint: str, include_fields: List[str]) -> List[Dict[str, Any]]:
        limit = 500
        page = 1
        items: List[Dict[str, Any]] = []
        include_key = endpoint.split("/")[-1].replace("-", "_")

        while True:
            payload = {
                "limit": limit,
                "page": page,
                "includes": {include_key: include_fields},
            }
            response = self.client._request("POST", endpoint, json=payload)
            data = response.get("data", []) if isinstance(response, dict) else []
            if not data:
                break
            for entry in data:
                attributes = entry.get("attributes", {})
                items.append(
                    {
                        "id": entry.get("id"),
                        "name": attributes.get("name") or entry.get("name", ""),
                        "createdAt": attributes.get("createdAt") or entry.get("createdAt"),
                    }
                )
            if len(data) < limit:
                break
            page += 1
        return items

    def _group_by_normalized_name(
        self,
        items: List[Dict[str, Any]],
        *,
        target_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        groups: Dict[str, Dict[str, Any]] = {}
        target_norm = self._normalize(target_name) if target_name else None

        for item in items:
            name = item.get("name") or ""
            normalized = self._normalize(name)
            if not normalized:
                continue
            if target_norm and normalized != target_norm:
                continue
            groups.setdefault(
                normalized,
                {"normalized": normalized, "display_name": name or normalized, "items": []},
            )
            groups[normalized]["items"].append(item)

        return list(groups.values())

    def _collect_product_ids_by_manufacturer(self, manufacturer_id: str) -> List[str]:
        ids: List[str] = []
        limit = 500
        page = 1
        while True:
            payload = {
                "filter": [{"field": "manufacturerId", "type": "equals", "value": manufacturer_id}],
                "limit": limit,
                "page": page,
                "includes": {"product": ["id"]},
            }
            response = self.client._request("POST", "/api/search/product", json=payload)
            data = response.get("data", []) if isinstance(response, dict) else []
            if not data:
                break
            for entry in data:
                pid = entry.get("id")
                if pid:
                    ids.append(pid)
            if len(data) < limit:
                break
            page += 1
        return ids

    def _fetch_product_prices_by_rule(self, rule_id: str) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        limit = 500
        page = 1
        while True:
            payload = {
                "filter": [{"field": "ruleId", "type": "equals", "value": rule_id}],
                "limit": limit,
                "page": page,
                "includes": {"product_price": ["id", "productId", "ruleId", "quantityStart", "price"]},
            }
            response = self.client._request("POST", "/api/search/product-price", json=payload)
            data = response.get("data", []) if isinstance(response, dict) else []
            if not data:
                break
            for entry in data:
                attributes = entry.get("attributes", {})
                entries.append(
                    {
                        "id": entry.get("id"),
                        "productId": attributes.get("productId") or entry.get("productId"),
                        "ruleId": attributes.get("ruleId") or entry.get("ruleId"),
                        "quantityStart": attributes.get("quantityStart") or entry.get("quantityStart"),
                        "price": attributes.get("price") or entry.get("price"),
                    }
                )
            if len(data) < limit:
                break
            page += 1
        return entries

    def _count_products_by_manufacturer(self, manufacturer_id: str) -> int:
        payload = {
            "filter": [{"field": "manufacturerId", "type": "equals", "value": manufacturer_id}],
            "limit": 1,
            "totalCountMode": 1,
        }
        try:
            response = self.client._request("POST", "/api/search/product", json=payload)
            return int(response.get("total") or 0)
        except Exception:
            return 0

    def _count_prices_by_rule(self, rule_id: str) -> int:
        payload = {
            "filter": [{"field": "ruleId", "type": "equals", "value": rule_id}],
            "limit": 1,
            "totalCountMode": 1,
        }
        try:
            response = self.client._request("POST", "/api/search/product-price", json=payload)
            return int(response.get("total") or 0)
        except Exception:
            return 0

    def _normalize(self, value: Optional[str]) -> str:
        if not value:
            return ""
        return " ".join(value.strip().split()).casefold()


def build_report_lines(title: str, stats: Dict[str, Any]) -> List[str]:
    lines = [
        f"# {title}",
        f"- Timestamp: {_now_iso()}",
        f"- Dry run: {'yes' if stats.get('dry_run') else 'no'}",
        f"- Groups total: {stats.get('groups_total', 0)}",
        f"- Groups with duplicates: {stats.get('groups_with_duplicates', 0)}",
        "",
        "| Normalized Name | Winner ID | Winner usage | Losers | Rebind count | Deleted | Errors |",
        "|-----------------|-----------|--------------|--------|--------------|---------|--------|",
    ]
    for detail in stats.get("details", []):
        lines.append(
            "| {name} | {winner} | {usage} | {losers} | {rebind} | {deleted} | {errors} |".format(
                name=detail["normalized"],
                winner=detail["winner_id"],
                usage=detail["winner_usage"],
                losers=len(detail["loser_ids"]),
                rebind=detail.get("products_rebound") or detail.get("prices_rebound") or 0,
                deleted=len(detail["deleted_entities"]),
                errors=len(detail["errors"]),
            )
        )
    if len(lines) == 8:
        lines.append("| (no duplicates) | - | - | - | - | - | - |")
    return lines


def write_reports(man_stats: Optional[Dict[str, Any]], rule_stats: Optional[Dict[str, Any]]) -> None:
    timestamp = _now_iso()
    summary_payload = {"timestamp": timestamp, "manufacturers": man_stats or {}, "rules": rule_stats or {}}
    _write_json(REPORTS_DIR / "normalize_entities_summary.json", summary_payload)

    summary_lines = ["# Normalize Entities Summary", f"- Timestamp: {timestamp}"]
    if man_stats:
        summary_lines.append(
            f"- Manufacturers: duplicates={man_stats.get('groups_with_duplicates', 0)}, "
            f"rebound={man_stats.get('products_rebound', 0)}, "
            f"deleted={man_stats.get('entities_deleted', 0)}"
        )
    if rule_stats:
        summary_lines.append(
            f"- Rules: duplicates={rule_stats.get('groups_with_duplicates', 0)}, "
            f"rebound={rule_stats.get('prices_rebound', 0)}, "
            f"deleted={rule_stats.get('entities_deleted', 0)}"
        )
    _write_text(REPORTS_DIR / "normalize_entities_summary.md", summary_lines)

    if man_stats is not None:
        _write_json(REPORTS_DIR / "normalize_entities_manufacturers.json", man_stats)
        _write_text(REPORTS_DIR / "normalize_entities_manufacturers.md", build_report_lines("Manufacturers normalization", man_stats))
    if rule_stats is not None:
        _write_json(REPORTS_DIR / "normalize_entities_rules.json", rule_stats)
        _write_text(REPORTS_DIR / "normalize_entities_rules.md", build_report_lines("Rules normalization", rule_stats))


def parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Р“Р»РѕР±Р°Р»СЊРЅР°СЏ РґРµРґСѓРїР»РёРєР°С†РёСЏ manufacturers Рё rules")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--dry-run", action="store_true", help="РџСЂРёРЅСѓРґРёС‚РµР»СЊРЅС‹Р№ dry-run (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ РІРєР»СЋС‡РµРЅ)")
    parser.add_argument("--apply", action="store_true", help="РџСЂРёРјРµРЅРёС‚СЊ РёР·РјРµРЅРµРЅРёСЏ")
    parser.add_argument("--only", choices=["manufacturers", "rules", "all"], default="all")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--rule-name", type=str, default=None)
    return parser.parse_args()


def load_client(config_path: str) -> ShopwareClient:
    config_data = load_json(Path(config_path))
    shopware_cfg = config_data["shopware"]
    return ShopwareClient(
        ShopwareConfig(
            url=shopware_cfg["url"],
            access_key_id=shopware_cfg["access_key_id"],
            secret_access_key=shopware_cfg["secret_access_key"],
        )
    )


def main() -> None:
    args = parse_cli_args()
    dry_run = True
    if args.apply:
        dry_run = False
    elif args.dry_run:
        dry_run = True

    client = load_client(args.config)
    registry = CanonRegistry(client)
    normalizer = EntityNormalizer(client, registry, dry_run)

    man_stats = None
    rule_stats = None

    if args.only in ("manufacturers", "all"):
        man_stats = normalizer.normalize_manufacturers(limit=args.limit)
    if args.only in ("rules", "all"):
        rule_stats = normalizer.normalize_rules(limit=args.limit, rule_name=args.rule_name)

    write_reports(man_stats, rule_stats)

    print("=== Normalize Entities ===")
    if man_stats:
        print(
            f"Manufacturers :: duplicates={man_stats['groups_with_duplicates']} "
            f"rebound={man_stats.get('products_rebound', 0)} deleted={man_stats.get('entities_deleted', 0)} "
            f"dry_run={man_stats['dry_run']}"
        )
    if rule_stats:
        print(
            f"Rules :: duplicates={rule_stats['groups_with_duplicates']} "
            f"rebound={rule_stats.get('prices_rebound', 0)} deleted={rule_stats.get('entities_deleted', 0)} "
            f"dry_run={rule_stats['dry_run']}"
        )


if __name__ == "__main__":
    main()
