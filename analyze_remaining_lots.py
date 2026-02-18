"""
Compatibility shim for scripts.analytics.analyze_remaining_lots.
"""

from scripts.analytics import analyze_remaining_lots as _impl  # type: ignore
from scripts.analytics.analyze_remaining_lots import *  # noqa: F401,F403


def main() -> None:
    if hasattr(_impl, "main"):
        _impl.main()  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()

