## Deep Research Findings — Claude Code Setup Optimization

This report resolves the 7 open questions left after Tier 1 AI-Audit and proposes a revised rollout order. Each finding is citation-backed; where behaviour is undocumented or contested, it is flagged explicitly.

---

### Q1. Hook execution semantics

**Parallel, not sequential.** The official reference is unambiguous: *"All matching hooks run in parallel, and identical handlers are deduplicated automatically. Command hooks are deduplicated by command string, and HTTP hooks are deduplicated by URL."* Anthropic's own plugin-dev SKILL.md reinforces: *"Hooks don't see each other's output. Non-deterministic ordering. Design for independence."* Several community tutorials (felo.ai, datacamp) claim sequential execution — **they are wrong**. Trust the official docs.
Sources: https://code.claude.com/docs/en/hooks, https://github.com/anthropics/claude-code/blob/main/plugins/plugin-dev/skills/hook-development/SKILL.md, https://blog.vincentqiao.com/en/posts/claude-code-settings-hooks/

**No chain abort on exit 1.** Any non-zero exit other than 2 is a *non-blocking* error for almost every event. Claude Code shows a one-line `<hook> hook error` notice in the transcript, routes full stderr to the debug log, and **the tool call proceeds**. The only event where any non-zero code aborts is `WorktreeCreate`. Since hooks are parallel, a sibling's exit 1 cannot cancel others.

**Exit 1 vs exit 2 — the critical asymmetry:**

| | Exit 1 (non-blocking error) | Exit 2 (blocking) |
|---|---|---|
| Tool call in PreToolUse | **Proceeds** | **Blocked** |
| stderr routing | first line in transcript, full in debug log | **fed to Claude as error context** |
| Claude awareness | no | yes (model can react) |

Per-event exit-2 behaviour: `PreToolUse`=blocks, `UserPromptSubmit`=rejects+erases prompt, `Stop`=forces continuation, `PostToolUse`/`Notification`/`SessionStart`=stderr shown only (cannot actually block).
Source: https://code.claude.com/docs/en/hooks (Exit code output)

**Timeouts fail-open.** Default `command` timeout = **600 s** (live reference docs) — although Anthropic's SKILL.md still says 60 s (stale). On cancellation the handler becomes a non-blocking error; **the action proceeds**. There is no documented fail-closed-on-timeout mode. If you need fail-closed semantics, enforce with an explicit `exit 2` inside a wrapping timeout, never rely on Claude Code's built-in timeout.

**stdout/stderr routing.** On exit 0, stdout is parsed for JSON; for most events, raw stdout goes to the debug log only. `UserPromptSubmit` and `SessionStart` are the exceptions — their stdout is injected into Claude's context. There is **no persistent on-disk hook log**; debug output streams when you run `claude --debug`. Transcripts live at `~/.claude/projects/<project-hash>/<session>.jsonl` and every hook receives the path as `transcript_path`.

**No priority/order field exists** in either plugin `hooks.json` or `settings.json`. The documented handler fields are `type, command|url|prompt, if, timeout, statusMessage, once, async, asyncRewake, shell, headers, allowedEnvVars, model`. Ordering is impossible by design.

**Environment vs stdin.** The canonical delivery channel is **stdin JSON**, not env vars. Confirmed env vars: `CLAUDE_PROJECT_DIR`, `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA`, `CLAUDE_ENV_FILE`, `CLAUDE_CODE_REMOTE`. **`$CLAUDE_TOOL_ARGS` does not exist**; issue #9567 confirms `$CLAUDE_TOOL_*` variants are empty. Use stdin JSON — for Write: `tool_input.file_path`, `tool_input.content`; for Edit: `tool_input.file_path`, `tool_input.old_string`, `tool_input.new_string`, `tool_input.replace_all`; for Bash: `tool_input.command`, `tool_input.description`, `tool_input.timeout`, `tool_input.run_in_background`.
Source: https://github.com/anthropics/claude-code/issues/9567

**settings.json vs plugin hooks.json — format and merge.** Plugin `hooks/hooks.json` is wrapped: `{"description":"...","hooks":{"PreToolUse":[...]}}`. `settings.json` has `hooks` as a top-level key. Hook arrays from **every layer concatenate and all run** — no layer overrides another. The `/hooks` menu labels each with its source (User, Project, Local, Plugin, Session, Built-in). Scalar-settings precedence (Managed > Project > User > Local > Plugin defaults) applies only to non-array settings. When multiple PreToolUse hooks return conflicting `permissionDecision`, precedence is **`deny > defer > ask > allow`** — this is the single most important semantic fact for the frozen_guard design. Enterprise `allowManagedHooksOnly` can disable all non-managed hooks.

---

### Q2. Destructive Bash regex patterns

**Architecture recommendation:** pair regex with a cheap substring pre-filter (dcg reports 99%+ early-exit at <10μs) and, where precision matters, a tokenizer (shlex/tree-sitter-bash) to separate *executed code* from *quoted data*. Claude Code's internal `bashSecurity.ts` uses exactly this pattern — 23+ regex validators plus AST extraction. **No source publishes numerical FP/FN rates** — all claims are qualitative; dcg explicitly accepts FPs over FNs.

| # | Category | Regex pattern | Severity | Known FP | Action |
|---|---|---|---|---|---|
| 1 | FS root wipe | `\brm\s+(-[a-zA-Z]*[rR][a-zA-Z]*[fF][a-zA-Z]*\|--recursive\s+--force)\s+(--no-preserve-root\s+)?/(\s\|$)` | CRIT | `rm -rf /tmp/...` if `/` anchor sloppy | **block** |
| 2 | FS home wipe | `\brm\s+-[rRfF]+\s+(~\|\$HOME\|/home/[^/\s]+)(\s\|/\|$)` | CRIT | CI container cleanup | **block** |
| 3 | Disk overwrite | `\bdd\s+.*\bof=/dev/(sd[a-z]\|nvme\d\|hd[a-z]\|mmcblk)` | CRIT | `of=/dev/null`, `/dev/stdout` (exclude explicitly) | **block** |
| 4 | Format/wipe | `\b(mkfs(\.[a-z0-9]+)?\|wipefs\|shred\|blkdiscard)\b\s` | CRIT | `shred` of controlled tempfile | **block** |
| 5 | Redirect to block dev | `(^\|\s\|\|)\s*>\s*/dev/(sd[a-z]\|nvme\d\|hd[a-z])` | CRIT | none | **block** |
| 6 | Partitioning | `\b(fdisk\|parted\|sfdisk\|gdisk)\s+(?!-l\b)` | HIGH | `fdisk -l` (excluded via lookahead) | **block** |
| 7 | SQL drop/truncate | `\b(DROP\s+(TABLE\|DATABASE\|SCHEMA)\|TRUNCATE\s+TABLE)\b` (i-flag) | HIGH | SQL in string literal / migration | **block** |
| 8 | DELETE/UPDATE no WHERE | `(?is)\b(DELETE\s+FROM\|UPDATE\s+\S+\s+SET)\b(?!.*\bWHERE\b)` | HIGH | DELETE with LIMIT/JOIN | **ask** |
| 9 | docker compose down -v | `\bdocker[- ]compose\s+down\s+(-[a-zA-Z]*v\|--volumes)` | HIGH | CI test teardown | **ask** |
| 10 | docker force remove | `\bdocker\s+(rm\s+-[a-zA-Z]*f\|volume\s+rm\|system\s+prune\s+.*-a)` | HIGH | ephemeral test container | **ask** |
| 11 | k8s ns delete | `\bkubectl\s+delete\s+(ns\|namespace\|--all\|-n\s+\S+\s+--all)\b` | CRIT | none | **block** |
| 12 | systemctl stop critical | `\bsystemctl\s+(stop\|disable\|mask)\s+(ssh\|sshd\|networking\|firewalld)` | HIGH | provisioning scripts | **ask** |
| 13 | sudo rm | `\bsudo\s+(-[^\s]*\s+)?rm\b` | HIGH | legit root-owned /tmp file | **ask** |
| 14 | chmod 777 | `\bchmod\s+(-[Rr])?\s*(777\|a\+rwx)\b` | MED | shared demo dir | **ask** |
| 15 | curl \| sh | `\b(curl\|wget)\s+[^|]*\|\s*(sudo\s+)?(bash\|sh\|zsh\|ksh)\b` | CRIT | trusted-vendor installer | **block** |
| 16 | eval of curl | `\$\(\s*(curl\|wget)\b[^)]*\)\s*\|\s*(bash\|sh)` | CRIT | none | **block** |
| 17 | git force push | `\bgit\s+push\s+(--force(?![-a-z])\|-f(?=\s\|$))` | HIGH | `--force-with-lease` (lookahead excluded) | **block on protected branches** |
| 18 | git reset --hard | `\bgit\s+reset\s+(--hard\|--merge)\b` | HIGH | intentional after stash | **ask** |
| 19 | git clean -fdx | `\bgit\s+clean\s+-[a-z]*f[a-z]*d[a-z]*x?\b` | HIGH | deliberate workspace purge | **ask** |
| 20 | Fork bomb | `:\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:` | CRIT | none | **block** |
| 21 | Scope-aware sed/frozen | `\bsed\s+-i(?:\s+'[^']*'\|\s+"[^"]*")?\s+(?:\S*/)?(FROZEN_LIST)\b` (generated) | HIGH | sed -i on safe file — by construction | **block frozen only** |

**Scope-aware matching strategies:**
1. Extract-and-compare (used by Anthropic's own `bashSecurity.ts` and dcg) — after regex hit on `\bsed\s+-i\b`, tokenize with shlex / tree-sitter-bash and test each token against the frozen set.
2. Alternation-injected regex — at hook build time, rewrite the pattern to embed the current frozen list; re-compile on DNA.md change. Works only for short lists.

**Known FP mitigations:** `grep -r` anchored to `^grep\b` (read-only, never block); `find -delete` inside `.git/` excluded when `cwd ⊂ .git`; `rm -rf /tmp/…` allowlisted; `git commit -m "rm -rf /"` handled by span-kind classification (Executed vs Data vs InlineCode, per dcg's SpanKind). ShellCheck SC2115 catches `rm -rf "$VAR/*"` when `$VAR` unset — complement the runtime hook with static lint.

Sources: https://github.com/anthropics/claude-code/blob/main/examples/hooks/bash_command_validator_example.py, https://github.com/falcosecurity/rules/blob/main/rules/falco_rules.yaml, https://falco.org/blog/falco-mitre-attack/, https://github.com/Dicklesworthstone/destructive_command_guard, https://www.shellcheck.net/wiki/SC2115, https://registry.semgrep.dev/tag/bash, https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html, https://docs.liquibase.com/pro/user-guide-4-33/no-delete-without-where, https://zread.ai/instructkr/claude-code/27-bash-security-and-sandbox

---

### Q3. Audit-mode (log-only) hook implementation

**Use JSONL, not syslog or OTel.** JSON Lines is zero-dep, `jq`-queryable, trivially appendable, and maps cleanly to the OpenTelemetry Logs Data Model if you later forward via the OTel Collector `filelog` receiver. Syslog (RFC 5424) requires a daemon. OTel logs are a logical model, not an emission format. The community's 12-factor stdout ideal doesn't work here because Claude Code consumes hook stdout for its decision protocol — **you must write to a file**.

**Storage:** local `.claude/logs/audit-YYYY-MM-DD.jsonl` with in-script size-based rotation via `flock` + atomic `mv`. Because each hook invocation is a short-lived process, the classic logrotate "writer keeps old fd" trap doesn't apply — rename-and-recreate is safe. Migrate to SQLite only if volume exceeds a few hundred MB/day; Postgres is over-kill.

**Minimum viable metric set (for later FP-rate math):** `timestamp, session_id, tool_name, matcher, regex_matched, would_have_blocked, decision, rule_id, rule_version`. Strongly add: `tool_input_hash, user_prompt_hash, file_path, cwd, hook_event_name`. For true FP computation you **must** correlate with PostToolUse to capture `tool_succeeded` and user_override — without that you only have *would-have-blocked rate*, not *false-positive rate*.

**A/B decision threshold:** target **FP ≤ 1%** (≤ 0.5% for promotion to `deny`). To estimate a 1% rate within ±0.5 pp at 95% confidence requires **n ≈ 1,520 flagged events** per rule. Practical ladder: <100 matches → stay audit; 100–1,000 + FP ≤ 1% → promote to `ask`; >1,000 + FP ≤ 0.5% → promote to `deny`. Roll out per-rule, not globally — SRE Workbook's canary granularity principle.

**auditbeat/auditd/Falco do not wrap Claude Code hooks** — they operate at syscall level, not app-semantic level. Indirect integration (point the OTel Collector's `filelog` receiver at the JSONL) is simpler than trying to force-fit.

**PII sanitization regexes (bash-pragmatic subset):** AWS `AKIA[0-9A-Z]{16}`; GitHub `ghp_[A-Za-z0-9]{36}` and `github_pat_[A-Za-z0-9_]{80,}`; Slack `xox[baprs]-[A-Za-z0-9-]{10,}`; OpenAI/Anthropic `sk-[A-Za-z0-9_\-]{20,}` and `sk-ant-[A-Za-z0-9_\-]{20,}`; Google `AIza[0-9A-Za-z\-_]{35}`; JWT `eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}`; PEM `-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----`. Replace with `[REDACTED:type:last4]`. **Bash regex will miss anything gitleaks catches via entropy** — for stronger guarantees, pipe the preview through `gitleaks detect --no-git --redact` or a Presidio analyzer service.

**Rotation pattern:** `flock -w 2 9` on a lock file (subshell redirection `) 9>"$LOCK_FILE"`), `wc -c` size check, `mv -f` atomic rename to `audit-YYYY-MM-DD-TTTTTT.jsonl`, `: >` truncate new file, append record. **Always `exit 0` — a broken audit hook must never break the user's session.** Graceful degradation when `jq` missing: grep/sed fallback with explicit JSON escape routine.

Reference `_log_only.sh` (≈150 lines), JSONL schema, and jq analysis queries (FP rate per rule, time-series, promotion-readiness check) were produced in full during research and should be dropped into `.claude/hooks/_log_only.sh`. The schema borrows OTel top-level field names (`timestamp, severity_text, attributes`) so later ingestion is free.

Sources: https://code.claude.com/docs/en/hooks, https://12factor.net/logs, https://opentelemetry.io/docs/specs/otel/logs/data-model/, https://github.com/gitleaks/gitleaks, https://github.com/foozzi/secrets-patterns-db, https://microsoft.github.io/presidio/analyzer/adding_recognizers/, https://sre.google/workbook/canarying-releases/, https://jsonl.help/tools/

---

### Q4. biretos-mcp architecture

**Stack decision: FastMCP (Python).** Three tie-breaking reasons: (1) the AI-Audit toolchain is already Python — importing `bundle_builder.py`, `gemini_call.py`, `build_index.py` as modules is a ~5-line refactor vs 100% wrapping work in TypeScript; (2) FastMCP was absorbed into the official `mcp` Python SDK and Prefect-maintained FastMCP 3.x powers ~70% of production MCP servers; (3) cold-start budgets are met in all three candidates (Python ~300–800 ms, Node ~200 ms faster, Go ~500 ms faster — all well under the 2 s target). Pick Go only for high-RPS or single-binary distribution; pick TypeScript only if you have no Python to wrap.

**Wrap vs rewrite:** prefer **library import** for `bundle_builder.py` and `build_index.py`; use **subprocess** for `gemini_call.py` to isolate network calls with a hard timeout. Lazy-import heavy deps (`google-generativeai`, `numpy`) inside tool bodies — not at module top — to keep startup low.

**Auth:** spec is explicit — *"Implementations using an STDIO transport SHOULD NOT follow this specification, and instead retrieve credentials from the environment."* stdio + env-injected `GEMINI_API_KEY` is the standard. OAuth 2.1 + PKCE is only required for HTTP/Streamable-HTTP remote servers.

**Observability golden rule:** *"Local MCP servers should not log messages to stdout, as this will interfere with protocol operation."* All logs → **stderr**, which Claude Code captures automatically. Structured JSON with `timestamp, level, tool, duration_ms, trace_id, request_id`. Surface progress to the LLM host via FastMCP `ctx.info()`/`ctx.error()` (uses `notifications/message`).

**Error handling:** raise `fastmcp.exceptions.ToolError("...")` for client-visible intentional errors (always sent regardless of masking); configure `FastMCP(..., mask_error_details=True)` so other exceptions return a generic "Error calling tool" — prevents leaking paths/creds. Use `subprocess.run(..., timeout=300, check=False)` and translate failures to `ToolError` with the last 500 chars of stderr.

**Hot-reload works:** MCP spec's `tools.listChanged: true` capability + `notifications/tools/list_changed` is supported — *"When an MCP server sends a list_changed notification, Claude Code automatically refreshes the available capabilities from that server."* For internal-logic changes (same tool signature), the next invocation picks up new code only if the server process itself reloaded. Dev tools: `mcp-reloader` or `mcp-server-hmr` watch files and restart transparently.

**Security isolation (April 2026 context is hot):** Ox Security / The Register reported stdio MCP CVEs; Anthropic warns *"MCP adapters, specifically STDIO ones, should be used with caution."* Pragmatic layering for biretos: dedicated venv at `.claude/mcp/biretos-mcp/.venv` + env-file secrets + `subprocess.run` with timeouts. Docker only if shipping to multiple developers with untrusted input. Never commit real keys in `.mcp.json` — use `${GEMINI_API_KEY}` expansion.

**Architecture:**
```
Claude Code ──stdio/JSON-RPC──▶ biretos-mcp (FastMCP)
                                 │
                                 ├── import ──▶ ai_audit/{bundle_builder,build_index}.py
                                 └── subprocess ──▶ python -m ai_audit.gemini_call ──▶ Gemini API
```

**Directory skeleton for `.claude/mcp/biretos-mcp/`:** `server.py` (FastMCP entrypoint), `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example` / `.env` (gitignored), `README.md`, `tools/{bundle,gemini,index}.py`, `_logging.py`, `tests/`, `scripts/dev.sh`. Plus a project-root `.mcp.json` (committed) with `enableAllProjectMcpServers: true` in `.claude/settings.json`.

Example `.mcp.json` entry: `{ "mcpServers": { "biretos-mcp": { "type": "stdio", "command": "uv", "args": ["run", "--project", ".claude/mcp/biretos-mcp", "python", ".claude/mcp/biretos-mcp/server.py"], "env": { "AI_AUDIT_ROOT": "${workspaceFolder}", "GEMINI_API_KEY": "${GEMINI_API_KEY}" } } } }`.

**Closest pattern precedent:** `mcp-server-git` (Python, wraps `gitpython`, stdio, uvx-installable).

Sources: https://modelcontextprotocol.io/specification/draft/basic/authorization, https://modelcontextprotocol.io/docs/tools/debugging, https://gofastmcp.com/servers/tools, https://github.com/modelcontextprotocol/python-sdk, https://github.com/modelcontextprotocol/servers, https://code.claude.com/docs/en/mcp, https://docs.anthropic.com/en/docs/claude-code/security, https://www.theregister.com/2026/04/16/anthropic_mcp_design_flaw/

---

### Q5. Dynamic DNA §3 sync for frozen_guard

**Strategy: SHA-256–invalidated cache, awk parser, fail-closed.** Community consensus is <100 ms budget for PreToolUse hooks; the Ruflo case (18–21 s CLI latency from 11 spawning hooks) is the cautionary tale. Bash startup ~10 ms, Node ~50–100 ms, Python ~200–400 ms — so pure-bash is the right tool.

**Hash-cache idiom:** `sha256sum -- docs/PROJECT_DNA.md | awk '{print $1}'` compared against `.claude/hooks/_cache/frozen_list.sha256`; on miss, regenerate `.claude/hooks/_cache/frozen_list.txt` via awk and atomically `mv`. SHA-256 on 50 KB is ~1 ms CPU; full fork+compare ~2–4 ms. Measured: **hot-cache ≈ 6.1 ms ± 0.8 ms, cold-parse ≈ 11.4 ms ± 1.1 ms** via hyperfine — comfortably under budget.

**Reject daemon (inotify/fswatch) for default deployment** — adds supervision burden, breaks in CI/fresh clones. Offer as optional optimization.

**Recommend git pre-commit hook as a complement**, not replacement: `.pre-commit-config.yaml` with `files: ^docs/PROJECT_DNA\.md$` → regenerate both `frozen_list.txt` and `frozen_list.sha256`, `git add` them. Runtime hook stays as safety net during live Claude sessions; pre-commit keeps the cache canonical in git for fresh clones and CI.

**Fail-closed on missing/parse error — this is non-negotiable.** Saltzer & Schroeder's "deny by default" principle, restated by Zwicky/Cooper/Chapman: *"the default deny stance... is a fail-safe stance. It recognizes that what you don't know can hurt you."* If `docs/PROJECT_DNA.md` is missing or §3 parses empty → `exit 2` with actionable stderr. Expose `FROZEN_GUARD_FAIL_OPEN=1` as a documented emergency escape hatch, but never default-open.

**Robust awk parsing:**
```awk
/^##[[:space:]]+3\./        { in_section = 1; next }
/^##[[:space:]]+[0-9]+\./   { in_section = 0 }
in_section && /^[[:space:]]*[-*+][[:space:]]+/ {
  sub(/^[[:space:]]*[-*+][[:space:]]+/, "")
  gsub(/`/, ""); sub(/[[:space:]\r]+$/, "")
  if (length($0) > 0) print
}
```
Handles CRLF, trailing whitespace, backticked paths, nested lists, `## 10.` after `## 9.` (regex `[0-9]+\.`), unicode/emoji headings. Sed-range approach (`/^## 3\./,/^## 4\./p`) is **fragile** — breaks on renumbering.

**Injection hardening (OWASP + BashPitfalls):**
- Never `eval` parsed input.
- Always double-quote expansions (ShellCheck SC2086).
- `printf '%s\n' "$var"` over `echo`.
- `while IFS= read -r line` (no word-splitting, no backslash interpretation).
- String compare `[[ "$target" == "$frozen" ]]`, never execute.
- `--` sentinel: `sha256sum -- "$file"`.

Because DNA.md content is only ever used as *data* (string-compared against target path, printed in stderr), steps 2–5 fully neutralize `$(rm -rf /)`-style injection.

Full reference `frozen_guard.sh` (~90 lines) and `refresh_frozen_cache.sh` pre-commit companion were produced during research. Wire with: `{ "PreToolUse": [{ "matcher": "Write|Edit|MultiEdit", "hooks": [{ "type":"command", "command":"$CLAUDE_PROJECT_DIR/.claude/hooks/frozen_guard.sh", "timeout":5 }] }] }`.

Sources: https://karanbansal.in/blog/claude-code-hooks/, https://github.com/ruvnet/ruflo/issues/1530, https://man7.org/linux/man-pages/man1/inotifywait.1.html, https://pre-commit.com/, https://iris.unitn.it/bitstream/11572/251142/1/SPM-fail-safe-v7.pdf, https://www.cs.ait.ac.th/~on/O/oreilly/tcpip/firewall/ch03_05.htm, https://google.github.io/styleguide/shellguide.html, https://mywiki.wooledge.org/BashPitfalls, https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html, https://github.com/sharkdp/hyperfine

---

### Q6. claude-mem plugin integration

**Critical upgrade first.** v12.1.3 has a **100% observation-failure bug** on Claude Code ≥ 2.1.109 due to empty-string `--setting-sources` arg corruption. Fixed in v12.1.4 (commit 3d92684 — `fix: filter empty string args before Bun spawn()`). **Before investing in any integration work, bump to ≥ v12.1.4.**

**Coexistence is the Claude Code default, not a claude-mem feature.** No claude-mem documentation addresses shared-matcher conflicts — the plugin treats coexistence as user-managed. But Claude Code itself guarantees it: *"Plugin hooks merge with user's hooks and run in parallel"* (Anthropic SKILL.md); *"hooks from multiple layers are merged and all run, not overwritten"* (official reference). Your project-level `UserPromptSubmit` runs alongside claude-mem's `new-hook.js`; both stdouts get appended to the model context. No override risk.

**Matcher overlap audit:**

| Shared hook | claude-mem | Your proposed project hook | Combined outcome | Status |
|---|---|---|---|---|
| UserPromptSubmit | creates SQLite session row, auto-starts worker | optional prompt rewriter | both run, both stdouts added to context | verified |
| PostToolUse `*` | enqueues observation async | e.g. Prettier on Write/Edit | parallel; claude-mem doesn't mutate files | verified |
| Stop | `POST /api/sessions/summarize`; emits `{continue:true, suppressOutput:true}` (issue #1290 — fails Stop schema, cosmetic noise) | notification/test-run | your `decision:"block"` still honored; summary fires anyway | verified |
| SessionEnd | 2 s tight self-imposed budget | git commit/archive | independent timeouts | verified |
| PreToolUse(Read) | **File Read Gate** — denies when observations exist, injects timeline | — (we're not adding Read hooks) | no overlap | verified |
| PreToolUse(Edit) | **extended File Read Gate as of v12.0.0** | your Edit hook | **overlap — deny wins over allow** | verified risk |
| PreToolUse(Write) | not claimed | frozen_guard | no interaction | verified no-conflict |
| PreToolUse(Bash) | not claimed | bash_guard | no interaction | verified no-conflict |

**Known conflicts (ranked):**
1. **HIGH — v12.1.3 bug** (upgrade to v12.1.4+).
2. **HIGH — PreToolUse(Edit) matcher overlap.** If your project Edit hook returns `allow` and claude-mem's Read Gate returns `deny`, the deny wins (precedence `deny > defer > ask > allow`) — your edit is blocked with a timeline injection. Also observed: subagent-modified files become unreadable for the rest of the conversation due to bad cache validation (issue #1719).
3. **MED — Stop-hook JSON validation noise** (issue #1290) — cosmetic only.
4. **MED — Port :37777 availability** — configurable via `CLAUDE_MEM_WORKER_PORT`; pre-flight with `lsof -i :37777`. Issues #324/#363/#380 — mostly Windows.
5. **MED — SessionStart ANSI error spam** (issues #621, #1237) — workaround: remove `user-message-hook.js` entry.
6. **LOW — UserPromptSubmit context duplication** — both hooks emit context; ~2× token cost for that single event.
7. **LOW — `/api/settings` leaks API keys in cleartext** (security audit #1251) — audit `~/.claude-mem/settings.json` permissions.

**Mitigations:** (2) either don't register PreToolUse(Edit) — use PostToolUse(Edit) instead; or set `CLAUDE_MEM_EXCLUDED_PROJECTS=<your-project-path>` to disable the Read Gate for biretos-automation; or remove the Read/Edit matcher from plugin's `hooks.json`. (4) set `CLAUDE_MEM_WORKER_PORT=38888`. (6) route your observations through claude-mem's worker: `curl -s -X POST localhost:37777/api/observations` — zero hook-level duplication.

**Programmatic API exists** — 22 HTTP endpoints on :37777 (`/api/observations`, `/api/sessions/*`, `/api/context/inject?project=...`, etc.) plus 4 MCP tools (`search`, `get_observations`, `timeline`). This means **integrate-via-API**, not parallel hooks, is feasible.

**Migration alternatives:**
- **Native Claude Code memory (CLAUDE.md + /memory)** — zero hooks, zero conflicts, but no semantic search.
- **basic-memory** — zero lifecycle hooks (pure MCP server), local markdown + SQLite/FTS/vectors, actively maintained.
- **mem0** — cloud-hosted (needs `MEM0_API_KEY`), similar hook footprint to claude-mem; self-host option exists.

**Recommendation for biretos:** Keep claude-mem (upgrade to ≥ v12.1.4), **do not register PreToolUse(Edit)** — use PostToolUse(Edit), and **integrate-via-API** for anything that overlaps with claude-mem's captured events. If you don't actually need automatic tool-call capture + semantic search, native CLAUDE.md + basic-memory is the cleanest zero-conflict path.

Sources: https://github.com/thedotmack/claude-mem/releases, https://docs.claude-mem.ai/hooks-architecture, https://docs.claude-mem.ai/file-read-gate, https://docs.claude-mem.ai/architecture/worker-service, https://github.com/anthropics/claude-code/blob/main/plugins/plugin-dev/skills/hook-development/SKILL.md, https://code.claude.com/docs/en/hooks, https://github.com/thedotmack/claude-mem/issues/{324,363,380,621,1237,1251,1290,1471,1719}, https://docs.mem0.ai/integrations/claude-code, https://github.com/basicmachines-co/basic-memory, https://docs.anthropic.com/en/docs/claude-code/memory

---

### Q7. Production-grade `.claude/` reference setups

**Top-5 reference repos:**

1. **ChrisWiles/claude-code-showcase** (⭐ ~5.8k) — closest to "production team" shape. Notable: `skill-eval.sh`/`skill-rules.json` `UserPromptSubmit` hook that scores prompts against a skill catalog (weighted confidence by keywords/paths/intent-regex), `settings.md` plain-English companion to `settings.json`, `.mcp.json` with `${VAR}` expansion + `enabledMcpjsonServers` allow-list, PreToolUse block-on-main (`[ "$(git branch --show-current)" != "main" ] || exit 2`, 5 s timeout). Caveat: single-author showcase; shallow commit history.

2. **obra/superpowers** (⭐ ~152k, v5.0.7 March 2026) — the most-starred Claude Code plugin. Skills > bare prompts (each is a directory with `SKILL.md` + scripts, trigger-rich descriptions). Phase-gated workflow (`brainstorming → writing-plans → subagent-driven-development → test-driven-development → requesting-code-review → finishing-a-development-branch`). **"Verification before completion" skill** mandates running verify commands before Claude claims "done" — closes the #1 agent failure mode (false completion). Two-stage code review inside `executing-plans`. Ships parallel `.codex/`, `.cursor-plugin/`, `.opencode/` dirs (multi-platform parity).

3. **wshobson/agents** (⭐ ~33.8k) — 182 specialized subagents / 149 skills / 77 plugins. Notable: Sonnet/Haiku **model tier-routing** documented inline (architect/reviewer = Sonnet, implementer/test/deploy = Haiku — cuts cost 3–5×). Team-role decomposition (lead/implementer/reviewer/debugger) with explicit file-ownership contracts preventing parallel-subagent merge hell. One-concern-per-plugin granularity.

4. **VoltAgent/awesome-claude-code-subagents** (⭐ ~17.1k) — 100+ subagents in 10 numbered taxonomic categories (`01-architecture/`, `02-lang/`, …, `09-meta-orchestration/`). Canonical frontmatter template: `name, description, tools, model`. `install-agents.sh` interactive installer (global vs project scope).

5. **disler/claude-code-hooks-mastery** — canonical hooks reference. All 8+ lifecycle events wired end-to-end using **`uv run` single-file Python scripts (PEP-723 inline deps)** — fast startup, no pip-install churn. JSON-logging every hook to `logs/*.json` for audit. Builder/Validator agent team + Meta-agent that scaffolds new agents on demand.

**Extracted patterns:**
- **"Lightweight gate + heavyweight deferred" hook chain:** PreToolUse = cheap blocking checks only (<100 ms target); PostToolUse = fire-and-forget formatters scoped by exact matcher + in-script extension filter, `|| true`; heavy validation (tsc, full tests, build) scoped to `Bash(git push*)` / `Bash(git commit*)` — never per-edit.
- **Agent frontmatter canonical shape:** `name: code-reviewer; description: <trigger-rich, ≤1024 chars>; tools: Read, Grep, Bash(git:*); model: sonnet|opus|haiku`.
- **MCP config discipline:** commit `.mcp.json` at repo root (not inside `.claude/`); never inline secrets → always `${VAR}`; gate activation via `enabledMcpjsonServers` allow-list in `settings.json`. The "big 6" in production stacks: github, filesystem, postgres, sentry, linear/jira, slack. Remote HTTP MCPs with OAuth (Sentry pattern) are the preferred transport where supported.
- **Defense-in-depth permissions:** `defaultMode: "default"` + tiered `allow`/`ask`/`deny` + `disableBypassPermissionsMode: "disable"` + env `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1"`. Split `settings.json` (committed) from `settings.local.json` (gitignored).
- **Skill-selection UserPromptSubmit hook** — pre-analyze prompts against a rules file and inject "SKILL ACTIVATION REQUIRED" into context rather than relying on Claude's own semantic match.

**Antipatterns (verified):**
1. **Hook cascades spawning Node/Python per event** — ruvnet/ruflo #1530: 11 hooks × 9 events, each forking node, ballooned latency from 4.8 s → 18–21 s. Fix: inline shell for PreToolUse; `uv run` only when a runtime is unavoidable. Strict <100 ms budget.
2. **Broad matchers pairing heavy tools with high-frequency events** — `tsc --noEmit` on every `Write|Edit` recompiles the whole project on every file touch. Fix: narrow matcher + extension filter; defer heavy checks to `Bash(git commit*)` matchers.
3. **Blocking Stop hooks → infinite Stop loop** — exit-2 on Stop to force "continue working" re-enters if the follow-up work hits the same condition. Fix: use `{"continue": false}` JSON; only exit-2 on a monotonic decreasing invariant; cap retries via tempfile counter.
4. **Over-broad Bash deny regex** — `Bash(rm *)` breaks `npm run rm-stale-cache`, `rm package-lock.json`; teams disable permissions in frustration. Fix: narrow anchored patterns (`Bash(rm -rf /*)`, `Bash(rm -rf ~)`); use `ask` tier for ambiguous cases; `disableBypassPermissionsMode: "disable"` at org-level.
5. **Trusting `permissions.deny` alone for secrets** — anthropics/claude-code issues #8961, #27040, #6699 all document `"deny": ["Read(./.env)"]` being silently ignored in some sessions. Fix belt-and-suspenders: (a) secrets outside workspace; (b) PreToolUse hook grepping file paths for `\.env|secrets/|credentials|\.pem$` → exit 2; (c) PreToolUse Bash hook regex for secret patterns; (d) `.gitignore` + `.claudeignore`.
6. **SessionStart daemons** — ruflo again: SessionStart launches daemon-manager with watchdog + 10 workers. Zombies remain on crash. Fix: SessionStart must be idempotent and terminal; manage daemons with systemd/launchd and have the hook just health-check.

Sources: https://github.com/ChrisWiles/claude-code-showcase, https://github.com/obra/superpowers, https://github.com/wshobson/agents, https://github.com/VoltAgent/awesome-claude-code-subagents, https://github.com/disler/claude-code-hooks-mastery, https://github.com/iannuttall/claude-agents, https://github.com/anthropics/claude-code/tree/main/examples, https://github.com/getsentry/sentry-mcp, https://github.com/ruvnet/ruflo/issues/1530, https://github.com/anthropics/claude-code/issues/{6699,8961,27040}, https://dev.to/helderberto/claude-code-hooks-1k7a, https://claudefa.st/blog/tools/hooks/hooks-guide, https://deepwiki.com/webdevtodayjason/claude-hooks/13.2-hook-execution-errors

---

### Cross-cutting recommendations

**Revised priority ordering vs Tier 1 plan.**

The deep research confirms Tier 1's REVISE verdict but reshuffles urgency:

1. **Promote to P0 (blocking): claude-mem ≥ v12.1.4 upgrade.** The v12.1.3 bug silently kills 100% of observations on Claude Code ≥ 2.1.109 — no point shipping any integration work on a broken memory plugin. This was not surfaced in Tier 1 and is the single highest-leverage 5-minute action.
2. **P0.2 frozen_guard (APPROVE, already Tier-1 approved)** — ship with the hash-cache + awk pattern from Q5. Add the git pre-commit companion in the same PR so fresh clones work instantly. Wire as `matcher: "Write|Edit|MultiEdit"` — and since Q6 confirmed claude-mem's File Read Gate extends to `Edit` in v12.0.0+, either set `CLAUDE_MEM_EXCLUDED_PROJECTS=<biretos-path>` OR drop `Edit` from your matcher to avoid the deny-wins conflict.
3. **P3.13 AI-Audit spec externalization (APPROVE, already Tier-1 approved)** — keep as planned.
4. **Upgrade P0.1 bash_guard from DEFER to P1 with audit-mode first** — the Q3 reference `_log_only.sh` enables shipping the hook *today* with zero user disruption, collecting 100–1000 flagged events, then promoting to `ask`, then `deny` per rule. This converts a deferred decision into a running data collector.
5. **Keep MCP DEFER but narrow the design to FastMCP (Python, library-import)** — Q4 resolves the stack question; when you un-defer, the skeleton is ready to drop in. stdio + env-injected keys, no OAuth.
6. **Keep subagents DEFER** — wshobson's model-tier routing pattern (Sonnet-for-hard/Haiku-for-repetitive) is the single most valuable pattern to copy if and when you un-defer; budget it as a cost-optimization play, not a capability play.
7. **Reject P3.14 global defaultMode and P1.7 liveness hook — reaffirmed.** The parallel-execution finding in Q1 means a liveness hook can't gate anything useful, and global defaultMode collides with enterprise `allowManagedHooksOnly` and with claude-mem's hook set.

**New risks surfaced by deep research.**

1. **Parallel-execution semantics** (Q1) invalidate any plan that assumes ordering between frozen_guard, bash_guard, and claude-mem hooks. Each hook must be *independently* correct. The `deny > defer > ask > allow` precedence rule is your only coordination primitive.
2. **600 s default command timeout is fail-open**, not fail-closed (Q1). Your security-critical hooks must not rely on timeout to block — enforce explicit `exit 2` inside a wrapped `timeout 5` if needed.
3. **claude-mem's File Read Gate extends to PreToolUse(Edit) in v12.0.0+** (Q6) — a previously-silent overlap with any planned Edit hook. Mitigation is a one-liner env var, but it must be explicit.
4. **`$CLAUDE_TOOL_ARGS` does not exist** (Q1) — any design that assumed env-var delivery of tool arguments is broken. Rewrite to consume stdin JSON (`tool_input.file_path`, `tool_input.command`, etc.).
5. **April 2026 stdio MCP CVE disclosures** (Q4) — Ox Security / The Register reports warrant an explicit secrets-hygiene checklist before biretos-mcp ships: dedicated venv, `.env` outside repo, no inline keys in committed `.mcp.json`, subprocess timeouts, and ideally `gitleaks detect --no-git` in the pre-commit chain.
6. **`permissions.deny` silent-bypass bugs** (Q7, issues #6699/#8961/#27040) — do not treat deny rules as sufficient protection for `.env`, secrets, or frozen files. Defense-in-depth with PreToolUse hooks is mandatory, not optional.
7. **Hook-cascade latency is real** (Q5, Q7) — Ruflo's 18–21 s regression is the floor of what happens when you don't budget. Every new hook must be benchmarked with `hyperfine` against the <100 ms ceiling before merge.

**Open questions remaining after Deep Research.**

1. **Exact claude-mem PostToolUse latency under load.** Docs claim <20 ms fire-and-forget, but no published measurement on a project with 10+ PostToolUse hooks running in parallel. Mitigation: measure locally after biretos-mcp + bash_guard + frozen_guard are all live.
2. **OTel Collector `filelog` receiver compatibility with the exact JSONL schema** proposed in Q3 — we borrowed OTel field names but didn't round-trip test. Low-risk, but worth a ~30-min validation before relying on downstream OTel ingestion.
3. **Whether Anthropic plans to deprecate `$CLAUDE_TOOL_*` env vars entirely** (issue #9567 is open). If they're eventually populated, some community hook examples may become correct — but designing against stdin JSON today is strictly safer.
4. **claude-mem's roadmap on PreToolUse(Edit) Gate policy.** v12.0.0 extended to Edit; it could extend to Write next, which would break frozen_guard by the same deny-precedence mechanism. Mitigation: pin claude-mem version in `.claude/settings.json` and monitor CHANGELOG.
5. **Whether a `before`/`after` hook field will be added** — no hint in the current roadmap, but the absence of ordering is a real design constraint; several community issues request it.
6. **How to correlate PreToolUse and PostToolUse events for true FP-rate math** (Q3) when hook invocations are independent processes with no shared state — `tool_input_hash` + `session_id` is the proposed join key, but duplicate tool_inputs within a session could conflate.
7. **Whether to eventually migrate biretos memory off claude-mem to basic-memory** (Q6) — unresolved trade-off between automatic capture (claude-mem's strength) and zero hook footprint (basic-memory's strength). Recommend running both for one sprint as an A/B.