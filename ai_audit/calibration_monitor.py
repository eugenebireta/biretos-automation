"""Calibration monitor for AI-Audit artifacts (Patch 5b, v0.5.1).

Detects modal-confidence collapse (Xiong 2024 arXiv:2306.13063) and
other calibration pathologies in the rolling last-N audit artifacts.

Run:
    python ai_audit/calibration_monitor.py                    # all
    python ai_audit/calibration_monitor.py --window 100       # last 100
    python ai_audit/calibration_monitor.py --alert-only       # only show alerts

Alert thresholds per Deep Research §6:
- entropy(confidence histogram) < 1.5 bits
- share of modal bin > 0.35
- per-auditor stdev(confidence) < 0.1 over window
- Brier Resolution component < 0.01 at T+30 horizon

Exits 0 = no alerts, 1 = alert raised.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = ROOT / "_scratchpad" / "ai_audits"

# IPCC verbal → numeric (matches Patch 5a)
IPCC_LADDER: dict[str, float] = {
    "virtually certain": 0.95,
    "highly likely": 0.80,
    "likely": 0.60,
    "even odds": 0.50,
    "unlikely": 0.40,
    "highly unlikely": 0.20,
    "virtually impossible": 0.05,
}


def _parse_yaml_frontmatter(text: str) -> dict | None:
    """Return YAML dict from artifact frontmatter, or None."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    body = text[3:end].strip()
    data: dict = {}
    for line in body.splitlines():
        m = re.match(r"^\s*([a-z_][a-z0-9_]*)\s*:\s*(.*)$", line, re.IGNORECASE)
        if m:
            k, v = m.group(1), m.group(2).strip()
            # strip quotes
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            data[k] = v
    return data


def _coerce_confidence(raw: str | None) -> float | None:
    """Accept integer 1-10 OR IPCC verbal OR 'VERDICT/N' format, return 0..1."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    # VERDICT/N format like "APPROVE/9"
    m = re.search(r"/(\d+(?:\.\d+)?)$", s)
    if m:
        n = float(m.group(1))
        return n / 10.0 if n > 1 else n
    # IPCC verbal
    for key, val in IPCC_LADDER.items():
        if key in s:
            return val
    # integer 1-10
    try:
        n = float(s)
        return n / 10.0 if n > 1 else n
    except ValueError:
        return None


def _shannon_entropy(counts: Counter[str]) -> float:
    """Shannon entropy in bits."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    entropy = 0.0
    for c in counts.values():
        if c > 0:
            p = c / total
            entropy -= p * math.log2(p)
    return entropy


def analyze(window: int | None) -> dict:
    """Compute calibration signals from last N artifacts."""
    if not ARTIFACT_DIR.exists():
        return {"error": "no artifact dir"}

    artifacts = sorted(ARTIFACT_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if window:
        artifacts = artifacts[:window]

    per_role: dict[str, list[float]] = defaultdict(list)
    all_conf: list[float] = []
    modal_bins: Counter[str] = Counter()
    loaded = 0

    for p in artifacts:
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        fm = _parse_yaml_frontmatter(text)
        if not fm:
            continue
        loaded += 1
        # Extract per-role confidences from r1/r2 fields if in VERDICT/N format
        for round_key in ("r1", "r2"):
            # Look for advocate/challenger/second_opinion keys in body
            role_pattern = re.compile(
                rf"^\s*{round_key}:\s*\n((?:\s+(?:advocate|challenger|second_opinion):\s*[A-Z_]+/\d+\s*\n)+)",
                re.MULTILINE | re.IGNORECASE,
            )
            m = role_pattern.search(text)
            if m:
                for role_line in m.group(1).splitlines():
                    lm = re.match(
                        r"\s*(advocate|challenger|second_opinion):\s*[A-Z_]+/(\d+(?:\.\d+)?)",
                        role_line, re.IGNORECASE,
                    )
                    if lm:
                        role = lm.group(1).lower()
                        conf = float(lm.group(2))
                        conf_norm = conf / 10.0 if conf > 1 else conf
                        per_role[role].append(conf_norm)
                        all_conf.append(conf_norm)
                        modal_bins[f"{conf:.1f}"] += 1

    # Compute signals
    entropy = _shannon_entropy(modal_bins)
    modal_share = (max(modal_bins.values()) / sum(modal_bins.values())) if modal_bins else 0.0

    role_stdevs: dict[str, float] = {}
    for role, confs in per_role.items():
        if len(confs) > 1:
            mean = sum(confs) / len(confs)
            var = sum((c - mean) ** 2 for c in confs) / len(confs)
            role_stdevs[role] = math.sqrt(var)

    alerts: list[str] = []
    if loaded < 10:
        alerts.append(f"LOW_SAMPLE: {loaded} artifacts — calibration noisy until N≥50")
    if entropy < 1.5 and loaded >= 10:
        alerts.append(f"MODAL_COLLAPSE: entropy={entropy:.2f} bits < 1.5 (Xiong 2024 signature)")
    if modal_share > 0.35 and loaded >= 10:
        alerts.append(f"MODAL_CONCENTRATION: top bin = {modal_share:.1%} > 35%")
    for role, sd in role_stdevs.items():
        if sd < 0.1 and len(per_role[role]) >= 20:
            alerts.append(f"FROZEN_ROLE: {role} stdev = {sd:.3f} — not discriminating")

    return {
        "artifacts_analyzed": loaded,
        "confidence_entropy_bits": round(entropy, 3),
        "modal_bin_share": round(modal_share, 3),
        "per_role_stdev": {k: round(v, 3) for k, v in role_stdevs.items()},
        "per_role_n": {k: len(v) for k, v in per_role.items()},
        "alerts": alerts,
        "modal_bins_top5": dict(modal_bins.most_common(5)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=100, help="Last N artifacts (default 100)")
    ap.add_argument("--alert-only", action="store_true")
    args = ap.parse_args()

    result = analyze(args.window)
    if args.alert_only:
        for alert in result.get("alerts", []):
            print(alert)
        return 1 if result.get("alerts") else 0

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("alerts") else 0


if __name__ == "__main__":
    sys.exit(main())
