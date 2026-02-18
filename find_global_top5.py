"""
Compatibility shim for scripts.analytics.find_global_top5.
"""

from scripts.analytics import find_global_top5 as _impl  # type: ignore
from scripts.analytics.find_global_top5 import *  # noqa: F401,F403


def main() -> None:
    if hasattr(_impl, "main"):
        _impl.main()  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()

