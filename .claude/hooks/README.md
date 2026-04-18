# .claude/hooks — project-level Claude Code hooks

Defensive hooks for biretos-automation. Derived from AI-Audit Tier 1 + Deep Research Tier 4. See [_scratchpad/ai_audits/2026-04-18_claude-code-setup-optimization.md](../../_scratchpad/ai_audits/2026-04-18_claude-code-setup-optimization.md).

## Files

| File | Purpose | Status |
|------|---------|--------|
| `frozen_guard.py` | PreToolUse(Write\|MultiEdit\|NotebookEdit) — blocks writes to `PROJECT_DNA.md §3` files | active once wired in `settings.json` |
| `bash_guard.py` | PreToolUse(Bash) — 21-pattern destructive-command detection | **audit-only mode** (exit 0, log-only) |
| `refresh_frozen_cache.py` | Pre-commit companion — validates DNA §3 parses on commit | hook-script (not a Claude Code hook) |
| `_reference/frozen_guard.sh.linux-optimized` | Bash+awk rewrite (Deep Research Q5 pattern) — reference only | 4× slower than Python on Windows Git Bash |
| `_log/*.jsonl` | Runtime log (JSONL, OTel-compatible field names) | gitignored |
| `_cache/frozen_list.json` | SHA-256–keyed cache of DNA §3 list | gitignored |

## Facts that shape the design (Deep Research 2026-04-18)

- **Hooks run in parallel, not sequentially.** Cannot assume ordering between our hooks and claude-mem's. Only coordination primitive: precedence `deny > defer > ask > allow`.
- **`exit 1` is non-blocking error.** Tool call proceeds. Only `exit 2` blocks.
- **Default timeout 600s is fail-OPEN.** Explicit `exit 2` is the only way to enforce fail-closed.
- **`$CLAUDE_TOOL_ARGS` does not exist** (issue #9567). Only stdin JSON.
- **claude-mem v12.0.0+ extends File Read Gate to Edit.** We drop `Edit` from `frozen_guard.py` matcher to avoid timeline-injection overlap.
- **Python beats Bash on Windows Git Bash** for hook cold-start (~70ms vs ~300ms — MSYS2 process spawning overhead).
- **`permissions.deny` has silent-bypass bugs** (issues #6699/#8961/#27040). Hook-level enforcement is mandatory, not optional.

## Wiring hooks in `.claude/settings.json`

`frozen_guard.py` (active enforcement — exit 2 blocks on match):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python ${CLAUDE_PROJECT_DIR}/.claude/hooks/frozen_guard.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

**Do not** include `Edit` in the matcher — claude-mem v12.0.0+ gates it.

`bash_guard.py` (audit-only — exit 0 always):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python ${CLAUDE_PROJECT_DIR}/.claude/hooks/bash_guard.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

## Bypass

| Hook | Env var | Effect | Audit trail |
|------|---------|--------|-------------|
| `frozen_guard.py` | `FROZEN_GUARD_BYPASS=1` | Allow write to frozen file | `decision: "bypass_granted"` in `_log/frozen_guard.jsonl` |
| `bash_guard.py` | `AUDIT_VERBOSE=1` | Print matched rules to stderr | N/A — audit mode never blocks |

Never set `FROZEN_GUARD_BYPASS=1` globally. Use per-command: `FROZEN_GUARD_BYPASS=1 <cmd>`.

## Rollout for `bash_guard.py` (audit-only → ask → block)

**Stage A (now):** audit-only. Exit 0 always. Collect `_log/bash_guard.jsonl`.

**Stage B (1-2 weeks):** review FP rate per rule:

```bash
jq -r 'select(.attributes.matched_rules | length > 0)
       | .attributes.matched_rules[]
       | "\(.rule_id)\t\(.recommended_action)"' \
  .claude/hooks/_log/bash_guard.jsonl | sort | uniq -c | sort -rn
```

**Stage C:** promote individual rules:

- → `ask` when: ≥100 matches, FP ≤ 1%
- → `block` when: ≥1000 matches, FP ≤ 0.5%
- Per Deep Research Q3: n ≈ 1520 events for 1% FP estimate ±0.5pp at 95% CI
- One rule at a time; each promotion = separate PR with log evidence

## Testing without wiring

```bash
# frozen_guard — expect BLOCK (exit 2)
echo '{"tool_name":"Write","tool_input":{"file_path":".cursor/windmill-core-v1/maintenance_sweeper.py"}}' \
  | python .claude/hooks/frozen_guard.py
echo "exit=$?"

# bash_guard — expect exit 0, entry in log
echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/test"}}' \
  | python .claude/hooks/bash_guard.py
tail -1 .claude/hooks/_log/bash_guard.jsonl | python -m json.tool
```

## Windows quirks

1. **Git Bash process spawning is slow** (~50ms per subprocess). Keep hooks Python-only.
2. **claude-mem v12.1.3 spawns visible cmd.exe windows.** Upgrade to ≥v12.1.4 (commit `3d92684`).
3. **Windows `D:/…` vs Git Bash `/d/…`** paths both normalize to repo-relative via `_normalize_target`.

## Benchmark

Windows Git Bash, warm interpreter cache:

| Impl | Cold | Hot | Notes |
|------|------|-----|-------|
| `frozen_guard.py` | ~70ms | ~70ms | Single Python process |
| `frozen_guard.sh` (reference) | ~300ms | ~300ms | MSYS2 fork overhead per `sha256sum`/`awk`/`grep` |

Expected Linux: Python ~200-400ms, Bash ~6-11ms (conclusion inverts — use Bash reference on Linux CI).

## Hooks are one layer, not the only layer

Authoritative sources remain:
- `docs/PROJECT_DNA.md` §3 (frozen files — policy)
- `.claude/settings.json` permissions (file access — policy)
- `.gitignore` (VCS-level — policy)
- Owner review (human judgment — final authority)

Hooks mechanize the default path; owners override via bypass env vars with audit trail.
