"""
Compatibility shim for scripts.analytics.deep_analyze_14_16.
"""

from scripts.analytics import deep_analyze_14_16 as _impl  # type: ignore
from scripts.analytics.deep_analyze_14_16 import *  # noqa: F401,F403


def main() -> None:
    if hasattr(_impl, "main"):
        _impl.main()  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()

