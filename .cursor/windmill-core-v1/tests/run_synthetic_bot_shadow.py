from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from synthetic_bot_driver import replay_reference_fixture


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the synthetic Telegram shadow transcript.")
    parser.add_argument(
        "--fixture",
        default=str(Path(__file__).resolve().parent / "fixtures" / "synthetic_bot_reference.json"),
        help="Path to the synthetic transcript fixture JSON.",
    )
    args = parser.parse_args()

    result = replay_reference_fixture(Path(args.fixture))

    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["match_rate"] == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
