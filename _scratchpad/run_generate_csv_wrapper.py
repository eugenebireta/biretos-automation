import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "_scratchpad" / "generate_csv_wrapper.log"


def main() -> int:
    try:
        module_path = ROOT / "insales_to_shopware_migration" / "src" / "generate_shopware_csv.py"
        scope: dict[str, object] = {"__name__": "__main__"}
        exec(module_path.read_text(encoding="utf-8"), scope)
    except SystemExit as exc:  # pragma: no cover
        code = exc.code or 0
        msg = "OK" if code == 0 else f"EXIT {code}"
        LOG_PATH.write_text(f"{msg}\n", encoding="utf-8")
        return code
    except Exception as exc:  # pragma: no cover
        LOG_PATH.write_text(f"ERROR: {exc}\n", encoding="utf-8")
        raise
    else:
        LOG_PATH.write_text("OK\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

