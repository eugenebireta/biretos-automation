"""
Compatibility shim for scripts.archive.compare_cores_v3.
"""

from scripts.archive import compare_cores_v3 as _impl  # type: ignore
from scripts.archive.compare_cores_v3 import *  # noqa: F401,F403


def main() -> None:
    if hasattr(_impl, "main"):
        _impl.main()  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()

