"""
runner_factory.py — Public factory for ReviewRunner (CORE_GATE bridge).

Exposes create_review_runner() as a public API, extracting the logic
previously only accessible through the private _make_live_runner() in cli.py.

Key difference from _make_live_runner():
- Raises ConfigError on missing .env.auditors (instead of sys.exit(1))
- Fully importable without CLI machinery

Standalone usage:
    python -m auditor_system.runner_factory
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_SECRETS_PATH = Path("auditor_system/config/.env.auditors")
_CONFIG_PATH  = Path("auditor_system/config/models.yaml")


class ConfigError(RuntimeError):
    """Raised when required config / secrets are missing."""


def create_review_runner(
    proposal_text: str = "",
    runs_dir: str | Path = "auditor_system/runs",
    experience_dir: str | Path = "shadow_log",
):
    """
    Build and return a live ReviewRunner (Gemini CRITIC + Anthropic JUDGE).

    Args:
        proposal_text: optional proposal context to pass to MockBuilder
        runs_dir: path where run artifacts are stored
        experience_dir: path to shadow_log / experience dir

    Returns:
        ReviewRunner ready for `await runner.execute(task_pack)`

    Raises:
        ConfigError: if .env.auditors is missing or required keys absent
        ImportError: if provider packages are not installed
    """
    secrets = _load_secrets_safe()

    try:
        import yaml
        models_config: dict = {}
        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                models_config = yaml.safe_load(f) or {}
    except ImportError:
        models_config = {}

    gemini_model = models_config.get("auditors", {}).get("gemini", "gemini-3.1-pro-preview")
    anthropic_model = models_config.get("auditors", {}).get("anthropic", "claude-sonnet-4-6")

    from .providers.mock_builder import MockBuilder
    from .providers.gemini_auditor import GeminiAuditor
    from .providers.anthropic_auditor import AnthropicAuditor
    from .review_runner import ReviewRunner

    runner = ReviewRunner(
        builder=MockBuilder(proposal_text=proposal_text),
        auditors=[
            GeminiAuditor(model=gemini_model, api_key=secrets["GEMINI_API_KEY"]),
            AnthropicAuditor(model=anthropic_model, api_key=secrets["ANTHROPIC_API_KEY"]),
        ],
        runs_dir=Path(runs_dir),
        experience_dir=Path(experience_dir),
        model_config_path=_CONFIG_PATH,
    )

    logger.info(
        json.dumps({
            "trace_id":    "runner_factory",
            "gemini_model": gemini_model,
            "anthropic_model": anthropic_model,
            "runs_dir":    str(runs_dir),
            "outcome":     "runner_created",
        }, ensure_ascii=False)
    )
    return runner


def _load_secrets_safe() -> dict[str, str]:
    """
    Load API secrets from .env.auditors.

    Raises ConfigError (not sys.exit) when file or keys are missing.
    This allows callers to handle the error gracefully.
    """
    secrets_path = _SECRETS_PATH
    if not secrets_path.exists():
        raise ConfigError(
            f"Secrets file not found: {secrets_path}\n"
            "Create it with GEMINI_API_KEY and ANTHROPIC_API_KEY."
        )

    try:
        from dotenv import dotenv_values
        secrets = dict(dotenv_values(str(secrets_path)))
    except ImportError as exc:
        raise ConfigError("python-dotenv not installed. Run: pip install python-dotenv") from exc
    except Exception as exc:
        raise ConfigError(f"Failed to parse {secrets_path}: {exc}") from exc

    missing = [k for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY") if not secrets.get(k)]
    if missing:
        raise ConfigError(
            f"Missing required keys in {secrets_path}: {missing}"
        )

    return secrets


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    print("runner_factory.py — standalone demo")
    print(f"Secrets expected at: {_SECRETS_PATH.resolve()}")
    print(f"Config expected at:  {_CONFIG_PATH.resolve()}")

    try:
        _load_secrets_safe()
        print("Secrets: OK")
    except ConfigError as e:
        print(f"Secrets: NOT OK — {e}")
    print("Use create_review_runner() in code to build a live ReviewRunner.")
