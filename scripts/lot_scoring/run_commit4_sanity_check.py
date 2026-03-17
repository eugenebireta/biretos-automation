from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(".")
DOWNLOADS = ROOT / "downloads"
AUDITS = DOWNLOADS / "audits"
REPORT_PATH = ROOT / "audits" / "commit4_sanity_report.json"

BASELINE = AUDITS / "baseline_v35.json"
DELTA = AUDITS / "delta_from_baseline.csv"
UNKNOWN_INTEL = AUDITS / "unknown_intelligence.csv"
RESULTS_FULL = DOWNLOADS / "results_full_v341.xlsx"
RESULTS_RANKED = DOWNLOADS / "results_ranked_v341.xlsx"
RANKED_CONTENT_SHA = AUDITS / "results_ranked_v341.content.sha256"
FULL_CONTENT_SHA = AUDITS / "results_full_v341.content.sha256"

FROZEN_FILES = [
    ROOT / "scripts" / "lot_scoring" / "pipeline" / "score.py",
    ROOT / "scripts" / "lot_scoring" / "cdm.py",
    ROOT / "scripts" / "lot_scoring" / "category_engine.py",
]


def sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mtime(path: Path) -> float | None:
    if not path.exists():
        return None
    return path.stat().st_mtime


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _read_content_sha(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if not _SHA256_RE.match(text):
        return ""
    return text


def run_ranking(*, save_baseline: bool) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "scripts.lot_scoring.run_full_ranking_v341",
        "--input",
        "honeywell.xlsx",
        "--output-dir",
        "downloads",
    ]
    if save_baseline:
        command.append("--save-baseline")
    process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    return {
        "cmd": " ".join(command),
        "exit_code": process.returncode,
        "stdout_tail": "\n".join(process.stdout.splitlines()[-25:]),
        "stderr_tail": "\n".join(process.stderr.splitlines()[-25:]),
    }


def collect_file_state() -> dict[str, Any]:
    return {
        "baseline_exists": BASELINE.exists(),
        "delta_exists": DELTA.exists(),
        "unknown_intelligence_exists": UNKNOWN_INTEL.exists(),
        "results_full_exists": RESULTS_FULL.exists(),
        "results_ranked_exists": RESULTS_RANKED.exists(),
        "hashes": {
            "baseline_v35_json": sha256(BASELINE),
            "delta_from_baseline_csv": sha256(DELTA),
            "unknown_intelligence_csv": sha256(UNKNOWN_INTEL),
            "results_full_v341_xlsx": sha256(RESULTS_FULL),
            "results_ranked_v341_xlsx": sha256(RESULTS_RANKED),
        },
        "mtimes": {
            "baseline_v35_json": mtime(BASELINE),
            "delta_from_baseline_csv": mtime(DELTA),
            "unknown_intelligence_csv": mtime(UNKNOWN_INTEL),
            "results_full_v341_xlsx": mtime(RESULTS_FULL),
            "results_ranked_v341_xlsx": mtime(RESULTS_RANKED),
        },
        "content_hashes": {
            "ranked_content_sha": _read_content_sha(RANKED_CONTENT_SHA),
            "full_content_sha": _read_content_sha(FULL_CONTENT_SHA),
        },
    }


def all_deltas_zero(delta_path: Path) -> tuple[bool, list[str]]:
    if not delta_path.exists():
        return False, ["delta file missing"]
    failures: list[str] = []
    with delta_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_idx, row in enumerate(reader, start=1):
            for key, value in row.items():
                if not key.startswith("delta_"):
                    continue
                try:
                    parsed = float(value)
                except Exception:
                    failures.append(f"row {row_idx} field {key} non-numeric: {value!r}")
                    continue
                if abs(parsed) > 1e-12:
                    failures.append(f"row {row_idx} field {key}={parsed}")
    return len(failures) == 0, failures


def _sorted_lot_df(path: Path) -> pd.DataFrame:
    frame = pd.read_excel(path)
    if "lot_id" not in frame.columns:
        raise ValueError(f"lot_id column missing in {path}")
    sorted_frame = frame.copy()
    sorted_frame["lot_id"] = sorted_frame["lot_id"].astype(str)
    sorted_frame = sorted_frame.sort_values(by=["lot_id"], ascending=[True], kind="mergesort")
    sorted_frame = sorted_frame.reset_index(drop=True)
    return sorted_frame


def _compare_excel_dataframes(df_a: pd.DataFrame, df_d: pd.DataFrame) -> tuple[bool, dict[str, Any]]:
    details: dict[str, Any] = {
        "shape_equal": tuple(df_a.shape) == tuple(df_d.shape),
        "columns_equal": list(df_a.columns) == list(df_d.columns),
        "numeric_columns": [],
        "string_columns": [],
        "numeric_mismatch_columns": [],
        "string_mismatch_columns": [],
    }
    if not details["shape_equal"] or not details["columns_equal"]:
        return False, details

    all_ok = True
    for column in df_a.columns:
        left = df_a[column]
        right = df_d[column]
        if (
            pd.api.types.is_numeric_dtype(left)
            and pd.api.types.is_numeric_dtype(right)
            and not pd.api.types.is_bool_dtype(left)
            and not pd.api.types.is_bool_dtype(right)
        ):
            details["numeric_columns"].append(column)
            left_num = pd.to_numeric(left, errors="coerce")
            right_num = pd.to_numeric(right, errors="coerce")
            diff = (left_num - right_num).abs()
            nan_equal = left_num.isna() & right_num.isna()
            equal_mask = (diff <= 1e-9) | nan_equal
            if not bool(equal_mask.all()):
                all_ok = False
                max_diff = float(diff.fillna(0.0).max())
                details["numeric_mismatch_columns"].append({"column": column, "max_abs_diff": round(max_diff, 12)})
        else:
            details["string_columns"].append(column)
            left_text = left.fillna("").astype(str)
            right_text = right.fillna("").astype(str)
            if not bool((left_text == right_text).all()):
                all_ok = False
                details["string_mismatch_columns"].append(column)
    return all_ok, details


def run_sanity_check() -> dict[str, Any]:
    failures: list[str] = []
    frozen_before = {str(path): sha256(path) for path in FROZEN_FILES}

    if AUDITS.exists():
        shutil.rmtree(AUDITS)

    # Scenario A
    scenario_a_run = run_ranking(save_baseline=False)
    scenario_a_state = collect_file_state()
    if scenario_a_run["exit_code"] != 0:
        failures.append("Scenario A run failed")
    if not scenario_a_state["baseline_exists"]:
        failures.append("Scenario A: baseline_v35.json must exist")
    if scenario_a_state["delta_exists"]:
        failures.append("Scenario A: delta_from_baseline.csv must NOT exist")
    if not scenario_a_state["unknown_intelligence_exists"]:
        failures.append("Scenario A: unknown_intelligence.csv must exist")
    frame_a_full = _sorted_lot_df(RESULTS_FULL)
    frame_a_ranked = _sorted_lot_df(RESULTS_RANKED)

    # Scenario B
    time.sleep(1.1)
    scenario_b_run = run_ranking(save_baseline=False)
    scenario_b_state = collect_file_state()
    if scenario_b_run["exit_code"] != 0:
        failures.append("Scenario B run failed")
    if not scenario_b_state["delta_exists"]:
        failures.append("Scenario B: delta_from_baseline.csv must exist")
    zero_b, zero_b_failures = all_deltas_zero(DELTA)
    if not zero_b:
        failures.append("Scenario B: delta_* are not zero")
        failures.extend([f"Scenario B: {item}" for item in zero_b_failures[:10]])
    if scenario_b_state["hashes"]["baseline_v35_json"] != scenario_a_state["hashes"]["baseline_v35_json"]:
        failures.append("Scenario B: baseline hash changed unexpectedly")
    if scenario_b_state["hashes"]["unknown_intelligence_csv"] != scenario_a_state["hashes"]["unknown_intelligence_csv"]:
        failures.append("Scenario B: unknown_intelligence hash changed unexpectedly")

    # Scenario C
    time.sleep(1.1)
    scenario_c_run = run_ranking(save_baseline=True)
    scenario_c_state = collect_file_state()
    if scenario_c_run["exit_code"] != 0:
        failures.append("Scenario C run failed")
    if scenario_c_state["mtimes"]["baseline_v35_json"] is None or scenario_b_state["mtimes"]["baseline_v35_json"] is None:
        failures.append("Scenario C: baseline mtime missing")
    elif not (scenario_c_state["mtimes"]["baseline_v35_json"] > scenario_b_state["mtimes"]["baseline_v35_json"]):
        failures.append("Scenario C: baseline mtime did not increase")
    if scenario_c_state["hashes"]["delta_from_baseline_csv"] != scenario_b_state["hashes"]["delta_from_baseline_csv"]:
        failures.append("Scenario C: delta hash changed but should stay the same")
    if scenario_c_state["mtimes"]["delta_from_baseline_csv"] != scenario_b_state["mtimes"]["delta_from_baseline_csv"]:
        failures.append("Scenario C: delta mtime changed but should stay the same")
    if scenario_c_state["hashes"]["baseline_v35_json"] != scenario_b_state["hashes"]["baseline_v35_json"]:
        failures.append("Scenario C: baseline content hash changed (non-deterministic)")

    # Scenario D
    time.sleep(1.1)
    scenario_d_run = run_ranking(save_baseline=False)
    scenario_d_state = collect_file_state()
    if scenario_d_run["exit_code"] != 0:
        failures.append("Scenario D run failed")
    if not scenario_d_state["delta_exists"]:
        failures.append("Scenario D: delta_from_baseline.csv must exist")
    zero_d, zero_d_failures = all_deltas_zero(DELTA)
    if not zero_d:
        failures.append("Scenario D: delta_* are not zero")
        failures.extend([f"Scenario D: {item}" for item in zero_d_failures[:10]])
    if scenario_d_state["mtimes"]["delta_from_baseline_csv"] is None or scenario_c_state["mtimes"]["delta_from_baseline_csv"] is None:
        failures.append("Scenario D: delta mtime missing")
    elif not (scenario_d_state["mtimes"]["delta_from_baseline_csv"] > scenario_c_state["mtimes"]["delta_from_baseline_csv"]):
        failures.append("Scenario D: delta was not recreated (mtime did not increase)")
    frame_d_full = _sorted_lot_df(RESULTS_FULL)
    frame_d_ranked = _sorted_lot_df(RESULTS_RANKED)

    unknown_identical = (
        scenario_a_state["hashes"]["unknown_intelligence_csv"]
        == scenario_b_state["hashes"]["unknown_intelligence_csv"]
        == scenario_c_state["hashes"]["unknown_intelligence_csv"]
        == scenario_d_state["hashes"]["unknown_intelligence_csv"]
    )
    baseline_identical = (
        scenario_a_state["hashes"]["baseline_v35_json"]
        == scenario_b_state["hashes"]["baseline_v35_json"]
        == scenario_c_state["hashes"]["baseline_v35_json"]
        == scenario_d_state["hashes"]["baseline_v35_json"]
    )
    delta_identical = (
        scenario_b_state["hashes"]["delta_from_baseline_csv"]
        == scenario_c_state["hashes"]["delta_from_baseline_csv"]
        == scenario_d_state["hashes"]["delta_from_baseline_csv"]
    )

    excel_full_identical, excel_full_details = _compare_excel_dataframes(frame_a_full, frame_d_full)
    excel_ranked_identical, excel_ranked_details = _compare_excel_dataframes(frame_a_ranked, frame_d_ranked)
    excel_content_identical = excel_full_identical and excel_ranked_identical

    if not unknown_identical:
        failures.append("Determinism: unknown_intelligence hashes differ")
    if not baseline_identical:
        failures.append("Determinism: baseline hashes differ")
    if not delta_identical:
        failures.append("Determinism: delta hashes differ")
    if not excel_content_identical:
        failures.append("Determinism: excel content differs (A vs D)")

    ranked_sha_a = scenario_a_state["content_hashes"]["ranked_content_sha"]
    ranked_sha_d = scenario_d_state["content_hashes"]["ranked_content_sha"]
    full_sha_a = scenario_a_state["content_hashes"]["full_content_sha"]
    full_sha_d = scenario_d_state["content_hashes"]["full_content_sha"]

    ranked_content_sha_identical = bool(ranked_sha_a and ranked_sha_d and ranked_sha_a == ranked_sha_d)
    full_content_sha_identical = bool(full_sha_a and full_sha_d and full_sha_a == full_sha_d)
    content_sha_identical = ranked_content_sha_identical and full_content_sha_identical

    if not ranked_sha_a:
        failures.append("Determinism: ranked content SHA missing after Scenario A")
    if not ranked_sha_d:
        failures.append("Determinism: ranked content SHA missing after Scenario D")
    if not full_sha_a:
        failures.append("Determinism: full content SHA missing after Scenario A")
    if not full_sha_d:
        failures.append("Determinism: full content SHA missing after Scenario D")
    if ranked_sha_a and ranked_sha_d and ranked_sha_a != ranked_sha_d:
        failures.append(f"Determinism: ranked content SHA differs (A={ranked_sha_a[:16]}.. vs D={ranked_sha_d[:16]}..)")
    if full_sha_a and full_sha_d and full_sha_a != full_sha_d:
        failures.append(f"Determinism: full content SHA differs (A={full_sha_a[:16]}.. vs D={full_sha_d[:16]}..)")

    frozen_after = {str(path): sha256(path) for path in FROZEN_FILES}
    frozen_core_modified = any(frozen_before[path] != frozen_after[path] for path in frozen_before)
    if frozen_core_modified:
        failures.append("Frozen core files were modified")

    status = "PASS" if not failures else "FAIL"
    report = {
        "status": status,
        "scenario_A": {
            "run": scenario_a_run,
            "checks": {
                "baseline_exists": scenario_a_state["baseline_exists"],
                "delta_absent": not scenario_a_state["delta_exists"],
                "unknown_intelligence_exists": scenario_a_state["unknown_intelligence_exists"],
            },
            "state": scenario_a_state,
        },
        "scenario_B": {
            "run": scenario_b_run,
            "checks": {
                "delta_exists": scenario_b_state["delta_exists"],
                "all_delta_zero": zero_b,
                "baseline_hash_unchanged_vs_A": scenario_b_state["hashes"]["baseline_v35_json"]
                == scenario_a_state["hashes"]["baseline_v35_json"],
                "unknown_hash_unchanged_vs_A": scenario_b_state["hashes"]["unknown_intelligence_csv"]
                == scenario_a_state["hashes"]["unknown_intelligence_csv"],
            },
            "state": scenario_b_state,
        },
        "scenario_C": {
            "run": scenario_c_run,
            "checks": {
                "baseline_mtime_changed_vs_B": (
                    scenario_c_state["mtimes"]["baseline_v35_json"] is not None
                    and scenario_b_state["mtimes"]["baseline_v35_json"] is not None
                    and scenario_c_state["mtimes"]["baseline_v35_json"] > scenario_b_state["mtimes"]["baseline_v35_json"]
                ),
                "delta_not_recreated_hash_same_vs_B": scenario_c_state["hashes"]["delta_from_baseline_csv"]
                == scenario_b_state["hashes"]["delta_from_baseline_csv"],
                "delta_not_recreated_mtime_same_vs_B": scenario_c_state["mtimes"]["delta_from_baseline_csv"]
                == scenario_b_state["mtimes"]["delta_from_baseline_csv"],
                "baseline_content_identical_vs_B": scenario_c_state["hashes"]["baseline_v35_json"]
                == scenario_b_state["hashes"]["baseline_v35_json"],
            },
            "state": scenario_c_state,
        },
        "scenario_D": {
            "run": scenario_d_run,
            "checks": {
                "delta_exists": scenario_d_state["delta_exists"],
                "delta_recreated_mtime_gt_C": (
                    scenario_d_state["mtimes"]["delta_from_baseline_csv"] is not None
                    and scenario_c_state["mtimes"]["delta_from_baseline_csv"] is not None
                    and scenario_d_state["mtimes"]["delta_from_baseline_csv"] > scenario_c_state["mtimes"]["delta_from_baseline_csv"]
                ),
                "all_delta_zero": zero_d,
            },
            "state": scenario_d_state,
        },
        "determinism_check": {
            "unknown_intelligence_identical": unknown_identical,
            "baseline_identical": baseline_identical,
            "delta_identical": delta_identical,
            "excel_content_identical": excel_content_identical,
            "ranked_content_sha_identical": ranked_content_sha_identical,
            "full_content_sha_identical": full_content_sha_identical,
            "content_sha_identical": content_sha_identical,
            "content_sha_values": {
                "scenario_A": {"ranked": ranked_sha_a, "full": full_sha_a},
                "scenario_D": {"ranked": ranked_sha_d, "full": full_sha_d},
            },
            "excel_content_comparison": {
                "results_full_v341": excel_full_details,
                "results_ranked_v341": excel_ranked_details,
            },
        },
        "frozen_core_modified": bool(frozen_core_modified),
        "frozen_core_hashes_before": frozen_before,
        "frozen_core_hashes_after": frozen_after,
        "failures": failures,
    }
    return report


def main() -> None:
    report = run_sanity_check()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report_path": str(REPORT_PATH), "failures_count": len(report["failures"])}, ensure_ascii=False))
    for failure in report["failures"][:30]:
        print(f"FAIL: {failure}")


if __name__ == "__main__":
    main()
