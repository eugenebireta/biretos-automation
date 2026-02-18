"""
Compatibility shim for scripts.analytics.recalc_rubles.
"""

from scripts.analytics import recalc_rubles as _impl  # type: ignore
from scripts.analytics.recalc_rubles import *  # noqa: F401,F403


def main() -> None:
    if hasattr(_impl, "main"):
        _impl.main()  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()

