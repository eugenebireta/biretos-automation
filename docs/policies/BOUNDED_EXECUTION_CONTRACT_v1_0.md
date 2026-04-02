# Bounded Execution Contract v1.0

Status: DRAFT-MVP  
Date: 2026-03-27

## 1. Purpose

Define a minimal execution contract for long-running jobs so the owner does not
have to babysit the console or manually detect hangs.

This contract is separate from:

- `judge_runner.py`
- merge gates
- background daemon automation
- full multi-agent orchestration

## 2. Core Principle

Long-running jobs must run inside bounded execution, not as open-ended terminal
sessions with implicit human supervision.

The owner should not be the watchdog.

## 3. Required Controls

Every bounded execution wrapper must support:

- hard timeout
- idle timeout or heartbeat timeout
- process-tree kill on timeout / stall
- bounded retry count
- machine-readable status artifact
- stdout / stderr log references
- explicit exit classification

## 4. Status Model

Allowed statuses:

- `STARTED`
- `RUNNING`
- `COMPLETED`
- `FAILED_EXIT`
- `FAILED_TIMEOUT`
- `FAILED_IDLE`
- `RETRYING`
- `ABORTED_MAX_RETRIES`

No custom status names without explicit contract update.

## 5. Hard Timeout Rule

Every long-running job must have a hard wall-clock timeout.

If the timeout is exceeded:

- kill the process tree
- classify the run as `FAILED_TIMEOUT`
- write a status artifact
- do not silently continue

## 6. Idle / Heartbeat Rule

Preferred mode:

- the child job emits explicit heartbeat or progress signals

Fallback mode:

- the wrapper watches stdout/stderr updates
- and/or checkpoint/state artifact freshness

If no heartbeat or observable progress occurs past the idle threshold:

- kill the process tree
- classify the run as `FAILED_IDLE`

## 7. Retry Rule

Retries must be bounded.

Suggested defaults:

- `0-1` retry for risky jobs
- `1-2` retries for safe read-only jobs

Infinite retry is forbidden.

If retry budget is exhausted:

- classify as `ABORTED_MAX_RETRIES`
- do not ask the owner to manually keep retrying

## 8. Side-Effect Safety Rule

If a job can create side effects, retry is allowed only when at least one is
true:

- the job is idempotent by contract
- the job is checkpoint/restart-safe
- duplicate side effects are explicitly prevented elsewhere

Otherwise:

- watchdog timeout may kill the run
- but automatic retry must stay disabled

## 9. Required Status Artifact

Each supervised run must write a machine-readable status artifact containing at
least:

- `status`
- `started_at`
- `finished_at` or `last_heartbeat_ts`
- `attempt_count`
- `retry_count`
- `command`
- `stdout_log_ref`
- `stderr_log_ref`
- `exit_code`
- `failure_reason`

Optional:

- `checkpoint_ref`
- `heartbeat_interval_sec`
- `idle_timeout_sec`
- `hard_timeout_sec`

## 10. Required Log Artifacts

The wrapper must preserve references to:

- stdout log
- stderr log

The owner does not need to read them directly, but they must exist for
evidence-pack and judge review.

## 11. Judge Integration Rule

Bounded execution status is not just operational noise.

When a job is reviewed by an external judge, the evidence pack should include:

- execution outcome summary
- timeout / heartbeat / retry status
- stall or retry exhaustion if it happened

This prevents flaky behavior from being hidden behind green diffs.

## 12. User Interface Rule

If a job times out, stalls, or exhausts retries:

the owner should not read logs to diagnose it first.

Instead, the human-facing verdict should reduce it to:

- `FIX` or `BLOCK`
- main risk = timeout / stall / retry exhaustion
- merge = `NO`

## 13. Non-Goals

This contract does not yet require:

- Windows Task Scheduler
- git hooks
- background daemon supervision
- automatic retries for all jobs
- self-healing black-box automation

## 14. MVP Intent

The immediate goal is to make hangs explicit, bounded, and reviewable.

The goal is not to create a hidden autonomous process manager.
