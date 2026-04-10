"""Tests for orchestrator.version module."""
from version import VERSION, get_version


def test_version_constant_value():
    """VERSION constant equals '1.0.0'."""
    assert VERSION == "1.0.0"


def test_get_version_returns_version_string():
    """get_version() returns the VERSION constant."""
    result = get_version(trace_id="test-trace-001")
    assert result == "1.0.0"


def test_get_version_return_type():
    """get_version() returns a str."""
    result = get_version(trace_id="test-trace-002", idempotency_key="idem-key-002")
    assert isinstance(result, str)
