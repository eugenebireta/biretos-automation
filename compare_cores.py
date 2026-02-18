"""
Compatibility shim for scripts.analytics.compare_cores.
"""

from scripts.analytics import compare_cores as _impl  # type: ignore
from scripts.analytics.compare_cores import *  # noqa: F401,F403


def main() -> None:
    if hasattr(_impl, "main"):
        _impl.main()  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()

