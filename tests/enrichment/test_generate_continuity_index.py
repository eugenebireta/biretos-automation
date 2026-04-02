"""Tests for the continuity index generator."""
from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path


_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from generate_continuity_index import render_continuity_index, write_continuity_index


def _write(path: Path, content: str) -> Path:
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
    return path


def test_render_continuity_index_mirrors_state_and_detects_drift(tmp_path):
    state = _write(
        tmp_path / "STATE.md",
        """
        # Autopilot State v2

        ## Current
        active_task: "8 - Stability Gate"
        task_id: "8"
        phase: MONITOR
        status: ACTIVE
        TODO later: doc audit / SOP cleanup after current R1 milestone
        awaiting: ">=30 closed cycles, 0 corruption"

        ## Task 7 Closeout
        task_7_status: MERGED
        task_7_pr: "https://example.test/pr/9"
        task_7_branch: "feat/task-7"
        task_7_commit: "df21f3d"

        ## History Tail
          - seq: 28
            note: "Task 7 MERGED. Advancing to Stage 8 - Stability Gate."
        """,
    )
    roadmap = _write(
        tmp_path / "ROADMAP.md",
        """
        Current position:
        Stage 8 - Stability Gate: MONITOR phase
        R1: Mass Catalog Pipeline: de facto active dev track, code merged to master

        Snapshot:
        Stage 8 - Stability Gate: не начат
        R1: Mass Catalog Pipeline: не начат
        """,
    )
    completed = _write(
        tmp_path / "COMPLETED_LOG.md",
        """
        # Completed Tasks Log

        2026-03-03 | Task 5.1 | CORE | Implemented CDM v2 runtime contracts
        """,
    )

    rendered = render_continuity_index(
        state_path=state,
        roadmap_path=roadmap,
        completed_log_path=completed,
        generated_on="2026-03-27",
    )

    assert "Preview with `python scripts/generate_continuity_index.py`." in rendered
    assert "Write with `python scripts/generate_continuity_index.py --write`." in rendered
    assert "Claim: `8 - Stability Gate` is the active execution thread in `MONITOR` / `ACTIVE`." in rendered
    assert "Claim: Continue `8 - Stability Gate` until the `STATE` exit criteria are satisfied." in rendered
    assert "Task 7" in rendered
    assert "Implemented CDM v2 runtime contracts" in rendered
    assert "ROADMAP` contains a live drift" in rendered
    assert "R1` as not started" in rendered
    assert "doc audit / SOP cleanup after current R1 milestone" in rendered


def test_render_continuity_index_handles_missing_optional_data(tmp_path):
    state = _write(
        tmp_path / "STATE.md",
        """
        # Autopilot State v2

        ## Current
        active_task: "5.2 - Validation Boundaries"
        task_id: "5.2"
        phase: BUILDER
        status: ACTIVE
        """,
    )
    roadmap = _write(tmp_path / "ROADMAP.md", "No matching drift here.")
    completed = _write(tmp_path / "COMPLETED_LOG.md", "# Completed Tasks Log")

    rendered = render_continuity_index(
        state_path=state,
        roadmap_path=roadmap,
        completed_log_path=completed,
        generated_on="2026-03-27",
    )

    assert "## Active Blockers" in rendered
    assert "None." in rendered
    assert "Claim: Continue `5.2 - Validation Boundaries` in `BUILDER` / `ACTIVE`." in rendered


def test_manual_addendum_is_preserved_on_write(tmp_path):
    state = _write(
        tmp_path / "STATE.md",
        """
        ## Current
        active_task: "8 - Stability Gate"
        task_id: "8"
        phase: MONITOR
        status: ACTIVE
        """,
    )
    roadmap = _write(tmp_path / "ROADMAP.md", "Stage 8 - Stability Gate: MONITOR phase")
    completed = _write(tmp_path / "COMPLETED_LOG.md", "# Completed Tasks Log")
    output = _write(
        tmp_path / "CONTINUITY_INDEX.md",
        """
        # CONTINUITY_INDEX

        ## Manual Addendum

        - Owner note kept by hand.
        """,
    )

    written = write_continuity_index(
        state_path=state,
        roadmap_path=roadmap,
        completed_log_path=completed,
        output_path=output,
        generated_on="2026-03-27",
    )

    assert "- Owner note kept by hand." in written
    assert "- Owner note kept by hand." in output.read_text(encoding="utf-8")


def test_generated_output_stays_under_size_cap_for_fixture(tmp_path):
    state = _write(
        tmp_path / "STATE.md",
        """
        ## Current
        active_task: "8 - Stability Gate"
        task_id: "8"
        phase: MONITOR
        status: ACTIVE
        awaiting: ">=30 closed cycles, 0 corruption"
        """,
    )
    roadmap = _write(
        tmp_path / "ROADMAP.md",
        """
        Stage 8 - Stability Gate: MONITOR phase
        Stage 8 - Stability Gate: не начат
        """,
    )
    completed = _write(
        tmp_path / "COMPLETED_LOG.md",
        """
        2026-03-03 | Task 5.1 | CORE | Implemented CDM v2 runtime contracts
        """,
    )

    rendered = render_continuity_index(
        state_path=state,
        roadmap_path=roadmap,
        completed_log_path=completed,
        generated_on="2026-03-27",
    )

    assert len(rendered.splitlines()) < 200
