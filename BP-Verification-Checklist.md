# Branch Protection v2 - Verification Checklist (master)

Repository: eugenebireta/biretos-automation
Default branch: master

Purpose:
- Make Branch Protection act as a governance barrier for Core changes.
- Prevent direct mutation of the truth source (master) without PR + CI.
- Ensure CI status check binding is correct and non-bypassable (including admins).

Non-goals:
- No workflow changes. This document only defines verification steps and proofs.

---

## A. CI Contract (Facts to Verify Locally)

Source: `.github/workflows/ci.yml`

- [ ] Workflow triggers include `pull_request` targeting `master`.
- [ ] Workflow triggers include `push` targeting `master`.
- [ ] CI job name is a static key `tests` under `jobs:` (no dynamic job naming).
- [ ] Required status check name planned for protection is exactly `tests` (must match the job key).

Evidence (local):
- Commit SHA used for this verification baseline: `882d651523476aecf4d8de532b87043ac11b3c91`

Notes:
- GitHub may render the check as `CI / tests` in the UI, but the required-check binding must refer to
  the exact check name GitHub exposes for this workflow. The job key is the canonical source of truth.

---

## B. Branch Protection v2 - Final Parameters (Target State)

Target branch pattern:
- `master`

Pull Request gate:
- [ ] Require a pull request before merging: ON
- [ ] Required approvals: 0

CI gate:
- [ ] Require status checks to pass before merging: ON
- [ ] Required status check: `tests`
- [ ] Require branches to be up to date before merging: ON

Admin enforcement:
- [ ] Include administrators: ON

Immutability:
- [ ] Allow force pushes: OFF
- [ ] Allow deletions: OFF

Optional (must remain as specified for v2):
- [ ] Require conversation resolution: OFF
- [ ] Require linear history: OFF
- [ ] Restrict who can push: OFF (solo; revisit when 2+ contributors)
- [ ] Require signed commits: OFF

---

## C. Merge Strategy Policy (Repository Settings - Target State)

- [ ] Merge commits: ALLOWED
- [ ] Squash merges: ALLOWED
- [ ] Rebase merges: DISABLED

Rationale (record only):
- Merge commits preserve an explicit governance boundary (merge point) in git history.
- Rebase merge is disallowed to avoid rewriting commit SHAs between PR validation and master history.

---

## D. Verification Test Matrix (5 Tests)

All tests must be executed by the repo owner/admin to confirm "Include administrators: ON" is effective.

### Test 1 (Positive): Green CI + Merge
- [ ] Create PR to `master`.
- [ ] Observe status check `tests` is GREEN.
- [ ] Observe PR is up to date with base branch.
- [ ] Merge succeeds.

Artifacts:
- PR URL
- Screenshot: Checks tab showing `tests` passed
- Merge commit SHA on `master`

### Test 2 (Negative): Merge with Red CI
- [ ] Create PR to `master` with a deliberate failing test.
- [ ] Observe status check `tests` is RED.
- [ ] Verify merge is blocked (button disabled / blocked message).

Artifacts:
- Screenshot: merge blocked due to required check
- CI logs link showing failing pytest output

### Test 3 (Negative): Merge without PR (Direct Push)
- [ ] Attempt direct push to `master` from local git.
- [ ] Verify push is rejected due to branch protection.

Artifacts:
- Terminal output (push rejection message)

### Test 4 (Negative): Force Push
- [ ] Attempt `git push --force` to `master`.
- [ ] Verify force push is rejected due to protection.

Artifacts:
- Terminal output (force push rejection message)

### Test 5 (Negative): Stale Branch Merge (Up-to-date Enforcement)
- [ ] Create PR branch A and merge it to `master` (so base advances).
- [ ] Create PR branch B from an older base (stale).
- [ ] Even with GREEN `tests`, verify merge is blocked until branch is updated.

Artifacts:
- Screenshot: PR marked out-of-date / update required

---

## E. Definition of Done (DoD) - Observable Proofs

Branch protection is considered DONE when:
- [ ] A protection rule exists for `master` with all parameters in section B.
- [ ] Required status check binding is correct and references `tests`.
- [ ] Include administrators is ON and verified (admin cannot merge on red CI).
- [ ] Test 1 passes (green CI allows merge).
- [ ] Tests 2-5 pass (all negative cases are blocked as expected).
- [ ] Merge strategy policy matches section C.

Proof bundle (store as links/screenshots in the PR description or an internal log):
- [ ] Screenshot: Branch protection rule for `master` (showing include admins + up-to-date + required check).
- [ ] Screenshot: Merge strategy settings (merge/squash enabled, rebase disabled).
- [ ] Links: PRs used for each test.
- [ ] Terminal outputs for direct push and force push rejections.

---

## F. Rollback Summary (If Misconfiguration Blocks All Work)

Goal: restore ability to merge safely, then re-enable the barrier.

Common failure modes:
- Required check name mismatch (PR waits forever for a check that never reports).
- GitHub Actions outage or permission issue preventing checks from running.

Rollback options (in order):
- [ ] Temporarily remove the required status check from the rule, merge the critical PR, re-add it.
- [ ] Temporarily disable "Require branches to be up to date" if it creates an unexpected deadlock.
- [ ] Emergency-only: temporarily disable "Include administrators", perform the merge, then re-enable it.
- [ ] Nuclear: delete the rule entirely, unblock, then recreate the rule from section B.

Audit note:
- GitHub records settings changes in the repository audit log. Capture the audit log entry links as part of the incident record.

