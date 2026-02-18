"""
Compatibility shim for scripts.analytics.analyze_categories_deep.
"""

from scripts.analytics import analyze_categories_deep as _impl  # type: ignore
from scripts.analytics.analyze_categories_deep import *  # noqa: F401,F403


def main() -> None:
    if hasattr(_impl, "main"):
        _impl.main()  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()

