# JUDGE RUNNER

Purpose: let an external AI judge read the evidence pack while the user reads
only the short human verdict.

## Core Rule

- User reads only `human_verdict.md`.
- User does not read `evidence_pack.md`, raw test logs, or diff noise.
- Executor must not self-approve its own change.
- `judge_runner.py` is fail-closed.

## What `judge_runner.py` Does

- assembles `evidence_pack.md`
- includes current continuity preview as an artifact, not proof
- calls an external OpenAI judge via API
- redacts obvious secrets before sending or storing artifacts
- validates structured output
- writes:
  - `evidence_pack.md`
  - `judge_verdict.json`
  - `judge_raw_response.json`
  - `human_verdict.md`
  - `shadow_corpus_status.json`

## What It Does Not Do

- no merge
- no code edits
- no rerun tests
- no hooks or scheduler
- no background supervision
- no self-approval

## Default Output

Artifacts are written under:

`artifacts/judge/<timestamp>_<sha>/`

`shadow_corpus_status.json` reports whether the auxiliary teacher-student corpus
write succeeded or failed. This does not change the judge verdict, but it
prevents silent holes in the future corpus layer.

## Example

```powershell
python scripts/judge_runner.py `
  --risk SEMI `
  --scope "R1 Phase A batch: verifier hardening" `
  --test-log docs/_governance/pytest_output.txt `
  --deferred-text "- None declared by executor."
```

The command prints the path to `human_verdict.md`.

## Fail-Closed Cases

`APPROVE` is forbidden when:

- evidence pack is incomplete
- judge API is unavailable
- `OPENAI_API_KEY` is missing
- judge output is malformed
- structured output validation fails
- risk is `CORE`

In those cases the runner writes `FIX` or `BLOCK` and sets `MERGE: NO`.

## Secret Hygiene

- `evidence_pack.md`, `judge_raw_response.json`, and `human_verdict.md` are redacted before write.
- The runner redacts obvious auth headers, API keys, passwords, URL credentials, and secret-like query params.
- This is a safety net, not permission to pass raw secrets or raw payload dumps into `--scope` or deferred notes.
- If sensitive material is suspected, treat the verdict as non-trustworthy until the source artifact is cleaned.

## Live SEMI/R1 Checklist

- Use only for `SEMI` / `R1` batches. `CORE` stays manual external judge only.
- Make sure the test log is real and non-empty before the run.
- Keep `--scope` and deferred text short and free of raw payload dumps.
- Run the command once and read only `human_verdict.md`.
- If verdict is not `APPROVE`, or `MERGE: NO`, stop. Do not merge.
- If the judge call fails, times out, or returns malformed output, the runner must fail closed to `FIX` or `BLOCK`.

## User Interface

The only required user-facing file is:

- `human_verdict.md`

Format:

- `VERDICT: APPROVE | FIX | BLOCK`
- `SCOPE: ...`
- `CHECKS: ...`
- `MAIN RISK: ...`
- `MERGE: YES | NO`

If the user needs more than this file to make a decision, the judge flow is not
working as intended.
