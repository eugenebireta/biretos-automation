"""Deterministic test: .pre-commit-config.yaml is valid YAML and references ruff."""
import pathlib
import yaml


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / ".pre-commit-config.yaml"


def test_precommit_config_is_valid_yaml():
    assert CONFIG_PATH.exists(), f".pre-commit-config.yaml not found at {CONFIG_PATH}"
    with CONFIG_PATH.open() as f:
        data = yaml.safe_load(f)
    assert data is not None, "YAML parsed as None"


def test_precommit_config_references_ruff():
    with CONFIG_PATH.open() as f:
        raw = f.read()
    assert "ruff" in raw, "Expected 'ruff' to appear in .pre-commit-config.yaml"
