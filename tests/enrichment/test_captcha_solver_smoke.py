"""Smoke tests for captcha_solver.py — unit tests with mocked HTTP.

Live test results (2026-04-03):
  - FlareSolverr v3.4.6 on localhost:8191: OPERATIONAL
  - vseinstrumenti.ru: ServicePipe JS-challenge NOT solved by FlareSolverr
    (returns challenge HTML, not product page)
  - lemanapro.ru: Qrator JS-challenge NOT solved by FlareSolverr
    (returns challenge HTML with qauth.js loader)
  - Conclusion: FlareSolverr handles Cloudflare but NOT ServicePipe/Qrator.
    CDP to real browser remains the only working approach for these sites.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from captcha_solver import CaptchaSolution, CaptchaSolverChain, FlareSolverrClient


class TestFlareSolverrClient:

    def test_is_available_health_ok(self):
        with patch("captcha_solver._requests") as mock_req:
            mock_req.get.return_value = MagicMock(status_code=200)
            client = FlareSolverrClient()
            assert client.is_available() is True

    def test_is_available_health_down(self):
        with patch("captcha_solver._requests") as mock_req:
            mock_req.get.side_effect = ConnectionError("refused")
            mock_req.post.side_effect = ConnectionError("refused")
            client = FlareSolverrClient()
            assert client.is_available() is False

    def test_solve_success(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "ok",
            "solution": {
                "response": "<html><body>Product page</body></html>",
                "cookies": [
                    {"name": "cf_clearance", "value": "abc123", "domain": ".example.com", "path": "/"}
                ],
                "userAgent": "Mozilla/5.0 Test",
            },
        }
        with patch("captcha_solver._requests") as mock_req:
            mock_req.post.return_value = mock_response
            client = FlareSolverrClient()
            sol = client.solve("https://example.com")

        assert sol.solved is True
        assert sol.solver_used == "flaresolverr"
        assert sol.cf_clearance == "abc123"
        assert len(sol.cookies) == 1
        assert sol.user_agent == "Mozilla/5.0 Test"

    def test_solve_non_ok_status(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "error",
            "message": "Timeout solving challenge",
        }
        with patch("captcha_solver._requests") as mock_req:
            mock_req.post.return_value = mock_response
            client = FlareSolverrClient()
            sol = client.solve("https://example.com")

        assert sol.solved is False
        assert "error" in sol.error

    def test_solve_network_error(self):
        with patch("captcha_solver._requests") as mock_req:
            mock_req.post.side_effect = ConnectionError("refused")
            client = FlareSolverrClient()
            sol = client.solve("https://example.com")

        assert sol.solved is False
        assert "ConnectionError" in sol.error

    def test_solve_detects_servicepipe_challenge(self):
        """FlareSolverr status=ok but HTML is ServicePipe challenge page."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "ok",
            "solution": {
                "response": '<html><script src="https://servicepipe.ru/static/jsrsasign-all-min.js"></script></html>',
                "cookies": [{"name": "new_auth_flow", "value": "on", "domain": ".example.com", "path": "/"}],
                "userAgent": "Test",
            },
        }
        with patch("captcha_solver._requests") as mock_req:
            mock_req.post.return_value = mock_response
            client = FlareSolverrClient()
            sol = client.solve("https://example.com")

        assert sol.solved is False
        assert "challenge_page_returned" in sol.error
        assert len(sol.cookies) == 1  # cookies still returned

    def test_solve_detects_qrator_challenge(self):
        """FlareSolverr status=ok but HTML is Qrator challenge page."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "ok",
            "solution": {
                "response": '<html><script src="/__qrator/qauth.js"></script></html>',
                "cookies": [{"name": "qrator_jsr", "value": "v2.0", "domain": ".example.com", "path": "/"}],
                "userAgent": "Test",
            },
        }
        with patch("captcha_solver._requests") as mock_req:
            mock_req.post.return_value = mock_response
            client = FlareSolverrClient()
            sol = client.solve("https://example.com")

        assert sol.solved is False
        assert "challenge_page_returned" in sol.error

    def test_cookie_normalization_playwright_format(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "ok",
            "solution": {
                "response": "<html></html>",
                "cookies": [
                    {
                        "name": "session",
                        "value": "xyz",
                        "domain": ".example.com",
                        "path": "/app",
                        "httpOnly": True,
                        "secure": True,
                        "sameSite": "Lax",
                    }
                ],
                "userAgent": "Test",
            },
        }
        with patch("captcha_solver._requests") as mock_req:
            mock_req.post.return_value = mock_response
            client = FlareSolverrClient()
            sol = client.solve("https://example.com")

        c = sol.cookies[0]
        assert c["name"] == "session"
        assert c["httpOnly"] is True
        assert c["secure"] is True
        assert c["sameSite"] == "Lax"


class TestCaptchaSolverChain:

    def test_chain_returns_flaresolverr_on_success(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "ok",
            "solution": {
                "response": "<html>Solved page content here</html>",
                "cookies": [],
                "userAgent": "Test",
            },
        }
        with patch("captcha_solver._requests") as mock_req:
            mock_req.get.return_value = MagicMock(status_code=200)
            mock_req.post.return_value = mock_response
            chain = CaptchaSolverChain(enable_capsolver=False)
            sol = chain.solve("https://example.com")

        assert sol.solved is True
        assert sol.solver_used == "flaresolverr"

    def test_chain_all_disabled(self):
        chain = CaptchaSolverChain(enable_flaresolverr=False, enable_capsolver=False)
        sol = chain.solve("https://example.com")
        assert sol.solved is False
        assert "no_solvers_available" in sol.error

    def test_chain_flare_unavailable_no_capsolver(self):
        with patch("captcha_solver._requests") as mock_req:
            mock_req.get.side_effect = ConnectionError("refused")
            mock_req.post.side_effect = ConnectionError("refused")
            chain = CaptchaSolverChain(enable_capsolver=False)
            sol = chain.solve("https://example.com")

        assert sol.solved is False
        assert "flaresolverr_not_available" in sol.error

    def test_solution_dataclass_defaults(self):
        sol = CaptchaSolution()
        assert sol.solved is False
        assert sol.solver_used == ""
        assert sol.cookies == []
        assert sol.error == ""
