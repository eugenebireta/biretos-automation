# CORE Watchdog Rescue Plan

- Branch: `feat/core-governance-watchdog`
- Rescued commit: `5551aea`
- Current state: rescued CORE payload exists, but its base is stale relative to current `master`
- Constraint: do not rebase, merge, or cherry-pick this branch as part of Phase 0
- Required follow-up: handle this work in a separate CORE Strict Mode batch later
- Scope for later batch: re-verify the rescued diff on top of current `master`, review Tier-1 risk, and only then decide transfer strategy
