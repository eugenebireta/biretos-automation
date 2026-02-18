"""
Remote Docker status checker for VPS-2 (77.233.222.214).
Uses Paramiko with password auth to execute `docker ps`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import paramiko

HOST = "77.233.222.214"  # VPS-2
USER = "root"
PASSWORD = "HuPtNj39"
COMMAND = "docker restart shopware && sleep 10 && docker ps"
LOG_PATH = Path(__file__).with_name("check_docker_result.json")


def run_remote_command() -> Dict[str, Any]:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=20)
    try:
        stdin, stdout, stderr = client.exec_command(COMMAND, timeout=30)
        exit_status = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="ignore")
        err = stderr.read().decode("utf-8", errors="ignore")
        return {"exit_status": exit_status, "stdout": out, "stderr": err}
    finally:
        client.close()


def main() -> int:
    try:
        result = run_remote_command()
    except Exception as exc:  # noqa: BLE001
        payload = {"success": False, "error": str(exc)}
        LOG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ERROR] {exc}")
        return 1

    payload = {"success": result["exit_status"] == 0, **result}
    LOG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(payload["stdout"] or payload["stderr"] or f"exit={payload['exit_status']}")
    return 0 if payload["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

