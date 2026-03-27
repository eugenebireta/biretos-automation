"""Tests for the external judge runner."""
from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path


_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from judge_runner import run_judge_flow


def _write(path: Path, content: str) -> Path:
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
    return path


class DummyResponse:
    def __init__(self, output_text: str = "", output_parsed=None, usage=None, request_id: str = "req_test"):
        self.output_text = output_text
        self.output_parsed = output_parsed
        self.usage = usage or {"input_tokens": 100, "output_tokens": 50}
        self._request_id = request_id


class DummyClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.last_kwargs = None
        self.responses = self

    def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if not self._responses:
            raise AssertionError("unexpected judge call")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _patch_repo_helpers(monkeypatch):
    monkeypatch.setattr("judge_runner._resolve_sha", lambda explicit_sha=None: explicit_sha or "abc123def456")
    monkeypatch.setattr("judge_runner._resolve_branch", lambda: "feat/test")
    monkeypatch.setattr("judge_runner._changed_files_for_sha", lambda sha: ["scripts/judge_runner.py", "config/judge_verdict_schema.json"])
    monkeypatch.setattr(
        "judge_runner._build_continuity_preview",
        lambda generated_on: (
            textwrap.dedent(
                """
                # CONTINUITY_INDEX

                ## Active Blockers

                - ID: `BL-001`
                  Claim: `ROADMAP` drift remains visible.
                """
            ).strip(),
            "No diff between current continuity artifact and preview.",
        ),
    )


def test_incomplete_pack_fails_closed_before_api(monkeypatch, tmp_path):
    _patch_repo_helpers(monkeypatch)
    test_log = _write(tmp_path / "pytest.txt", "")
    outdir = tmp_path / "judge_out"
    client = DummyClient([])

    result = run_judge_flow(
        risk="SEMI",
        scope="R1 batch",
        test_log_path=test_log,
        deferred_text="",
        outdir=outdir,
        generated_on="2026-03-27",
        client=client,
    )

    verdict = result["verdict"]
    assert verdict["verdict"] == "FIX"
    assert verdict["merge"] == "NO"
    assert verdict["manual_external_judge_required"] is True
    assert client.calls == 0
    assert "Evidence pack completeness check failed" in result["human_verdict_path"].read_text(encoding="utf-8")


def test_api_failure_blocks_and_requires_manual_external_judge(monkeypatch, tmp_path):
    _patch_repo_helpers(monkeypatch)
    test_log = _write(tmp_path / "pytest.txt", "======================= 12 passed in 0.20s =======================")
    outdir = tmp_path / "judge_out"
    client = DummyClient([RuntimeError("judge api down")])

    result = run_judge_flow(
        risk="SEMI",
        scope="R1 batch",
        test_log_path=test_log,
        deferred_text="- None declared.",
        outdir=outdir,
        generated_on="2026-03-27",
        client=client,
    )

    verdict = result["verdict"]
    assert verdict["verdict"] == "BLOCK"
    assert verdict["merge"] == "NO"
    assert verdict["manual_external_judge_required"] is True
    raw = json.loads(result["judge_raw_response_path"].read_text(encoding="utf-8"))
    assert raw["call_state"] == "failed"


def test_setup_failure_blocks_instead_of_crashing(monkeypatch, tmp_path):
    _patch_repo_helpers(monkeypatch)
    monkeypatch.setattr("judge_runner.call_external_judge", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("OPENAI_API_KEY is not configured")))
    test_log = _write(tmp_path / "pytest.txt", "======================= 12 passed in 0.20s =======================")
    outdir = tmp_path / "judge_out"

    result = run_judge_flow(
        risk="SEMI",
        scope="R1 batch",
        test_log_path=test_log,
        deferred_text="- None declared.",
        outdir=outdir,
        generated_on="2026-03-27",
        client=None,
    )

    assert result["verdict"]["verdict"] == "BLOCK"
    assert result["verdict"]["merge"] == "NO"
    assert result["verdict"]["manual_external_judge_required"] is True
    raw = json.loads(result["judge_raw_response_path"].read_text(encoding="utf-8"))
    assert raw["call_state"] == "failed"
    assert "OPENAI_API_KEY is not configured" in raw["error"]


def test_timeout_error_blocks_and_requires_manual_external_judge(monkeypatch, tmp_path):
    _patch_repo_helpers(monkeypatch)
    test_log = _write(tmp_path / "pytest.txt", "======================= 12 passed in 0.20s =======================")
    outdir = tmp_path / "judge_out"
    client = DummyClient([TimeoutError("judge timed out after 60s")])

    result = run_judge_flow(
        risk="SEMI",
        scope="R1 batch",
        test_log_path=test_log,
        deferred_text="- None declared.",
        outdir=outdir,
        generated_on="2026-03-27",
        client=client,
    )

    assert result["verdict"]["verdict"] == "BLOCK"
    assert result["verdict"]["merge"] == "NO"
    raw = json.loads(result["judge_raw_response_path"].read_text(encoding="utf-8"))
    assert raw["call_state"] == "failed"
    assert "timed out" in raw["error"]


def test_invalid_api_key_error_redacts_masked_key_tail(monkeypatch, tmp_path):
    _patch_repo_helpers(monkeypatch)
    test_log = _write(tmp_path / "pytest.txt", "======================= 12 passed in 0.20s =======================")
    outdir = tmp_path / "judge_out"
    client = DummyClient(
        [
            RuntimeError(
                "Error code: 401 - {'error': {'message': 'Incorrect API key provided: "
                "sk-proj-********************************TEST. You can find your API key at "
                "https://platform.openai.com/account/api-keys.', 'type': 'invalid_request_error'}}"
            )
        ]
    )

    result = run_judge_flow(
        risk="SEMI",
        scope="R1 batch",
        test_log_path=test_log,
        deferred_text="- None declared.",
        outdir=outdir,
        generated_on="2026-03-27",
        client=client,
    )

    raw = result["judge_raw_response_path"].read_text(encoding="utf-8")
    verdict = result["judge_verdict_path"].read_text(encoding="utf-8")
    assert "sk-proj-" not in raw
    assert "TEST" not in raw
    assert "sk-proj-" not in verdict
    assert "TEST" not in verdict
    assert "[REDACTED]" in raw


def test_malformed_judge_output_blocks(monkeypatch, tmp_path):
    _patch_repo_helpers(monkeypatch)
    test_log = _write(tmp_path / "pytest.txt", "PYTEST_EXIT_CODE=0")
    outdir = tmp_path / "judge_out"
    client = DummyClient([DummyResponse(output_text='{"verdict":"APPROVE"}')])

    result = run_judge_flow(
        risk="SEMI",
        scope="R1 batch",
        test_log_path=test_log,
        deferred_text="- None declared.",
        outdir=outdir,
        generated_on="2026-03-27",
        client=client,
    )

    assert result["verdict"]["verdict"] == "BLOCK"
    assert result["verdict"]["merge"] == "NO"
    assert result["verdict"]["manual_external_judge_required"] is True


def test_truncated_json_response_blocks(monkeypatch, tmp_path):
    _patch_repo_helpers(monkeypatch)
    test_log = _write(tmp_path / "pytest.txt", "PYTEST_EXIT_CODE=0")
    outdir = tmp_path / "judge_out"
    client = DummyClient([DummyResponse(output_text='{"schema_version":"judge_verdict_schema_v1",')])

    result = run_judge_flow(
        risk="SEMI",
        scope="R1 batch",
        test_log_path=test_log,
        deferred_text="- None declared.",
        outdir=outdir,
        generated_on="2026-03-27",
        client=client,
    )

    assert result["verdict"]["verdict"] == "BLOCK"
    assert result["verdict"]["merge"] == "NO"
    assert result["verdict"]["manual_external_judge_required"] is True


def test_schema_mismatch_blocks_on_unexpected_fields(monkeypatch, tmp_path):
    _patch_repo_helpers(monkeypatch)
    test_log = _write(tmp_path / "pytest.txt", "======================= 12 passed in 0.20s =======================")
    outdir = tmp_path / "judge_out"
    verdict_payload = {
        "schema_version": "judge_verdict_schema_v1",
        "verdict": "APPROVE",
        "scope_summary": "R1 batch changes limited to declared files.",
        "checks_summary": "Changed files, tests, continuity artifact, and blockers were reviewed.",
        "main_risk": "Residual roadmap drift remains outside this batch.",
        "merge": "YES",
        "required_fixes": [],
        "manual_external_judge_required": False,
        "evidence_pack_complete": True,
        "unresolved_critical_risk": False,
        "rationale_short": "Evidence is sufficient for SEMI approval.",
        "extra_field": "should fail schema validation",
    }
    client = DummyClient([DummyResponse(output_parsed=verdict_payload)])

    result = run_judge_flow(
        risk="SEMI",
        scope="R1 batch",
        test_log_path=test_log,
        deferred_text="- None declared.",
        outdir=outdir,
        generated_on="2026-03-27",
        client=client,
    )

    assert result["verdict"]["verdict"] == "BLOCK"
    assert result["verdict"]["merge"] == "NO"
    assert result["verdict"]["manual_external_judge_required"] is True


def test_secret_hygiene_redacts_pack_request_and_verdict_artifacts(monkeypatch, tmp_path):
    _patch_repo_helpers(monkeypatch)
    test_log = _write(tmp_path / "pytest.txt", "======================= 12 passed in 0.20s =======================")
    outdir = tmp_path / "judge_out"
    verdict_payload = {
        "schema_version": "judge_verdict_schema_v1",
        "verdict": "FIX",
        "scope_summary": 'Observed "Authorization: Bearer super-secret-token" in executor notes.',
        "checks_summary": 'Reviewed x-api-key: raw-secret-value and https://user:pa55@example.com/path?q=1.',
        "main_risk": 'OPENAI_API_KEY=sk-secret-1234567890 should never appear in artifacts.',
        "merge": "NO",
        "required_fixes": ['Remove password="top-secret" from shared notes.'],
        "manual_external_judge_required": False,
        "evidence_pack_complete": True,
        "unresolved_critical_risk": False,
        "rationale_short": "Secrets were detected in operator-supplied text.",
    }
    client = DummyClient([DummyResponse(output_parsed=verdict_payload)])

    result = run_judge_flow(
        risk="SEMI",
        scope='R1 batch with Authorization: Bearer super-secret-token and OPENAI_API_KEY=sk-secret-1234567890',
        test_log_path=test_log,
        deferred_text='- Deferred because password="top-secret" and https://user:pa55@example.com/path?token=abc123 were found.',
        outdir=outdir,
        generated_on="2026-03-27",
        client=client,
    )

    evidence_pack = result["evidence_pack_path"].read_text(encoding="utf-8")
    raw = result["judge_raw_response_path"].read_text(encoding="utf-8")
    human = result["human_verdict_path"].read_text(encoding="utf-8")
    outbound_input = client.last_kwargs["input"]

    for text in (evidence_pack, raw, human, outbound_input):
        assert "super-secret-token" not in text
        assert "sk-secret-1234567890" not in text
        assert "top-secret" not in text
        assert "pa55@" not in text
        assert "[REDACTED]" in text


def test_valid_judge_output_renders_short_human_verdict(monkeypatch, tmp_path):
    _patch_repo_helpers(monkeypatch)
    test_log = _write(tmp_path / "pytest.txt", "======================= 12 passed in 0.20s =======================")
    outdir = tmp_path / "judge_out"
    verdict_payload = {
        "schema_version": "judge_verdict_schema_v1",
        "verdict": "APPROVE",
        "scope_summary": "R1 batch changes limited to declared files.",
        "checks_summary": "Changed files, tests, continuity artifact, and blockers were reviewed.",
        "main_risk": "Residual roadmap drift remains outside this batch.",
        "merge": "YES",
        "required_fixes": [],
        "manual_external_judge_required": False,
        "evidence_pack_complete": True,
        "unresolved_critical_risk": False,
        "rationale_short": "Evidence is sufficient for SEMI approval.",
    }
    client = DummyClient([DummyResponse(output_parsed=verdict_payload)])

    result = run_judge_flow(
        risk="SEMI",
        scope="R1 batch",
        test_log_path=test_log,
        deferred_text="- None declared.",
        outdir=outdir,
        generated_on="2026-03-27",
        client=client,
    )

    human = result["human_verdict_path"].read_text(encoding="utf-8").strip().splitlines()
    assert result["verdict"]["verdict"] == "APPROVE"
    assert result["verdict"]["merge"] == "YES"
    assert len(human) == 5
    assert human[0] == "VERDICT: APPROVE"


def test_judge_runner_writes_shadow_corpus_records(monkeypatch, tmp_path):
    _patch_repo_helpers(monkeypatch)
    test_log = _write(tmp_path / "pytest.txt", "======================= 12 passed in 0.20s =======================")
    outdir = tmp_path / "judge_out"
    shadow_log_dir = tmp_path / "shadow_log"
    verdict_payload = {
        "schema_version": "judge_verdict_schema_v1",
        "verdict": "APPROVE",
        "scope_summary": "R1 batch changes limited to declared files.",
        "checks_summary": "Changed files, tests, continuity artifact, and blockers were reviewed.",
        "main_risk": "Residual roadmap drift remains outside this batch.",
        "merge": "YES",
        "required_fixes": [],
        "manual_external_judge_required": False,
        "evidence_pack_complete": True,
        "unresolved_critical_risk": False,
        "rationale_short": "Evidence is sufficient for SEMI approval.",
    }
    client = DummyClient([DummyResponse(output_parsed=verdict_payload)])

    result = run_judge_flow(
        risk="SEMI",
        scope="R1 batch",
        test_log_path=test_log,
        deferred_text="- None declared.",
        outdir=outdir,
        generated_on="2026-03-27",
        client=client,
        shadow_log_dir=shadow_log_dir,
    )

    assert result["shadow_corpus_write_error"] is None
    assert result["shadow_corpus_records_written"] == 5
    assert result["shadow_corpus_status_write_error"] is None
    corpus_path = result["shadow_corpus_path"]
    assert corpus_path == shadow_log_dir / "corpus_v0" / "trajectory_records_2026-03.jsonl"
    status_path = result["shadow_corpus_status_path"]
    assert status_path == outdir / "shadow_corpus_status.json"
    status_payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert status_payload["status"] == "written"
    assert status_payload["records_written"] == 5
    assert status_payload["error"] is None
    assert status_payload["reason"] == "corpus_write_succeeded"
    records = [
        json.loads(line)
        for line in corpus_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [record["record_kind"] for record in records] == [
        "continuity_artifact",
        "evidence_pack",
        "judge_verdict",
        "human_verdict",
        "final_outcome",
    ]
    trajectory_ids = {record["trajectory_id"] for record in records}
    assert len(trajectory_ids) == 1
    judge_record = next(record for record in records if record["record_kind"] == "judge_verdict")
    final_record = next(record for record in records if record["record_kind"] == "final_outcome")
    assert judge_record["provider"] == "openai"
    assert judge_record["model"] == "gpt-5.4"
    assert judge_record["verdict_ref"].endswith("judge_verdict.json")
    assert final_record["final_outcome_label"] == "needs_human_review"
    assert final_record["authoritative_label_source"] == "none"


def test_execution_status_artifact_adds_status_event_to_shadow_corpus(monkeypatch, tmp_path):
    _patch_repo_helpers(monkeypatch)
    test_log = _write(tmp_path / "pytest.txt", "PYTEST_EXIT_CODE=0")
    status_path = tmp_path / "execution_status.json"
    status_path.write_text(
        json.dumps(
            {
                "status": "FAILED_TIMEOUT",
                "attempt_count": 2,
                "retry_count": 1,
                "last_heartbeat_ts": "2026-03-27T10:00:00Z",
                "stdout_log_ref": "logs/stdout.log",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    outdir = tmp_path / "judge_out"
    shadow_log_dir = tmp_path / "shadow_log"
    verdict_payload = {
        "schema_version": "judge_verdict_schema_v1",
        "verdict": "FIX",
        "scope_summary": "R1 batch changes limited to declared files.",
        "checks_summary": "Execution status and tests were reviewed.",
        "main_risk": "Timeout remains unresolved.",
        "merge": "NO",
        "required_fixes": ["Investigate timeout root cause."],
        "manual_external_judge_required": False,
        "evidence_pack_complete": True,
        "unresolved_critical_risk": False,
        "rationale_short": "The run timed out and needs follow-up.",
    }
    client = DummyClient([DummyResponse(output_parsed=verdict_payload)])

    result = run_judge_flow(
        risk="SEMI",
        scope="R1 batch",
        test_log_path=test_log,
        deferred_text="- None declared.",
        outdir=outdir,
        generated_on="2026-03-27",
        client=client,
        execution_status_path=status_path,
        shadow_log_dir=shadow_log_dir,
    )

    assert result["shadow_corpus_write_error"] is None
    assert result["shadow_corpus_status_write_error"] is None
    records = [
        json.loads(line)
        for line in result["shadow_corpus_path"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    status_record = next(record for record in records if record["record_kind"] == "status_event")
    evidence_record = next(record for record in records if record["record_kind"] == "evidence_pack")
    assert status_record["run_status"] == "FAILED_TIMEOUT"
    assert status_record["retry_count"] == 1
    assert status_record["attempt_index"] == 2
    assert status_record["output_ref"] == status_path.resolve().as_posix()
    assert evidence_record["parent_id"] == status_record["record_id"]


def test_shadow_corpus_failure_writes_failed_status_artifact(monkeypatch, tmp_path):
    _patch_repo_helpers(monkeypatch)
    test_log = _write(tmp_path / "pytest.txt", "PYTEST_EXIT_CODE=0")
    outdir = tmp_path / "judge_out"
    shadow_log_dir = tmp_path / "shadow_log"
    verdict_payload = {
        "schema_version": "judge_verdict_schema_v1",
        "verdict": "APPROVE",
        "scope_summary": "R1 batch changes limited to declared files.",
        "checks_summary": "Changed files, tests, continuity artifact, and blockers were reviewed.",
        "main_risk": "Residual roadmap drift remains outside this batch.",
        "merge": "YES",
        "required_fixes": [],
        "manual_external_judge_required": False,
        "evidence_pack_complete": True,
        "unresolved_critical_risk": False,
        "rationale_short": "Evidence is sufficient for SEMI approval.",
    }
    client = DummyClient([DummyResponse(output_parsed=verdict_payload)])

    def _boom(**kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("judge_runner.write_judge_shadow_corpus_records", _boom)

    result = run_judge_flow(
        risk="SEMI",
        scope="R1 batch",
        test_log_path=test_log,
        deferred_text="- None declared.",
        outdir=outdir,
        generated_on="2026-03-27",
        client=client,
        shadow_log_dir=shadow_log_dir,
    )

    assert result["shadow_corpus_path"] is None
    assert result["shadow_corpus_records_written"] == 0
    assert result["shadow_corpus_write_error"] == "disk full"
    assert result["shadow_corpus_status_write_error"] is None
    status_path = result["shadow_corpus_status_path"]
    assert status_path == outdir / "shadow_corpus_status.json"
    status_payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert status_payload["status"] == "failed"
    assert status_payload["records_written"] == 0
    assert status_payload["error"] == "disk full"
    assert status_payload["reason"] == "corpus_write_failed"
