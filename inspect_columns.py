"""
Compatibility shim for scripts.diagnostics.inspect_columns.
"""

from scripts.diagnostics import inspect_columns as _impl  # type: ignore
from scripts.diagnostics.inspect_columns import *  # noqa: F401,F403


def main() -> None:
    if hasattr(_impl, "main"):
        _impl.main()  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()

