#!/usr/bin/env python3
"""Normalize line endings to LF and strip UTF-8 BOM for specified files."""
from __future__ import annotations

import pathlib
import sys


def normalize_file(path: pathlib.Path) -> bool:
    original = path.read_bytes()
    data = original

    # Strip UTF-8 BOM if present.
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]

    # Convert CRLF/CR to LF.
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")

    if data == original:
        return False

    path.write_bytes(data)
    return True


def main(args: list[str]) -> int:
    if not args:
        print("Usage: normalize_line_endings.py <file> [<file> ...]", file=sys.stderr)
        return 1

    for raw in args:
        path = pathlib.Path(raw)
        if not path.exists():
            print(f"[SKIP] {raw} (not found)")
            continue

        changed = normalize_file(path)
        status = "UPDATED" if changed else "OK"
        print(f"[{status}] {raw}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
from pathlib import Path

FILES = [
    Path("infrastructure/vpn-bridge/wg-msk-client.conf"),
    Path("infrastructure/vpn-bridge/wg-usa-server.conf"),
]

for path in FILES:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    data = data.replace(b"\r\n", b"\n")
    path.write_bytes(data)
    print(f"Normalized {path}")

