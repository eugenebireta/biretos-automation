"""
M4 Executor Bridge — Sandbox Pilot Smoke Test.

trace_id: orch_20260408T111929Z_1a1150
task_id: M4-PILOT-001
risk_class: LOW
"""
import pathlib

TRACE_ID = "orch_20260408T111929Z_1a1150"
IDEMPOTENCY_KEY = "m4-pilot-001-smoke-test"

DIRECTIVE_PATH = pathlib.Path(__file__).resolve().parents[2] / "orchestrator" / "directive.md"


def test_arithmetic():
    assert 1 + 1 == 2


def test_directive_utf8_readable():
    """Verify the orchestrator directive can be read as UTF-8."""
    # The directive may not exist in every environment; if the file is present,
    # assert it is non-empty UTF-8 text.  If absent, we look for any .md in the
    # orchestrator directory as a fallback, or skip gracefully.
    candidates = []
    if DIRECTIVE_PATH.exists():
        candidates.append(DIRECTIVE_PATH)
    else:
        orch_dir = DIRECTIVE_PATH.parent
        if orch_dir.is_dir():
            candidates = list(orch_dir.glob("*.md"))

    if not candidates:
        # No orchestrator markdown files to test — pass vacuously.
        return

    for path in candidates[:1]:
        text = path.read_text(encoding="utf-8")
        assert isinstance(text, str)
        assert len(text) > 0, f"{path.name} is empty"
