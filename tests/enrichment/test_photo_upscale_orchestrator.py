"""tests/enrichment/test_photo_upscale_orchestrator.py — Upscale orchestrator unit tests.

Tests preparation logic, command construction, GPU assignment, fail-fast behavior.
No real upscale runs (binary may not be installed).
"""
import sys
import os
import json
from pathlib import Path
from unittest.mock import patch

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from photo_upscale_orchestrator import (
    check_engine,
    build_upscale_command,
    process_one_sku,
    run_batch,
    update_triage_state,
    ENGINE_EXE,
    MODEL_DIR,
    MODEL_NAME,
    REQUIRED_MODEL_FILES,
    TOOLS_DIR,
)


# ══════════════════════════════════════════════════════════════════════════════
# A. Engine detection
# ══════════════════════════════════════════════════════════════════════════════

class TestEngineDetection:

    def test_engine_check_reports_missing_binary(self):
        """When binary doesn't exist, check_engine returns problems."""
        ok, problems = check_engine()
        # On CI / dev without binary, this should fail
        if not ENGINE_EXE.exists():
            assert ok is False
            assert any("Binary not found" in p for p in problems)

    def test_engine_check_reports_missing_models(self):
        ok, problems = check_engine()
        for mf in REQUIRED_MODEL_FILES:
            if not mf.exists():
                assert any(str(mf) in p for p in problems)

    def test_engine_paths_are_correct(self):
        """Verify expected path structure."""
        assert TOOLS_DIR.name == "realesrgan-ncnn-vulkan"
        assert ENGINE_EXE.name == "realesrgan-ncnn-vulkan.exe"
        assert MODEL_DIR == TOOLS_DIR / "models"
        assert MODEL_NAME == "realesrnet-x4plus"


# ══════════════════════════════════════════════════════════════════════════════
# B. Command construction
# ══════════════════════════════════════════════════════════════════════════════

class TestCommandConstruction:

    def test_basic_command(self):
        cmd = build_upscale_command(
            Path("C:/photos/test.jpg"),
            Path("C:/upscaled/test_x4.png"),
            gpu_id=0,
        )
        assert cmd[0] == str(ENGINE_EXE)
        assert "-i" in cmd
        assert cmd[cmd.index("-i") + 1] == "C:\\photos\\test.jpg"
        assert "-o" in cmd
        assert cmd[cmd.index("-o") + 1] == "C:\\upscaled\\test_x4.png"
        assert "-s" in cmd
        assert cmd[cmd.index("-s") + 1] == "4"
        assert "-n" in cmd
        assert cmd[cmd.index("-n") + 1] == "realesrnet-x4plus"
        assert "-g" in cmd
        assert cmd[cmd.index("-g") + 1] == "0"
        assert "-f" in cmd
        assert cmd[cmd.index("-f") + 1] == "png"

    def test_gpu_1_command(self):
        cmd = build_upscale_command(
            Path("C:/photos/test.jpg"),
            Path("C:/upscaled/test_x4.png"),
            gpu_id=1,
        )
        assert cmd[cmd.index("-g") + 1] == "1"

    def test_model_is_deterministic(self):
        """Must use realesrnet-x4plus, NOT realesrgan (generative)."""
        cmd = build_upscale_command(Path("in.jpg"), Path("out.png"), 0)
        model_idx = cmd.index("-n") + 1
        assert cmd[model_idx] == "realesrnet-x4plus"
        assert "realesrgan" not in cmd[model_idx]  # not the GAN variant


# ══════════════════════════════════════════════════════════════════════════════
# C. GPU assignment
# ══════════════════════════════════════════════════════════════════════════════

class TestGpuAssignment:

    def test_round_robin_two_gpus(self):
        """5 SKUs across 2 GPUs: 0,1,0,1,0."""
        skus = [{"part_number": f"PN{i}", "raw_photo_path": f"C:/photos/PN{i}.jpg", "min_dimension": 300}
                for i in range(5)]
        gpu_ids = [0, 1]

        # Dry-run to check GPU assignment without binary
        results = run_batch(skus, gpu_ids, dry_run=True)
        assert len(results) == 5
        assert results[0]["gpu_id"] == 0
        assert results[1]["gpu_id"] == 1
        assert results[2]["gpu_id"] == 0
        assert results[3]["gpu_id"] == 1
        assert results[4]["gpu_id"] == 0

    def test_single_gpu(self):
        skus = [{"part_number": f"PN{i}", "raw_photo_path": f"C:/photos/PN{i}.jpg", "min_dimension": 300}
                for i in range(3)]
        results = run_batch(skus, [0], dry_run=True)
        for r in results:
            assert r["gpu_id"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# D. Fail-loud behavior
# ══════════════════════════════════════════════════════════════════════════════

class TestFailLoud:

    def test_source_missing_outcome(self):
        """SKU with nonexistent raw file → source_missing."""
        sku = {
            "part_number": "GHOST001",
            "raw_photo_path": "C:/nonexistent/ghost.jpg",
            "min_dimension": 300,
        }
        result = process_one_sku(sku, gpu_id=0, dry_run=False)
        assert result["outcome"] == "source_missing"
        assert "not found" in result["error"]

    def test_dry_run_does_not_execute(self):
        """Dry-run should not attempt subprocess."""
        sku = {
            "part_number": "DRY001",
            "raw_photo_path": "C:/photos/DRY001.jpg",
            "min_dimension": 300,
        }
        result = process_one_sku(sku, gpu_id=0, dry_run=True)
        assert result["outcome"] == "dry_run_skipped"
        assert "DRY RUN" in result["error"]
        assert "realesrgan-ncnn-vulkan" in result["error"]


# ══════════════════════════════════════════════════════════════════════════════
# E. State update logic
# ══════════════════════════════════════════════════════════════════════════════

class TestStateUpdate:

    def test_promoted_sku_moves_to_good(self, tmp_path):
        """Successful SKU should move from needs_upscale to good_quality."""
        needs = [
            {"part_number": "OK001", "raw_photo_path": "C:/photos/OK001.jpg",
             "raw_width": 300, "raw_height": 400, "min_dimension": 300,
             "bucket": "needs_upscale"},
            {"part_number": "FAIL001", "raw_photo_path": "C:/photos/FAIL001.jpg",
             "raw_width": 250, "raw_height": 350, "min_dimension": 250,
             "bucket": "needs_upscale"},
        ]
        good = [
            {"part_number": "EXISTING001", "bucket": "good_quality"},
        ]

        results = [
            {"part_number": "OK001", "outcome": "upscale_success_promoted",
             "raw_path": "C:/photos/OK001.jpg", "upscaled_width": 1200,
             "upscaled_height": 1600, "enhanced_path": "C:/enhanced/OK001.jpg"},
            {"part_number": "FAIL001", "outcome": "upscale_failed",
             "error": "timeout"},
        ]

        # Patch file paths to temp dir
        needs_file = tmp_path / "needs_upscale.json"
        good_file = tmp_path / "good_quality.json"
        needs_file.write_text(json.dumps(needs))
        good_file.write_text(json.dumps(good))

        with patch("photo_upscale_orchestrator.NEEDS_UPSCALE_JSON", needs_file), \
             patch("photo_upscale_orchestrator.GOOD_QUALITY_JSON", good_file):
            stats = update_triage_state(results)

        assert stats["promoted"] == 1
        assert stats["remaining_needs_upscale"] == 1
        assert stats["total_good_quality"] == 2  # existing + promoted

        remaining = json.loads(needs_file.read_text())
        assert len(remaining) == 1
        assert remaining[0]["part_number"] == "FAIL001"

        updated_good = json.loads(good_file.read_text())
        pns = {g["part_number"] for g in updated_good}
        assert "EXISTING001" in pns
        assert "OK001" in pns

    def test_failed_sku_stays_in_needs(self, tmp_path):
        """Failed SKU must remain in needs_upscale."""
        needs = [
            {"part_number": "FAIL001", "raw_photo_path": "x", "bucket": "needs_upscale"},
        ]
        good = []
        results = [
            {"part_number": "FAIL001", "outcome": "upscale_failed", "error": "timeout"},
        ]

        needs_file = tmp_path / "needs_upscale.json"
        good_file = tmp_path / "good_quality.json"
        needs_file.write_text(json.dumps(needs))
        good_file.write_text(json.dumps(good))

        with patch("photo_upscale_orchestrator.NEEDS_UPSCALE_JSON", needs_file), \
             patch("photo_upscale_orchestrator.GOOD_QUALITY_JSON", good_file):
            stats = update_triage_state(results)

        assert stats["promoted"] == 0
        assert stats["remaining_needs_upscale"] == 1

    def test_no_results_no_crash(self, tmp_path):
        """Empty results should not crash."""
        needs_file = tmp_path / "needs_upscale.json"
        good_file = tmp_path / "good_quality.json"
        needs_file.write_text("[]")
        good_file.write_text("[]")

        with patch("photo_upscale_orchestrator.NEEDS_UPSCALE_JSON", needs_file), \
             patch("photo_upscale_orchestrator.GOOD_QUALITY_JSON", good_file):
            stats = update_triage_state([])

        assert stats["promoted"] == 0
