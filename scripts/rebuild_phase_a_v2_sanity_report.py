"""Rebuild corrected sanity report from existing artifact folder only.

No pipeline execution. No external API calls. Reads existing bundles, sidecar,
manifest, and logs, then writes a corrected report with separated legacy/v2
status distributions.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from run_phase_a_v2_sanity_batch import (  # noqa: E402
    build_report,
    load_bundles,
)


DEFAULT_BATCH_ROOT = ROOT / "downloads" / "audits" / "phase_a_v2_sanity_20260326T171834Z"


def main() -> None:
    batch_root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BATCH_ROOT
    paths = {
        "batch_root": batch_root,
        "manifest_file": batch_root / "batch_manifest.json",
        "report_file": batch_root / "sanity_audit_report.corrected.json",
        "sidecar_file": batch_root / "candidate_sidecar.jsonl",
        "stdout_first": batch_root / "run_first_stdout.log",
        "stdout_resume": batch_root / "run_resume_stdout.log",
        "checkpoint_file": batch_root / "checkpoint.json",
        "evidence_dir": batch_root / "evidence",
        "export_dir": batch_root / "export",
    }

    manifest = json.loads(paths["manifest_file"].read_text(encoding="utf-8"))
    first_stdout = paths["stdout_first"].read_text(encoding="utf-8")
    resume_stdout = paths["stdout_resume"].read_text(encoding="utf-8")
    bundles = load_bundles(paths, manifest)
    sidecar_rows = [
        json.loads(line)
        for line in paths["sidecar_file"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = build_report(
        manifest=manifest,
        paths=paths,
        bundles=bundles,
        sidecar_rows=sidecar_rows,
        first_stdout=first_stdout,
        resume_stdout=resume_stdout,
    )
    report["rebuild_mode"] = "corrected_from_existing_artifacts_only"
    report["rebuild_inputs"] = {
        "manifest": str(paths["manifest_file"]),
        "sidecar": str(paths["sidecar_file"]),
        "run_first_stdout": str(paths["stdout_first"]),
        "run_resume_stdout": str(paths["stdout_resume"]),
        "evidence_dir": str(paths["evidence_dir"]),
    }
    paths["report_file"].write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(paths["report_file"])


if __name__ == "__main__":
    main()
