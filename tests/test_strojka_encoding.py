"""Test subprocess encoding in strojka.py — Cyrillic text must not garble.

trace_id: orch_20260408T191747Z_9e2c97
Deterministic test — no live API, no unmocked time/randomness.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import importlib.util

import pytest

_root = Path(os.path.dirname(__file__)).resolve().parent
_strojka_path = _root / "orchestrator" / "strojka.py"


def _import_strojka():
    """Import strojka.py by file path to avoid tests/orchestrator/ namespace clash.

    Caches in sys.modules so patch() targets resolve to the same object.
    """
    key = "orchestrator.strojka"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, _strojka_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


TRACE_ID = "orch_20260408T191747Z_9e2c97"
IDEMPOTENCY_KEY = "test-strojka-encoding-001"

# Cyrillic phrases that cp1251/cp866 would mangle if UTF-8 bytes are decoded wrong
CYRILLIC_STDOUT = "Задача выполнена успешно\nСледующий шаг: проверить манифест\n"
CYRILLIC_STDERR = "ПРЕДУПРЕЖДЕНИЕ: устаревший ключ конфигурации\n"


def _make_completed_process(stdout: str, stderr: str, returncode: int = 0):
    cp = MagicMock()
    cp.stdout = stdout
    cp.stderr = stderr
    cp.returncode = returncode
    return cp


# ---------------------------------------------------------------------------
# 1. subprocess.run receives encoding="utf-8"
# ---------------------------------------------------------------------------

def test_run_orchestrator_passes_utf8_encoding(tmp_path, monkeypatch):
    """run_orchestrator must call subprocess.run with encoding='utf-8'."""
    strojka = _import_strojka()

    # Point ORCH_DIR at a temp dir so yaml read doesn't fail
    fake_cfg = tmp_path / "config.yaml"
    fake_cfg.write_text("auto_execute: false\n", encoding="utf-8")
    fake_main = tmp_path / "main.py"
    fake_main.write_text("", encoding="utf-8")

    monkeypatch.setattr(strojka, "ORCH_DIR", tmp_path)

    captured_kwargs = {}

    def fake_run(cmd, **kwargs):
        captured_kwargs.update(kwargs)
        return _make_completed_process(stdout="ok\n", stderr="")

    with patch("orchestrator.strojka.subprocess.run", side_effect=fake_run):
        strojka.run_orchestrator(auto_execute=False)

    assert captured_kwargs.get("encoding") == "utf-8", (
        f"Expected encoding='utf-8', got {captured_kwargs.get('encoding')!r}"
    )


# ---------------------------------------------------------------------------
# 2. PYTHONIOENCODING=utf-8 is injected into the subprocess environment
# ---------------------------------------------------------------------------

def test_run_orchestrator_sets_pythonioencoding(tmp_path, monkeypatch):
    """PYTHONIOENCODING must be set to 'utf-8' in the subprocess env."""
    strojka = _import_strojka()

    fake_cfg = tmp_path / "config.yaml"
    fake_cfg.write_text("auto_execute: false\n", encoding="utf-8")
    monkeypatch.setattr(strojka, "ORCH_DIR", tmp_path)

    captured_env = {}

    def fake_run(cmd, **kwargs):
        captured_env.update(kwargs.get("env", {}))
        return _make_completed_process(stdout="", stderr="")

    with patch("orchestrator.strojka.subprocess.run", side_effect=fake_run):
        strojka.run_orchestrator(auto_execute=False)

    assert captured_env.get("PYTHONIOENCODING") == "utf-8", (
        f"Expected PYTHONIOENCODING='utf-8', got {captured_env.get('PYTHONIOENCODING')!r}"
    )


# ---------------------------------------------------------------------------
# 3. Cyrillic stdout is printed without garbling
# ---------------------------------------------------------------------------

def test_cyrillic_stdout_preserved(tmp_path, monkeypatch, capsys):
    """Cyrillic characters in subprocess stdout must reach sys.stdout intact."""
    strojka = _import_strojka()

    fake_cfg = tmp_path / "config.yaml"
    fake_cfg.write_text("auto_execute: false\n", encoding="utf-8")
    monkeypatch.setattr(strojka, "ORCH_DIR", tmp_path)

    with patch(
        "orchestrator.strojka.subprocess.run",
        return_value=_make_completed_process(
            stdout=CYRILLIC_STDOUT, stderr=""
        ),
    ):
        strojka.run_orchestrator(auto_execute=False)

    out = capsys.readouterr().out
    assert "Задача выполнена успешно" in out, (
        "Cyrillic stdout was garbled or lost — encoding mismatch"
    )
    assert "Следующий шаг" in out


# ---------------------------------------------------------------------------
# 4. Cyrillic bytes round-trip: UTF-8 encode → decode
# ---------------------------------------------------------------------------

def test_cyrillic_bytes_roundtrip():
    """Encoding/decoding Cyrillic as UTF-8 must be lossless."""
    samples = [
        "Привет мир",
        "Задача выполнена успешно",
        "Следующий шаг: проверить манифест",
        "ПРЕДУПРЕЖДЕНИЕ: устаревший ключ конфигурации",
        "стройка — ИИ интеграция",
    ]
    for text in samples:
        encoded = text.encode("utf-8")
        decoded = encoded.decode("utf-8")
        assert decoded == text, f"Round-trip failed for: {text!r}"


# ---------------------------------------------------------------------------
# 5. cp1251 decode of UTF-8 bytes produces garbled text (negative control)
# ---------------------------------------------------------------------------

def test_cp1251_garbles_cyrillic_utf8():
    """Confirm that decoding UTF-8-encoded Cyrillic via cp1251 corrupts text.

    This is the negative control: proves why encoding='utf-8' is required.
    """
    original = "Задача выполнена"
    utf8_bytes = original.encode("utf-8")
    # cp1251 cannot correctly decode multi-byte UTF-8 sequences
    garbled = utf8_bytes.decode("cp1251", errors="replace")
    assert garbled != original, (
        "cp1251 unexpectedly reproduced UTF-8 Cyrillic text — test logic error"
    )
    assert "?" in garbled or "\ufffd" in garbled or garbled != original
