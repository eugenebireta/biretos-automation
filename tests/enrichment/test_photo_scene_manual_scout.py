from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import photo_scene_manual_scout as scout  # noqa: E402


def test_output_path_for_record_uses_canonical_photos_for_product_assets(tmp_path, monkeypatch):
    monkeypatch.setattr(scout, "PRODUCT_PHOTOS_DIR", tmp_path / "photos")
    monkeypatch.setattr(scout, "SCOUT_ASSET_DIR", tmp_path / "scout_assets")

    product_path = scout.output_path_for_record("033588.17", "product_photo")
    scene_path = scout.output_path_for_record("033588.17", "scene_placeholder")

    assert product_path == (tmp_path / "photos" / "033588.17.jpg")
    assert scene_path == (tmp_path / "scout_assets" / "033588.17__scene.jpg")


def test_materialize_seed_record_preserves_existing_canonical_photo(tmp_path, monkeypatch):
    photos_dir = tmp_path / "photos"
    scout_dir = tmp_path / "scout_assets"
    photos_dir.mkdir(parents=True)
    scout_dir.mkdir(parents=True)
    canonical_path = photos_dir / "033588.17.jpg"
    canonical_path.write_bytes(b"existing")

    monkeypatch.setattr(scout, "PRODUCT_PHOTOS_DIR", photos_dir)
    monkeypatch.setattr(scout, "SCOUT_ASSET_DIR", scout_dir)
    monkeypatch.setattr(scout, "parse_product_page", lambda *_args, **_kwargs: {"image_url": "https://example.com/bad.jpg"})
    monkeypatch.setattr(scout, "get_source_trust", lambda *_args, **_kwargs: {"tier": "authorized", "weight": 0.9, "domain": "example.com"})
    monkeypatch.setattr(scout, "get_source_role", lambda *_args, **_kwargs: "authorized_distributor")
    monkeypatch.setattr(scout, "is_denied", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(scout, "get_size", lambda *_args, **_kwargs: (640, 480))
    monkeypatch.setattr(scout, "compute_sha1", lambda *_args, **_kwargs: "sha1")

    def _download_should_not_run(*_args, **_kwargs):
        raise AssertionError("existing canonical photo should be preserved without downloading")

    monkeypatch.setattr(scout, "download_image", _download_should_not_run)

    result = scout.materialize_seed_record(
        {
            "part_number": "033588.17",
            "brand": "Honeywell",
            "product_name": "Ball-and-socket joint",
            "asset_kind": "product_photo",
            "page_url": "https://example.com/product",
            "asset_url": "",
            "source_provider": "codex_manual",
            "notes": "preserve existing canonical",
        }
    )

    assert result["download_ok"] is True
    assert result["used_existing_canonical"] is True
    assert result["selection_reason"] == "existing_canonical_preserved"
    assert result["local_path"] == str(canonical_path)
    assert result["storage_role"] == "canonical_raw_photo"
