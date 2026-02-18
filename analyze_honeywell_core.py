"""
Compatibility shim for scripts.analytics.analyze_honeywell_core.
"""

from scripts.analytics import analyze_honeywell_core as _impl  # type: ignore
from scripts.analytics.analyze_honeywell_core import *  # noqa: F401,F403


def main() -> None:
    if hasattr(_impl, "main"):
        _impl.main()  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()

