"""
Compatibility shim for scripts.archive.inspect_columns_v2.
"""

from scripts.archive import inspect_columns_v2 as _impl  # type: ignore
from scripts.archive.inspect_columns_v2 import *  # noqa: F401,F403


def main() -> None:
    if hasattr(_impl, "main"):
        _impl.main()  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()

