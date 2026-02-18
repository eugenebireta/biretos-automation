import argparse
import os
from pathlib import Path
import sys

import paramiko


def run_remote_command(client: paramiko.SSHClient, command: str) -> None:
    """Execute a command on the remote host and raise if it fails."""
    stdin, stdout, stderr = client.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()
    if exit_status != 0:
        err_output = stderr.read().decode().strip()
        raise RuntimeError(f"Command '{command}' failed with code {exit_status}: {err_output}")


def ensure_local_key(path: Path) -> None:
    """Ensure the local public key exists."""
    if not path.exists():
        raise FileNotFoundError(
            f"Public key not found at {path}. Generate it with 'ssh-keygen -t rsa -b 4096 -N \"\" -f {path.with_suffix('')}'."
        )


def append_remote_key(host: str, username: str, password: str, public_key: str) -> None:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, username=username, password=password)

    try:
        commands = [
            "mkdir -p ~/.ssh",
            "chmod 700 ~/.ssh",
            f"printf '%s\\n' '{public_key}' >> ~/.ssh/authorized_keys",
            "sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys",
            "chmod 600 ~/.ssh/authorized_keys",
        ]
        for cmd in commands:
            run_remote_command(client, cmd)
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Setup passwordless SSH access using an existing public key.")
    parser.add_argument("--host", required=True, help="Target server IP or hostname")
    parser.add_argument("--user", default="root", help="SSH username (default: root)")
    parser.add_argument("--password", required=True, help="SSH password")
    parser.add_argument(
        "--key",
        dest="key_path",
        default=str(Path.home() / ".ssh" / "id_rsa.pub"),
        help="Path to local public key (default: ~/.ssh/id_rsa.pub)",
    )
    args = parser.parse_args()

    key_path = Path(args.key_path).expanduser()
    ensure_local_key(key_path)

    public_key = key_path.read_text(encoding="utf-8").strip()
    if not public_key:
        raise ValueError(f"Public key file {key_path} is empty.")

    append_remote_key(args.host, args.user, args.password, public_key)
    print(f"[OK] Public key from '{key_path}' added to {args.user}@{args.host}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)











