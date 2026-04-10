"""Deterministic tests for orchestrator.get_version()."""

import importlib.util
import os
import sys

# tests/orchestrator/ shadows the real orchestrator package during pytest
# collection, so we load the real package explicitly by file path.
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_pkg_dir = os.path.join(_root, "orchestrator")

# Save and temporarily replace the orchestrator entry in sys.modules
_saved = sys.modules.pop("orchestrator", None)

# Load __version__ first
_ver_spec = importlib.util.spec_from_file_location(
    "orchestrator.__version__", os.path.join(_pkg_dir, "__version__.py"))
_ver_mod = importlib.util.module_from_spec(_ver_spec)
sys.modules["orchestrator.__version__"] = _ver_mod
_ver_spec.loader.exec_module(_ver_mod)

# Load __init__ as the orchestrator package
_init_spec = importlib.util.spec_from_file_location(
    "orchestrator", os.path.join(_pkg_dir, "__init__.py"),
    submodule_search_locations=[_pkg_dir])
_orch = importlib.util.module_from_spec(_init_spec)
sys.modules["orchestrator"] = _orch
_init_spec.loader.exec_module(_orch)

get_version = _orch.get_version
_expected_version = _ver_mod.__version__

# Restore original so we don't break other tests
if _saved is not None:
    sys.modules["orchestrator"] = _saved
else:
    del sys.modules["orchestrator"]


def test_get_version_returns_string():
    assert isinstance(get_version(), str)


def test_get_version_matches_dunder():
    assert get_version() == _expected_version


def test_get_version_not_empty():
    assert len(get_version()) > 0
