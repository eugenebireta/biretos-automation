#!/usr/bin/env bash
# apply_branch_protection.sh — enforce branch protection on master
# Requires: gh cli authenticated with a token that has administration:write scope.
# The default GITHUB_TOKEN does NOT have this — use a PAT stored as BRANCH_PROTECTION_TOKEN.
set -euo pipefail

REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is not set}"
BRANCH="master"

echo "Applying branch protection to ${REPO}@${BRANCH}..."

gh api \
  "repos/${REPO}/branches/${BRANCH}/protection" \
  -X PUT \
  --input - <<'PAYLOAD'
{
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true
  },
  "required_status_checks": {
    "strict": true,
    "contexts": ["tests"]
  },
  "enforce_admins": true,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
PAYLOAD

echo "Branch protection applied successfully to ${REPO}@${BRANCH}."
