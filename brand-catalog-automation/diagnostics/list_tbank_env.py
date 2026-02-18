from pathlib import Path


def main() -> None:
    env_path = Path(".env")
    diagnostics_dir = Path("diagnostics")
    diagnostics_dir.mkdir(exist_ok=True)
    keys = []
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "TBANK" in line and "=" in line:
            keys.append(line.split("=", 1)[0])
    output = diagnostics_dir / "tbank_env_keys.txt"
    output.write_text("\n".join(keys), encoding="utf-8")


if __name__ == "__main__":
    main()

