"""
secrets.py — Centralized secrets hub for all subsystems.

SINGLE SOURCE OF TRUTH for API keys across the project.
All subsystems MUST use get_secret() instead of their own loaders.

Location: config/.secrets.env (gitignored by *.env + explicit rule)
Method: dotenv_values() — NEVER load_dotenv() (no os.environ pollution)

Usage:
    from scripts.secrets import get_secret, get_all_secrets

    api_key = get_secret("ANTHROPIC_API_KEY")
    all_keys = get_all_secrets()

Fallback chain:
    1. config/.secrets.env  (primary — centralized hub)
    2. auditor_system/config/.env.auditors  (legacy compat)
    3. downloads/.env  (legacy compat)
    4. os.environ  (CI/CD, Docker)

If key not found in any source → raises KeyError (fail loud, not silent).
"""
from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# Ordered by priority — first file wins
_SECRETS_FILES = [
    _ROOT / "config" / ".secrets.env",
    _ROOT / "auditor_system" / "config" / ".env.auditors",
    _ROOT / "downloads" / ".env",
    _ROOT / "config" / ".env.providers",
    _ROOT / "orchestrator" / ".env.telegram",
    _ROOT / "orchestrator" / ".env.max",
]

_cache: dict[str, str] | None = None


def _load_all() -> dict[str, str]:
    """Load secrets from all .env files, first value wins."""
    global _cache
    if _cache is not None:
        return _cache

    try:
        from dotenv import dotenv_values
    except ImportError:
        # Fallback: manual .env parsing (no dependency needed)
        dotenv_values = _parse_env_file

    merged: dict[str, str] = {}
    for path in reversed(_SECRETS_FILES):  # reverse so first file wins
        if path.exists():
            try:
                values = dict(dotenv_values(str(path)))
                merged.update({k: v for k, v in values.items() if v})
            except Exception:
                pass

    _cache = merged
    return merged


def _parse_env_file(path: str) -> dict[str, str]:
    """Minimal .env parser — no dependency on python-dotenv."""
    result: dict[str, str] = {}
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and value:
                result[key] = value
    except (OSError, UnicodeDecodeError):
        pass
    return result


def get_secret(name: str, default: str | None = None) -> str:
    """Get a single secret by name.

    Checks centralized hub first, then legacy files, then os.environ.
    Raises KeyError if not found and no default provided.
    """
    secrets = _load_all()
    value = secrets.get(name)
    if value:
        return value

    # Fallback to os.environ (for CI/CD, Docker)
    env_val = os.environ.get(name, "")
    if env_val:
        return env_val

    if default is not None:
        return default

    raise KeyError(
        f"Secret '{name}' not found. "
        f"Add it to config/.secrets.env or set as environment variable."
    )


def get_all_secrets() -> dict[str, str]:
    """Get all loaded secrets as a dict. Key names only from files, not os.environ."""
    return dict(_load_all())


def has_secret(name: str) -> bool:
    """Check if a secret exists (in files or os.environ)."""
    secrets = _load_all()
    return bool(secrets.get(name)) or bool(os.environ.get(name, ""))


def clear_cache() -> None:
    """Force reload on next access. Useful after writing new keys."""
    global _cache
    _cache = None


def list_available_keys() -> list[str]:
    """List all available key names (for diagnostics, NOT values)."""
    secrets = _load_all()
    env_keys = {k for k in os.environ if k.endswith("_KEY") or k.endswith("_TOKEN") or k.endswith("_SECRET")}
    return sorted(set(secrets.keys()) | env_keys)


# ── CLI diagnostic ─────────────────────────────────────────────────────

def _cli_status() -> None:
    """Print secrets status (key names + sources, never values)."""
    print("Secrets Hub Status")
    print("=" * 60)

    for path in _SECRETS_FILES:
        exists = path.exists()
        status = "OK" if exists else "MISSING"
        count = 0
        if exists:
            try:
                vals = _parse_env_file(str(path))
                count = len([v for v in vals.values() if v])
            except Exception:
                pass
        rel = path.relative_to(_ROOT)
        print(f"  [{status:7}] {rel} ({count} keys)")

    print()
    print("Available keys:")
    for key in list_available_keys():
        print(f"  - {key}")


if __name__ == "__main__":
    _cli_status()
