import json
import os
import sys
from pathlib import Path

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from naming_resolver import load_scout_cache, resolve_naming, resolve_title_or_fallback


class TestNamingResolver:
    def test_loads_scout_cache_jsonl(self, tmp_path: Path):
        cache_path = tmp_path / "naming_scout_cache.jsonl"
        cache_path.write_text(
            json.dumps(
                {
                    "part_number": "189791",
                    "brand_hint": "PEHA",
                    "scouted_at": "2026-03-31T12:00:00Z",
                    "scout_provider": "codex_manual",
                    "facts": {
                        "brand": "PEHA",
                        "series": "NOVA",
                        "product_type": "frame",
                        "gang_count": 3,
                        "color": None,
                        "source_url": "https://example.com/189791",
                    },
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        cache = load_scout_cache(cache_path)
        assert cache["189791"]["facts"]["series"] == "NOVA"
        assert cache["189791"]["facts"]["gang_count"] == 3

    def test_empty_cache_keeps_existing_resolution(self, tmp_path: Path):
        cache_path = tmp_path / "missing_cache.jsonl"
        decision = resolve_naming(
            part_number="189791",
            raw_title="D 20.673.244.192",
            brand="PEHA",
            cache_path=cache_path,
        )
        assert decision["title_ru"] == "Рамка 3-постовая PEHA NOVA, 189791"
        assert decision["review_required"] is False

    def test_resolves_peha_nova_three_gang_frame(self):
        decision = resolve_naming(
            part_number="189791",
            raw_title="D 20.673.244.192",
            brand="PEHA",
        )
        assert decision["matched_family"] == "peha_nova"
        assert decision["series"] == "NOVA"
        assert decision["canonical_product_type"] == "frame"
        assert decision["attributes"]["gang_count"] == 3
        assert decision["title_ru"] == "Рамка 3-постовая PEHA NOVA, 189791"
        assert decision["review_required"] is False

    def test_resolves_peha_aura_frame_from_specs(self):
        decision = resolve_naming(
            part_number="101411",
            raw_title="D 20.572.51.70",
            brand="PEHA",
            specs={
                "Тип товара:": "Рамка 2 поста",
                "Количество постов:": "2",
                "Цвет:": "Серебристый",
                "Материал:": "Закаленное стекло",
                "Ориентация:": "Горизонтальная/вертикальная",
                "Коллекция:": "AURA GLAS",
            },
        )
        assert decision["matched_family"] == "peha_aura"
        assert decision["series"] == "AURA"
        assert decision["canonical_product_type"] == "frame"
        assert str(decision["attributes"]["gang_count"]) == "2"
        assert decision["title_ru"] == "Рамка 2-постовая PEHA AURA, 101411"
        assert decision["review_required"] is False

    def test_resolves_peha_dialog_socket(self):
        decision = resolve_naming(
            part_number="820611",
            raw_title="D 95.6511.02 SI",
            brand="PEHA",
        )
        assert decision["matched_family"] == "peha_dialog"
        assert decision["series"] == "DIALOG"
        assert decision["canonical_product_type"] == "socket"
        assert decision["title_ru"] == "Розетка PEHA DIALOG, 820611"
        assert decision["review_required"] is False

    def test_resolves_generic_peha_switch(self):
        decision = resolve_naming(
            part_number="190511",
            raw_title="D 515",
            brand="PEHA",
        )
        assert decision["matched_family"] == "peha_generic"
        assert decision["canonical_product_type"] == "switch"
        assert decision["title_ru"] == "Выключатель PEHA, 190511"
        assert decision["review_required"] is False

    def test_resolves_compacta_frame(self):
        decision = resolve_naming(
            part_number="603111",
            raw_title="D 771.02",
            brand="PEHA",
        )
        assert decision["matched_family"] == "peha_compacta"
        assert decision["series"] == "COMPACTA"
        assert decision["canonical_product_type"] == "frame"
        assert decision["attributes"]["gang_count"] == 1
        assert decision["title_ru"] == "Рамка 1-постовая PEHA COMPACTA, 603111"
        assert decision["review_required"] is False

    def test_cache_overrides_pattern_inferred_values(self, tmp_path: Path):
        cache_path = tmp_path / "naming_scout_cache.jsonl"
        cache_path.write_text(
            json.dumps(
                {
                    "part_number": "189791",
                    "brand_hint": "PEHA",
                    "scouted_at": "2026-03-31T12:00:00Z",
                    "scout_provider": "codex_manual",
                    "facts": {
                        "brand": "PEHA",
                        "series": "NOVA",
                        "product_type": "frame",
                        "gang_count": 4,
                        "color": None,
                        "source_url": "https://example.com/189791",
                    },
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        decision = resolve_naming(
            part_number="189791",
            raw_title="D 20.673.244.192",
            brand="PEHA",
            cache_path=cache_path,
        )
        assert decision["attributes"]["gang_count"] == 4
        assert decision["title_ru"] == "Рамка 4-постовая PEHA NOVA, 189791"

    def test_fallback_passthrough_for_non_peha(self):
        title, decision = resolve_title_or_fallback(
            part_number="802371",
            raw_title="Smoke detector",
            brand="Esser",
            fallback_title="Дымовой извещатель Esser 802371",
        )
        assert title == "Дымовой извещатель Esser 802371"
        assert decision["review_required"] is True
