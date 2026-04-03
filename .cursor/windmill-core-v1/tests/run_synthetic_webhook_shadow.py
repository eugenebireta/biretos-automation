from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from synthetic_webhook_driver import replay_reference_fixture_n_times


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the synthetic TBank/CDEK webhook transcript.")
    parser.add_argument(
        "--fixture",
        default=str(Path(__file__).resolve().parent / "fixtures" / "synthetic_webhook_reference.json"),
        help="Path to the synthetic webhook transcript fixture JSON.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="How many times to replay the fixture batch. Use 7 for 56 synthetic requests.",
    )
    args = parser.parse_args()

    result = replay_reference_fixture_n_times(Path(args.fixture), repeat=args.repeat)

    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["match_rate"] == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
