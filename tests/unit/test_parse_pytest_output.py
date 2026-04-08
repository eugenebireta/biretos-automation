"""
tests/unit/test_parse_pytest_output.py

Edge case tests for _parse_pytest_output.
trace_id: orch_20260408T162253Z_a03ad7 / TEST-PARSE-PYTEST-EDGE
"""

from collect_packet import _parse_pytest_output


class TestParsePytestOutputEdgeCases:
    # trace_id: orch_20260408T162253Z_a03ad7
    def test_empty_string(self):
        """Empty output must return all-zero counts."""
        result = _parse_pytest_output("")
        assert result == {"passed": 0, "failed": 0, "skipped": 0, "error": 0}

    def test_output_without_digits(self):
        """Output containing keywords but no digits must return all-zero counts."""
        result = _parse_pytest_output("no tests ran — nothing collected")
        assert result == {"passed": 0, "failed": 0, "skipped": 0, "error": 0}

    def test_only_errors_no_passed_no_failed(self):
        """Output with only error counts (no passed/failed) must parse error correctly."""
        result = _parse_pytest_output("3 error in 0.42s")
        assert result == {"passed": 0, "failed": 0, "skipped": 0, "error": 3}
