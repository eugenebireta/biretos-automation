"""CAPTCHA solver for browser_vision_scout pipeline.

Two-tier solver chain:
  1. FlareSolverr (local, free) — sends URL to local FlareSolverr instance,
     which uses a real browser to solve Cloudflare/DDoS-Guard challenges.
     Returns cookies + rendered HTML.
  2. CapSolver (paid API, ~$0.001/solve) — fallback when FlareSolverr is
     unavailable or fails. Supports image CAPTCHA and Cloudflare Turnstile.

Both solvers return a CaptchaSolution with cookies that can be injected
into a Playwright browser context or requests session to bypass the challenge.

Usage:
    solver = CaptchaSolverChain()
    solution = solver.solve(url, screenshot_bytes=png)

    if solution.solved:
        # Inject cookies into Playwright context
        for cookie in solution.cookies:
            context.add_cookies([cookie])
        page.goto(url)  # now loads without challenge
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import capsolver as _capsolver
    HAS_CAPSOLVER = True
except ImportError:
    HAS_CAPSOLVER = False


# ── Solution contract ────────────────────────────────────────────────────────

@dataclass
class CaptchaSolution:
    """Result of a CAPTCHA solve attempt."""
    solved: bool = False
    solver_used: str = ""           # "flaresolverr" | "capsolver" | ""
    cookies: list[dict[str, Any]] = field(default_factory=list)
    user_agent: str = ""
    html: str = ""                  # rendered HTML (FlareSolverr only)
    cf_clearance: str = ""          # Cloudflare clearance token
    error: str = ""
    solve_time_sec: float = 0.0


# ── FlareSolverr ─────────────────────────────────────────────────────────────

FLARESOLVERR_DEFAULT_URL = "http://localhost:8191/v1"
FLARESOLVERR_TIMEOUT_SEC = 60


class FlareSolverrClient:
    """Client for local FlareSolverr instance.

    FlareSolverr runs as a standalone process or Docker container on port 8191.
    It launches a real browser internally to solve JS challenges.
    """

    def __init__(
        self,
        endpoint: str = FLARESOLVERR_DEFAULT_URL,
        timeout_sec: int = FLARESOLVERR_TIMEOUT_SEC,
    ) -> None:
        if not HAS_REQUESTS:
            raise RuntimeError("requests is required for FlareSolverr: pip install requests")
        self._endpoint = endpoint
        self._timeout = timeout_sec

    def is_available(self) -> bool:
        """Check if FlareSolverr is running."""
        try:
            resp = _requests.get(
                self._endpoint.replace("/v1", "/health"),
                timeout=3,
            )
            return resp.status_code == 200
        except Exception:
            # Some versions don't have /health — try /v1 with a test command
            try:
                resp = _requests.post(
                    self._endpoint,
                    json={"cmd": "sessions.list"},
                    timeout=3,
                )
                return resp.status_code == 200
            except Exception:
                return False

    def solve(self, url: str) -> CaptchaSolution:
        """Send URL to FlareSolverr, wait for challenge solve, return cookies."""
        t0 = time.monotonic()
        try:
            resp = _requests.post(
                self._endpoint,
                json={
                    "cmd": "request.get",
                    "url": url,
                    "maxTimeout": self._timeout * 1000,
                },
                timeout=self._timeout + 10,
            )
            data = resp.json()

            if data.get("status") != "ok":
                return CaptchaSolution(
                    error=f"flaresolverr_status={data.get('status')}: {data.get('message', '')}",
                    solve_time_sec=time.monotonic() - t0,
                )

            solution = data.get("solution", {})
            raw_cookies = solution.get("cookies", [])

            # Normalize cookies to Playwright format
            pw_cookies = []
            cf_clearance = ""
            for c in raw_cookies:
                pw_cookie: dict[str, Any] = {
                    "name": c.get("name", ""),
                    "value": c.get("value", ""),
                    "domain": c.get("domain", ""),
                    "path": c.get("path", "/"),
                }
                if c.get("httpOnly"):
                    pw_cookie["httpOnly"] = True
                if c.get("secure"):
                    pw_cookie["secure"] = True
                if c.get("sameSite"):
                    pw_cookie["sameSite"] = c["sameSite"]
                pw_cookies.append(pw_cookie)
                if c.get("name") == "cf_clearance":
                    cf_clearance = c.get("value", "")

            html = solution.get("response", "")

            # Validate: FlareSolverr returns status=ok even when the
            # JS challenge was NOT actually solved (ServicePipe, Qrator).
            # Detect known challenge markers in the returned HTML.
            actually_solved = True
            html_lower = html.lower()
            challenge_markers = [
                "servicepipe.ru",     # ServicePipe JS-challenge (vseinstrumenti.ru)
                "/__qrator/",         # Qrator JS-challenge (lemanapro.ru)
                "qrator_jsr",         # Qrator cookie loader
                "id_captcha_frame",   # ServicePipe captcha frame
            ]
            if any(marker in html_lower for marker in challenge_markers):
                actually_solved = False
                log.info(
                    "flaresolverr_challenge_not_solved",
                    extra={"url": url, "html_len": len(html)},
                )

            return CaptchaSolution(
                solved=actually_solved,
                solver_used="flaresolverr",
                cookies=pw_cookies,
                user_agent=solution.get("userAgent", ""),
                html=html,
                cf_clearance=cf_clearance,
                error="" if actually_solved else "flaresolverr_challenge_page_returned",
                solve_time_sec=time.monotonic() - t0,
            )

        except Exception as exc:
            log.warning(
                "flaresolverr_failed",
                extra={"url": url, "error": str(exc)},
            )
            return CaptchaSolution(
                error=f"flaresolverr_error: {type(exc).__name__}: {exc}",
                solve_time_sec=time.monotonic() - t0,
            )


# ── CapSolver ────────────────────────────────────────────────────────────────

CAPSOLVER_DEFAULT_TIMEOUT = 120


class CapSolverClient:
    """Client for CapSolver paid API.

    Supports:
    - Image CAPTCHA (rotating image, text recognition)
    - Cloudflare Turnstile / DDoS-Guard challenges
    """

    def __init__(
        self,
        api_key: str | None = None,
        timeout_sec: int = CAPSOLVER_DEFAULT_TIMEOUT,
    ) -> None:
        if not HAS_CAPSOLVER:
            raise RuntimeError("capsolver is required: pip install capsolver")
        self._api_key = api_key or os.environ.get("CAPSOLVER_API_KEY", "")
        self._timeout = timeout_sec
        if self._api_key:
            _capsolver.api_key = self._api_key

    def is_available(self) -> bool:
        """Check if CapSolver API key is configured and has balance."""
        if not self._api_key:
            return False
        try:
            balance = _capsolver.balance()
            has_balance = float(balance.get("balance", 0)) > 0
            if not has_balance:
                log.warning("capsolver_no_balance", extra={"balance": balance})
            return has_balance
        except Exception as exc:
            log.warning("capsolver_check_failed", extra={"error": str(exc)})
            return False

    def solve_image(self, image_bytes: bytes) -> CaptchaSolution:
        """Solve image CAPTCHA (rotating image, text recognition)."""
        t0 = time.monotonic()
        try:
            b64 = base64.standard_b64encode(image_bytes).decode("ascii")
            result = _capsolver.solve({
                "type": "ImageToTextTask",
                "body": b64,
                "module": "common",
            })
            text = result.get("text", "") if isinstance(result, dict) else str(result)
            return CaptchaSolution(
                solved=bool(text),
                solver_used="capsolver_image",
                error="" if text else "capsolver_empty_result",
                solve_time_sec=time.monotonic() - t0,
            )
        except Exception as exc:
            return CaptchaSolution(
                error=f"capsolver_image_error: {type(exc).__name__}: {exc}",
                solve_time_sec=time.monotonic() - t0,
            )

    def solve_cloudflare(
        self,
        url: str,
        website_key: str = "",
    ) -> CaptchaSolution:
        """Solve Cloudflare Turnstile / DDoS-Guard challenge."""
        t0 = time.monotonic()
        try:
            task: dict[str, Any] = {
                "type": "AntiCloudflareTask",
                "websiteURL": url,
            }
            if website_key:
                task["websiteKey"] = website_key

            result = _capsolver.solve(task)

            token = ""
            cookies: list[dict[str, Any]] = []
            if isinstance(result, dict):
                token = result.get("token", "") or result.get("cf_clearance", "")
                if result.get("cookies"):
                    for c in result["cookies"]:
                        cookies.append({
                            "name": c.get("name", ""),
                            "value": c.get("value", ""),
                            "domain": c.get("domain", ""),
                            "path": c.get("path", "/"),
                        })

            return CaptchaSolution(
                solved=bool(token or cookies),
                solver_used="capsolver_cloudflare",
                cookies=cookies,
                cf_clearance=token,
                solve_time_sec=time.monotonic() - t0,
            )
        except Exception as exc:
            return CaptchaSolution(
                error=f"capsolver_cf_error: {type(exc).__name__}: {exc}",
                solve_time_sec=time.monotonic() - t0,
            )


# ── Solver chain ─────────────────────────────────────────────────────────────

class CaptchaSolverChain:
    """Two-tier solver: FlareSolverr (free) -> CapSolver (paid fallback).

    Usage:
        chain = CaptchaSolverChain()
        solution = chain.solve(url)
    """

    def __init__(
        self,
        *,
        flaresolverr_url: str = FLARESOLVERR_DEFAULT_URL,
        capsolver_api_key: str | None = None,
        enable_flaresolverr: bool = True,
        enable_capsolver: bool = True,
    ) -> None:
        self._flare: FlareSolverrClient | None = None
        self._capsolver: CapSolverClient | None = None

        if enable_flaresolverr and HAS_REQUESTS:
            self._flare = FlareSolverrClient(endpoint=flaresolverr_url)
        if enable_capsolver and HAS_CAPSOLVER:
            self._capsolver = CapSolverClient(api_key=capsolver_api_key)

    def solve(
        self,
        url: str,
        *,
        screenshot_bytes: bytes | None = None,
    ) -> CaptchaSolution:
        """Try FlareSolverr first, then CapSolver as fallback.

        Args:
            url: The blocked URL to solve.
            screenshot_bytes: Optional screenshot for image CAPTCHA (CapSolver only).
        """
        errors: list[str] = []

        # ── Tier 1: FlareSolverr ─────────────────────────────────────────
        if self._flare is not None:
            if self._flare.is_available():
                log.info("captcha_trying_flaresolverr", extra={"url": url})
                solution = self._flare.solve(url)
                if solution.solved:
                    log.info(
                        "captcha_solved",
                        extra={
                            "solver": "flaresolverr",
                            "url": url,
                            "solve_time": solution.solve_time_sec,
                            "cookies_count": len(solution.cookies),
                        },
                    )
                    return solution
                errors.append(solution.error)
                log.info("flaresolverr_failed_trying_next", extra={"error": solution.error})
            else:
                errors.append("flaresolverr_not_available")
                log.info("flaresolverr_not_available")

        # ── Tier 2: CapSolver ────────────────────────────────────────────
        if self._capsolver is not None:
            if self._capsolver.is_available():
                log.info("captcha_trying_capsolver", extra={"url": url})
                # Try Cloudflare/DDoS-Guard task first
                solution = self._capsolver.solve_cloudflare(url)
                if solution.solved:
                    log.info(
                        "captcha_solved",
                        extra={
                            "solver": "capsolver_cloudflare",
                            "url": url,
                            "solve_time": solution.solve_time_sec,
                        },
                    )
                    return solution
                errors.append(solution.error)

                # Fallback: try image CAPTCHA if screenshot provided
                if screenshot_bytes:
                    log.info("capsolver_trying_image", extra={"url": url})
                    solution = self._capsolver.solve_image(screenshot_bytes)
                    if solution.solved:
                        log.info(
                            "captcha_solved",
                            extra={
                                "solver": "capsolver_image",
                                "url": url,
                                "solve_time": solution.solve_time_sec,
                            },
                        )
                        return solution
                    errors.append(solution.error)
            else:
                errors.append("capsolver_not_available")
                log.info("capsolver_not_available")

        # ── All solvers failed ───────────────────────────────────────────
        combined_error = "; ".join(e for e in errors if e)
        log.warning(
            "captcha_all_solvers_failed",
            extra={"url": url, "errors": combined_error},
        )
        return CaptchaSolution(error=combined_error or "no_solvers_available")
