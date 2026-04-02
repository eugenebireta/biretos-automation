# Proposal: Branch Protection на master (Stage 2.2)

## Summary

Configure branch protection rules on `master` via GitHub CLI / API.
**No live changes applied** — this proposal defines the configuration to be applied
by the owner after review. Output: runnable `gh` CLI command + documentation.

---

## Configuration Script

```bash
#!/bin/bash
# scripts/setup_branch_protection.sh
# Apply AFTER owner review of this proposal.
# Requires: gh CLI authenticated with repo admin rights.

OWNER="eugenebireta"
REPO="biretos-automation"
BRANCH="master"

gh api \
  repos/${OWNER}/${REPO}/branches/${BRANCH}/protection \
  --method PUT \
  --header "Accept: application/vnd.github+json" \
  -f 'required_status_checks[strict]=true' \
  -f 'required_status_checks[contexts][]=test' \
  -f 'enforce_admins=false' \
  -f 'required_pull_request_reviews[dismiss_stale_reviews]=true' \
  -f 'required_pull_request_reviews[required_approving_review_count]=1' \
  -f 'required_pull_request_reviews[require_code_owner_reviews]=false' \
  -f 'restrictions=null' \
  -f 'allow_force_pushes=false' \
  -f 'allow_deletions=false'

echo "Branch protection applied to ${BRANCH}"
```

---

## Rules Applied

| Rule | Value | Reason |
|------|-------|--------|
| Required status checks | `test` (CI job name) | Block merge if pytest fails |
| Strict status checks | true | Branch must be up-to-date with master before merge |
| Required PR reviews | 1 | At least one human approval before merge |
| Dismiss stale reviews | true | Re-review required after new commits |
| Direct push to master | BLOCKED | All changes via PR only |
| Force push | BLOCKED | Protect commit history |
| Branch deletion | BLOCKED | Prevent accidental delete |
| Enforce for admins | false | Owner can bypass if emergency |

---

## CI Status Check Name

The current CI workflow (`.github/workflows/`) runs under job name `test`.
If the actual job name differs, update `required_status_checks[contexts][]` accordingly.

To verify current CI job name:
```bash
gh run list --limit 5 --json name,status,conclusion
```

---

## Verification After Apply

```bash
# Verify protection is active:
gh api repos/eugenebireta/biretos-automation/branches/master/protection \
  --jq '{required_pr: .required_pull_request_reviews.required_approving_review_count, required_ci: .required_status_checks.contexts}'

# Expected output:
# {
#   "required_pr": 1,
#   "required_ci": ["test"]
# }
```

---

## Risk Assessment

- **Mutation surface**: GitHub API settings only. No code changes.
- **Reversibility**: Fully reversible (`gh api ... --method DELETE`).
- **Side effects**: Existing open PRs may require re-approval if stale.
- **Admin bypass**: `enforce_admins=false` — owner can push directly in emergency.
