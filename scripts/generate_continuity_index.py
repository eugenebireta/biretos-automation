"""Deterministic generator for docs/autopilot/CONTINUITY_INDEX.md.

The generator keeps the continuity index as a derived, non-authoritative
artifact. It mirrors STATE where required and only flags roadmap drift instead
of trying to resolve it automatically.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_PATH = REPO_ROOT / "docs" / "autopilot" / "STATE.md"
DEFAULT_ROADMAP_PATH = REPO_ROOT / "docs" / "EXECUTION_ROADMAP_v2_3.md"
DEFAULT_COMPLETED_LOG_PATH = REPO_ROOT / "docs" / "COMPLETED_LOG.md"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "docs" / "autopilot" / "CONTINUITY_INDEX.md"
MANUAL_ADDENDUM_HEADER = "## Manual Addendum"


@dataclass(frozen=True)
class LocatedValue:
    value: str
    line_no: int


@dataclass(frozen=True)
class TaskStatusBlock:
    task_id: str
    status: str
    line_no: int
    block_end: int


@dataclass(frozen=True)
class CompletedEntry:
    date: str
    task_id: str
    risk: str
    summary: str
    line_no: int


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _clean_scalar(raw: str) -> str:
    value = raw.strip()
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    return value


def _find_prefixed_value(lines: list[str], prefix: str) -> LocatedValue:
    for line_no, line in enumerate(lines, start=1):
        if line.startswith(prefix):
            return LocatedValue(_clean_scalar(line[len(prefix) :]), line_no)
    raise ValueError(f"missing required field: {prefix}")


def _find_optional_prefixed_value(lines: list[str], prefix: str) -> LocatedValue | None:
    for line_no, line in enumerate(lines, start=1):
        if line.startswith(prefix):
            return LocatedValue(_clean_scalar(line[len(prefix) :]), line_no)
    return None


def _find_last_note(lines: list[str]) -> LocatedValue | None:
    note_re = re.compile(r'^\s*note:\s*"(.*)"\s*$')
    found: LocatedValue | None = None
    for line_no, line in enumerate(lines, start=1):
        match = note_re.match(line)
        if match:
            found = LocatedValue(match.group(1), line_no)
    return found


def _parse_task_status_blocks(lines: list[str]) -> list[TaskStatusBlock]:
    blocks: list[TaskStatusBlock] = []
    status_re = re.compile(r"^task_(\d+(?:_\d+)*)_status:\s*(.+)$")
    for index, line in enumerate(lines):
        match = status_re.match(line)
        if not match:
            continue
        task_id = match.group(1)
        status = _clean_scalar(match.group(2))
        block_end = index + 1
        probe = index + 1
        prefix = f"task_{task_id}_"
        while probe < len(lines) and lines[probe].startswith(prefix):
            block_end = probe + 1
            probe += 1
        blocks.append(TaskStatusBlock(task_id=task_id, status=status, line_no=index + 1, block_end=block_end))
    return blocks


def _task_sort_key(task_id: str) -> tuple[int, ...]:
    return tuple(int(part) for part in task_id.split("_"))


def _latest_closed_task_block(lines: list[str]) -> TaskStatusBlock | None:
    candidates = [
        block
        for block in _parse_task_status_blocks(lines)
        if block.status.upper() in {"MERGED", "CLOSED", "DONE"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda block: _task_sort_key(block.task_id))


def _parse_completed_entries(lines: list[str]) -> list[CompletedEntry]:
    entries: list[CompletedEntry] = []
    entry_re = re.compile(r"^(\d{4}-\d{2}-\d{2}) \| ([^|]+) \| ([^|]+) \| (.+)$")
    for line_no, line in enumerate(lines, start=1):
        match = entry_re.match(line)
        if not match:
            continue
        entries.append(
            CompletedEntry(
                date=match.group(1),
                task_id=match.group(2).strip(),
                risk=match.group(3).strip(),
                summary=match.group(4).strip(),
                line_no=line_no,
            )
        )
    return entries


def _latest_relevant_completed_entry(lines: list[str]) -> CompletedEntry | None:
    entries = _parse_completed_entries(lines)
    if not entries:
        return None
    task_entries = [entry for entry in entries if entry.task_id.startswith("Task ")]
    if task_entries:
        return task_entries[-1]
    return entries[-1]


def _extract_stage_number(active_task: str) -> str | None:
    match = re.match(r"^(\d+(?:\.\d+)?)", active_task.strip())
    if not match:
        return None
    return match.group(1)


def _first_line_contains(lines: list[str], needle: str) -> int | None:
    for line_no, line in enumerate(lines, start=1):
        if needle in line:
            return line_no
    return None


def _roadmap_stage_conflict(lines: list[str], stage_number: str | None) -> tuple[int, int] | None:
    if not stage_number:
        return None
    stage_markers = (
        f"Этап {stage_number}",
        f"Stage {stage_number}",
    )
    positive_line: int | None = None
    negative_line: int | None = None
    for line_no, line in enumerate(lines, start=1):
        if not any(marker in line for marker in stage_markers):
            continue
        lowered = line.lower()
        if positive_line is None and any(token in lowered for token in ("monitor", "active", "done", "активно")):
            positive_line = line_no
        if negative_line is None and "не начат" in lowered:
            negative_line = line_no
    if positive_line and negative_line:
        return positive_line, negative_line
    return None


def _roadmap_r1_conflict(lines: list[str]) -> tuple[int, int] | None:
    positive_line: int | None = None
    negative_line: int | None = None
    for line_no, line in enumerate(lines, start=1):
        if "R1" not in line:
            continue
        lowered = line.lower()
        if positive_line is None and any(token in lowered for token in ("active dev track", "merged to master", "owner-authorized")):
            positive_line = line_no
        if negative_line is None and "не начат" in lowered:
            negative_line = line_no
    if positive_line and negative_line:
        return positive_line, negative_line
    return None


def _line_ref(path: Path, start: int, end: int | None = None) -> str:
    try:
        repo_relative = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        repo_relative = path.name
    if end is None or end == start:
        return f"{repo_relative}#L{start}"
    return f"{repo_relative}#L{start}-L{end}"


def _read_manual_addendum(path: Path) -> str:
    if not path.exists():
        return "- None.\n"
    text = path.read_text(encoding="utf-8")
    marker = f"\n{MANUAL_ADDENDUM_HEADER}\n\n"
    if marker not in text:
        return "- None.\n"
    return text.split(marker, 1)[1].rstrip() + "\n"


def render_continuity_index(
    *,
    state_path: Path = DEFAULT_STATE_PATH,
    roadmap_path: Path = DEFAULT_ROADMAP_PATH,
    completed_log_path: Path = DEFAULT_COMPLETED_LOG_PATH,
    generated_on: str,
    manual_addendum: str = "- None.\n",
) -> str:
    state_lines = _read_lines(state_path)
    roadmap_lines = _read_lines(roadmap_path)
    completed_lines = _read_lines(completed_log_path)

    active_task = _find_prefixed_value(state_lines, "active_task: ")
    phase = _find_prefixed_value(state_lines, "phase: ")
    status = _find_prefixed_value(state_lines, "status: ")
    awaiting = _find_optional_prefixed_value(state_lines, "awaiting: ")
    todo_later = _find_optional_prefixed_value(state_lines, "TODO later: ")
    latest_note = _find_last_note(state_lines)
    latest_closed_task = _latest_closed_task_block(state_lines)
    latest_completed = _latest_relevant_completed_entry(completed_lines)

    current_start = active_task.line_no
    current_end = status.line_no
    if awaiting is not None:
        current_end = max(current_end, awaiting.line_no)

    verified_entries: list[str] = []
    if latest_closed_task is not None:
        task_label = latest_closed_task.task_id.replace("_", ".")
        claim = f"`Task {task_label}` {latest_closed_task.status.lower()}."
        source_ref = _line_ref(state_path, latest_closed_task.line_no, latest_closed_task.block_end)
        if latest_note is not None and "advancing to" in latest_note.value.lower():
            claim = f"`Task {task_label}` {latest_closed_task.status.lower()}, and execution advanced to `{active_task.value}`."
            source_ref = f"{source_ref}; {_line_ref(state_path, latest_note.line_no)}"
        verified_entries.append(
            "\n".join(
                [
                    f"- ID: `VF-001`",
                    f"  Status: `verified`",
                    f"  Claim: {claim}",
                    f"  Source_ref: `{source_ref}`",
                    f"  Last_validated: `{generated_on}`",
                ]
            )
        )

    if latest_completed is not None:
        verified_entries.append(
            "\n".join(
                [
                    f"- ID: `VF-002`",
                    f"  Status: `verified`",
                    f"  Claim: {latest_completed.summary}",
                    f"  Source_ref: `{_line_ref(completed_log_path, latest_completed.line_no)}`",
                    f"  Last_validated: `{generated_on}`",
                ]
            )
        )

    blocker_entries: list[str] = []
    if awaiting is not None:
        blocker_entries.append(
            "\n".join(
                [
                    f"- ID: `BL-001`",
                    f"  Status: `blocked`",
                    f"  Claim: `{active_task.value}` cannot advance until the `STATE` exit conditions are met: {awaiting.value}",
                    f"  Source_ref: `{_line_ref(state_path, awaiting.line_no)}`",
                    f"  Last_validated: `{generated_on}`",
                ]
            )
        )

    stage_conflict = _roadmap_stage_conflict(roadmap_lines, _extract_stage_number(active_task.value))
    if stage_conflict is not None:
        blocker_entries.append(
            "\n".join(
                [
                    f"- ID: `BL-002`",
                    f"  Status: `blocked`",
                    f"  Claim: `ROADMAP` contains a live drift for `{active_task.value}`: one snapshot marks it active, another still marks it not started.",
                    f"  Source_ref: `{_line_ref(roadmap_path, stage_conflict[0])}; {_line_ref(roadmap_path, stage_conflict[1])}`",
                    f"  Last_validated: `{generated_on}`",
                ]
            )
        )

    r1_conflict = _roadmap_r1_conflict(roadmap_lines)
    if r1_conflict is not None:
        blocker_entries.append(
            "\n".join(
                [
                    f"- ID: `BL-003`",
                    f"  Status: `blocked`",
                    f"  Claim: `ROADMAP` still shows `R1` as not started in one snapshot while other roadmap text says the track is active in practice.",
                    f"  Source_ref: `{_line_ref(roadmap_path, r1_conflict[0])}; {_line_ref(roadmap_path, r1_conflict[1])}`",
                    f"  Last_validated: `{generated_on}`",
                ]
            )
        )

    hypothesis_entries: list[str] = []
    if todo_later is not None:
        hypothesis_entries.append(
            "\n".join(
                [
                    f"- ID: `HY-001`",
                    f"  Status: `open`",
                    f"  Claim: {todo_later.value}",
                    f"  Source_ref: `{_line_ref(state_path, todo_later.line_no)}`",
                    f"  Last_validated: `{generated_on}`",
                ]
            )
        )

    next_item_claim = f"Continue `{active_task.value}` in `{phase.value}` / `{status.value}`."
    if awaiting is not None:
        next_item_claim = f"Continue `{active_task.value}` until the `STATE` exit criteria are satisfied."

    parts = [
        "# CONTINUITY_INDEX",
        "",
        "Purpose: short continuity summary for fast re-entry and handoff.",
        "Non-authoritative. Mirrors canonical and operational sources. If conflict exists, owner source wins.",
        "",
        "## Usage Rules",
        "",
        "- Read after `STATE.md`, not instead of it.",
        "- Preview with `python scripts/generate_continuity_index.py`.",
        "- Write with `python scripts/generate_continuity_index.py --write`.",
        "- Update only after milestone-like events or substantial handoff.",
        "- Every entry must have `source_ref`.",
        "- Do not duplicate decision ledger, audit dumps, or long closeout summaries.",
        "- `Current thread` and `Next approved item` are mirror-from-STATE only.",
        "- Prefer exact `STATE` section or line references, not free retelling.",
        "- Keep this file under 200 lines.",
        "- If this file does not improve re-entry after 2-3 cycles, creates bureaucracy, or becomes a drift source, freeze or remove it.",
        "",
        "## Conflict Rules",
        "",
        "- For live execution conflicts: `STATE` wins over `ROADMAP`.",
        "- For plan and scope conflicts: `PROJECT_DNA`, policy docs, and `MASTER_PLAN` win; `ROADMAP` is only a planning snapshot.",
        "- `CONTINUITY_INDEX` never resolves conflicts by itself; it only mirrors or flags them.",
        "",
        "## Current Thread",
        "",
        "Status: `open`",
        f"Claim: `{active_task.value}` is the active execution thread in `{phase.value}` / `{status.value}`.",
        f"Source_ref: `{_line_ref(state_path, current_start, current_end)}`",
        f"Last_validated: `{generated_on}`",
        "",
        "## Verified Findings",
        "",
        *(verified_entries if verified_entries else ["None."]),
        "",
        "## Active Blockers",
        "",
        *(blocker_entries if blocker_entries else ["None."]),
        "",
        "## Open Hypotheses",
        "",
        *(hypothesis_entries if hypothesis_entries else ["None."]),
        "",
        "## Next Approved Item",
        "",
        "Status: `open`",
        f"Claim: {next_item_claim}",
        f"Source_ref: `{_line_ref(state_path, current_start, current_end)}`",
        f"Last_validated: `{generated_on}`",
        "",
        MANUAL_ADDENDUM_HEADER,
        "",
        manual_addendum.rstrip(),
        "",
    ]
    return "\n".join(parts)


def write_continuity_index(
    *,
    state_path: Path = DEFAULT_STATE_PATH,
    roadmap_path: Path = DEFAULT_ROADMAP_PATH,
    completed_log_path: Path = DEFAULT_COMPLETED_LOG_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    generated_on: str,
) -> str:
    manual_addendum = _read_manual_addendum(output_path)
    content = render_continuity_index(
        state_path=state_path,
        roadmap_path=roadmap_path,
        completed_log_path=completed_log_path,
        generated_on=generated_on,
        manual_addendum=manual_addendum,
    )
    output_path.write_text(content, encoding="utf-8")
    return content


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate docs/autopilot/CONTINUITY_INDEX.md")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--roadmap", type=Path, default=DEFAULT_ROADMAP_PATH)
    parser.add_argument("--completed-log", type=Path, default=DEFAULT_COMPLETED_LOG_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--date", default=None, help="Override Last_validated date (YYYY-MM-DD).")
    parser.add_argument("--write", action="store_true", help="Write the generated index to the output file.")
    args = parser.parse_args()

    generated_on = args.date or date.today().isoformat()
    manual_addendum = _read_manual_addendum(args.output)
    content = render_continuity_index(
        state_path=args.state,
        roadmap_path=args.roadmap,
        completed_log_path=args.completed_log,
        generated_on=generated_on,
        manual_addendum=manual_addendum,
    )
    if args.write:
        args.output.write_text(content, encoding="utf-8")
        return 0

    stdout = sys.stdout
    if hasattr(stdout, "reconfigure"):
        try:
            stdout.reconfigure(encoding="utf-8")
        except ValueError:
            pass
    stdout.write(content)
    if not content.endswith("\n"):
        stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
