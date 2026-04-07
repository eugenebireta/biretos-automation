"""research_runner.py — Claude API deep-research runner for enrichment gaps.

Reads research packets from research_queue/research_queue.jsonl,
sends each to Claude API as a self-contained research task, and saves
results to research_results/.

Results are NEVER written directly to evidence bundles — they require
owner review via prepare_merge_candidates() before any merge.

Budget-aware: checks shadow_log/budget_tracking.json before each call.
Deterministic tests use MockProvider — no live API required.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

_repo_root = Path(_scripts_dir).parent

QUEUE_DIR       = _repo_root / "research_queue"
QUEUE_JSONL     = QUEUE_DIR / "research_queue.jsonl"
RESULTS_DIR     = _repo_root / "research_results"
BUDGET_FILE     = _repo_root / "shadow_log" / "budget_tracking.json"
SHADOW_LOG_DIR  = _repo_root / "shadow_log"

RESULT_VERSION  = "v1"
DAILY_BUDGET_USD: float = float(os.environ.get("RESEARCH_DAILY_BUDGET_USD", "10.0"))

# Cost estimate per research call (claude-haiku-4-5, ~2k tokens in + 1k out)
_COST_PER_CALL_USD: float = 0.05


# ── Budget check ─────────────────────────────────────────────────────────────

class BudgetExceeded(Exception):
    pass


def _get_today_spent_usd() -> float:
    """Read today's cumulative spend from budget_tracking.json."""
    today_str = date.today().isoformat()
    if not BUDGET_FILE.exists():
        return 0.0
    try:
        data = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
        if data.get("date") != today_str:
            return 0.0  # new day, fresh budget
        return float(data.get("daily_total_usd", 0.0))
    except Exception:
        return 0.0


def check_budget(estimated_cost: float = _COST_PER_CALL_USD) -> None:
    """Raise BudgetExceeded if adding estimated_cost would exceed daily limit."""
    spent = _get_today_spent_usd()
    if spent + estimated_cost > DAILY_BUDGET_USD:
        raise BudgetExceeded(
            f"Daily budget exceeded: spent=${spent:.2f} + "
            f"estimated=${estimated_cost:.2f} > limit=${DAILY_BUDGET_USD:.2f}"
        )


def _record_spend(cost_usd: float, model: str) -> None:
    """Append spend to budget_tracking.json."""
    today_str = date.today().isoformat()
    SHADOW_LOG_DIR.mkdir(exist_ok=True)
    data: dict = {}
    if BUDGET_FILE.exists():
        try:
            data = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    if data.get("date") != today_str:
        data = {"date": today_str, "runs": [], "daily_total_usd": 0.0}
    data["runs"].append({
        "provider": "anthropic",
        "model": model,
        "cost_usd": cost_usd,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    data["daily_total_usd"] = round(
        float(data.get("daily_total_usd", 0.0)) + cost_usd, 6
    )
    BUDGET_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── Prompt builder ────────────────────────────────────────────────────────────

def build_research_prompt(packet: dict) -> str:
    """Assemble the Claude research prompt from a research packet."""
    pn = packet["entity_id"]
    brand = packet.get("brand_hint", "Honeywell")
    goal = packet["goal"]
    reason = packet["research_reason"]
    questions = packet["questions_to_resolve"]
    current_state = packet.get("current_state", {})
    known_facts = packet.get("known_facts", {})
    constraints = packet.get("constraints", [])

    return f"""You are a B2B industrial product research specialist with deep knowledge of
industrial sensors, safety equipment, PPE, automation components, and their
distributors.

## Task
{goal}

## Product Identity
- Part Number (PN): {pn}
- Brand (hint): {brand}
- Current name in catalog: {known_facts.get('name', '?')}
- Expected category: {known_facts.get('expected_category', '?')}
- Our price reference (xlsx, not for market use): {known_facts.get('our_price_raw', '?')}

## Research Reason
{reason}

## Questions to Resolve
{chr(10).join(f"- {q}" for q in questions)}

## Current Known State
```json
{json.dumps(current_state, indent=2, ensure_ascii=False)}
```

## Constraints
{chr(10).join(f"- {c}" for c in constraints)}

## Required Output

Return a JSON object with EXACTLY these fields (do not add others):
{{
  "identity_confirmed": true,
  "brand": "Honeywell",
  "title_ru": "Russian product title (concise, accurate)",
  "description_ru": "Short Russian description (1-3 sentences)",
  "category_suggestion": "suggested product category in Russian",
  "price_assessment": "admissible_public_price|no_public_price|ambiguous_offer|blocked_only|rfq_only",
  "price_evidence": "brief explanation: source name, price range, currency, unit basis",
  "photo_assessment": "exact|family|mismatch|not_found",
  "specs_assessment": "found|partial|specs_gap",
  "key_findings": ["finding 1", "finding 2"],
  "ambiguities": ["unresolved question 1"],
  "sources": [
    {{"url": "https://...", "type": "manufacturer|distributor|marketplace|datasheet", "supports": ["identity"]}}
  ],
  "confidence": "high|medium|low",
  "confidence_notes": "brief explanation of confidence level"
}}

Rules:
- Do NOT invent specifications, prices, or URLs
- If you cannot confirm something, say so in ambiguities
- Prefer exact PN matches over family-level information
- For price_assessment: only say admissible_public_price if you know a specific
  public price from a verifiable distributor (not rfq, not quote)
- For category_suggestion: use Russian category names matching industrial catalog conventions
- Return ONLY the JSON object, no surrounding text
"""


# ── Response parser ───────────────────────────────────────────────────────────

def parse_research_response(response_text: str, packet: dict) -> dict:
    """Parse Claude's JSON response into a standardized result record."""
    parsed: dict = {}
    parse_error = ""

    # Try to extract JSON from the response
    try:
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            parsed = json.loads(json_match.group())
        else:
            parse_error = "no_json_block_found"
            parsed = {"raw_response": response_text[:2000]}
    except json.JSONDecodeError as e:
        parse_error = f"json_decode_error: {e}"
        parsed = {"raw_response": response_text[:2000]}

    return {
        "result_version": RESULT_VERSION,
        "task_id": packet.get("task_id"),
        "entity_id": packet.get("entity_id"),
        "research_reason": packet.get("research_reason"),
        "priority": packet.get("priority"),
        "final_recommendation": parsed,
        "sources": parsed.get("sources", []),
        "confidence": parsed.get("confidence", "unknown"),
        "parse_error": parse_error,
        "timestamp": _now_iso(),
        "provider": "claude",
        "model": "",  # filled in by caller
        "raw_response_length": len(response_text),
    }


# ── Provider abstraction ──────────────────────────────────────────────────────

class ResearchProvider:
    """Abstract interface for research LLM calls."""
    def call(self, prompt: str) -> tuple[str, str, float]:
        """Returns (response_text, model_used, estimated_cost_usd)."""
        raise NotImplementedError


class ClaudeResearchProvider(ResearchProvider):
    """Uses ClaudeChatAdapter from providers.py."""

    _model = "claude-haiku-4-5-20251001"

    def call(self, prompt: str) -> tuple[str, str, float]:
        from providers import ClaudeChatAdapter
        adapter = ClaudeChatAdapter()
        response = adapter.complete(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )
        # Rough cost estimate for haiku: $0.25/M in, $1.25/M out
        # ~2k in + ~1k out ≈ $0.0019 per call
        cost = 0.0019
        return response, self._model, cost


class MockResearchProvider(ResearchProvider):
    """Deterministic mock for testing — no API calls."""

    def __init__(self, fixed_response: str = ""):
        self._response = fixed_response or json.dumps({
            "identity_confirmed": True,
            "brand": "Honeywell",
            "title_ru": "Тестовый продукт Honeywell",
            "description_ru": "Тестовое описание продукта.",
            "category_suggestion": "Датчики промышленные",
            "price_assessment": "no_public_price",
            "price_evidence": "Нет публичных цен в данных.",
            "photo_assessment": "not_found",
            "specs_assessment": "specs_gap",
            "key_findings": ["Test finding"],
            "ambiguities": [],
            "sources": [],
            "confidence": "low",
            "confidence_notes": "Mock response — no real research performed",
        }, ensure_ascii=False)

    def call(self, prompt: str) -> tuple[str, str, float]:
        return self._response, "mock", 0.0


# ── Core runner ───────────────────────────────────────────────────────────────

def run_research_for_packet(
    packet_path: str,
    provider: Optional[ResearchProvider] = None,
) -> dict:
    """Read a research packet, send to Claude API, save result.

    Args:
        packet_path: Path to research_packet_{pn}.json
        provider:    Override provider (for testing). Defaults to ClaudeResearchProvider.

    Returns:
        Result record dict.
    """
    if provider is None:
        provider = ClaudeResearchProvider()

    packet_path_obj = Path(packet_path)
    with open(packet_path_obj, encoding="utf-8") as f:
        packet = json.load(f)

    pn = packet["entity_id"]
    pn_safe = re.sub(r'[\\/:*?"<>|]', "_", pn)

    check_budget()  # raises BudgetExceeded if over limit

    prompt = build_research_prompt(packet)
    response_text, model_used, cost = provider.call(prompt)
    _record_spend(cost, model_used)

    result = parse_research_response(response_text, packet)
    result["model"] = model_used
    result["cost_usd"] = cost

    # Save result
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / f"result_{pn_safe}.json"
    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return result


# ── Batch runner ──────────────────────────────────────────────────────────────

def run_batch_research(
    queue_path: Path = QUEUE_JSONL,
    max_items: int = 50,
    priority_filter: Optional[str] = "high",
    provider: Optional[ResearchProvider] = None,
) -> dict:
    """Run research for top-N items from the research queue.

    Args:
        queue_path:      Path to research_queue.jsonl
        max_items:       Maximum number of SKUs to research
        priority_filter: Only process items with this priority (None = all)
        provider:        Override provider (for testing)

    Returns:
        Batch statistics dict.
    """
    if not queue_path.exists():
        return {
            "total": 0, "success": 0, "failed": 0,
            "budget_stop": False,
            "error": f"queue not found: {queue_path}",
        }

    # Read queue
    queue: list[dict] = []
    with open(queue_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                queue.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    # Filter by priority
    if priority_filter:
        filtered = [q for q in queue if q.get("priority") == priority_filter]
    else:
        filtered = queue

    # Skip already-researched
    already_done: set[str] = set()
    if RESULTS_DIR.exists():
        for f in RESULTS_DIR.glob("result_*.json"):
            pn_safe = f.stem.replace("result_", "")
            already_done.add(pn_safe)

    pending = [
        q for q in filtered
        if re.sub(r'[\\/:*?"<>|]', "_", q.get("pn", "")) not in already_done
    ][:max_items]

    batch_results: dict = {
        "total": len(pending),
        "success": 0,
        "failed": 0,
        "budget_stop": False,
        "skipped_already_done": len(filtered) - len(pending),
        "results": [],
        "started_at": _now_iso(),
    }

    for item in pending:
        pn = item.get("pn", "?")
        packet_path = item.get("packet_path", "")

        try:
            result = run_research_for_packet(packet_path, provider=provider)
            batch_results["success"] += 1
            batch_results["results"].append({
                "pn": pn,
                "confidence": result.get("confidence", "unknown"),
                "has_title": bool(
                    result.get("final_recommendation", {}).get("title_ru")
                ),
                "has_price": result.get("final_recommendation", {}).get(
                    "price_assessment"
                ) not in (None, "no_public_price", ""),
                "parse_error": result.get("parse_error", ""),
            })
        except BudgetExceeded as e:
            batch_results["budget_stop"] = True
            print(f"  [BUDGET_STOP] {e}")
            break
        except FileNotFoundError:
            batch_results["failed"] += 1
            print(f"  [FAIL] {pn}: packet not found at {packet_path}")
        except Exception as e:
            batch_results["failed"] += 1
            print(f"  [FAIL] {pn}: {type(e).__name__}: {e}")

    batch_results["completed_at"] = _now_iso()

    # Save batch report
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    report_path = RESULTS_DIR / f"batch_report_{today}.json"
    report_path.write_text(
        json.dumps(batch_results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return batch_results


# ── Quality gate ──────────────────────────────────────────────────────────────

def audit_research_results(results_dir: Path = RESULTS_DIR) -> dict:
    """Analyze research results quality. No API calls."""
    if not results_dir.exists():
        return {"total_results": 0, "error": "results_dir not found"}

    result_files = [f for f in results_dir.glob("result_*.json")]
    audit: dict = {
        "total_results": len(result_files),
        "high_confidence": 0,
        "medium_confidence": 0,
        "low_confidence": 0,
        "unknown_confidence": 0,
        "parse_errors": 0,
        "has_title": 0,
        "has_price": 0,
        "has_sources": 0,
        "issues": [],
    }

    for f in result_files:
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            audit["parse_errors"] += 1
            continue

        conf = r.get("confidence", "unknown")
        if conf == "high":
            audit["high_confidence"] += 1
        elif conf == "medium":
            audit["medium_confidence"] += 1
        elif conf == "low":
            audit["low_confidence"] += 1
        else:
            audit["unknown_confidence"] += 1

        rec = r.get("final_recommendation", {})
        if r.get("parse_error"):
            audit["parse_errors"] += 1
            audit["issues"].append(f"{r.get('entity_id', '?')}: parse error — {r['parse_error']}")
        if rec.get("title_ru"):
            audit["has_title"] += 1
        if rec.get("price_assessment") not in (None, "no_public_price", ""):
            audit["has_price"] += 1
        if r.get("sources"):
            audit["has_sources"] += 1

    # Save audit
    today = date.today().isoformat()
    audit_path = RESULTS_DIR / f"quality_audit_{today}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")

    return audit


# ── Merge candidate preparation ───────────────────────────────────────────────

def prepare_merge_candidates(
    results_dir: Path = RESULTS_DIR,
    min_confidence: str = "high",
) -> list[dict]:
    """Select research results ready for owner review/merge.

    Only returns high-confidence, complete results with:
    - identity confirmed
    - title_ru present
    - at least one source citation

    Does NOT write to evidence — owner must approve.
    """
    if not results_dir.exists():
        return []

    candidates: list[dict] = []

    for f in sorted(results_dir.glob("result_*.json")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue

        if r.get("confidence") != min_confidence:
            continue
        rec = r.get("final_recommendation", {})
        if r.get("parse_error"):
            continue
        has_title = bool(rec.get("title_ru"))
        has_identity = bool(rec.get("identity_confirmed"))
        has_sources = bool(r.get("sources") or rec.get("sources"))

        if has_title and has_identity and has_sources:
            candidates.append({
                "pn": r.get("entity_id"),
                "title_ru": rec.get("title_ru"),
                "description_ru": rec.get("description_ru"),
                "category": rec.get("category_suggestion"),
                "price_assessment": rec.get("price_assessment"),
                "confidence": r["confidence"],
                "source_count": len(r.get("sources") or rec.get("sources", [])),
                "result_path": str(f),
                "research_reason": r.get("research_reason"),
            })

    today = date.today().isoformat()
    candidates_path = RESULTS_DIR / f"merge_candidates_{today}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    candidates_path.write_text(
        json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Merge candidates: {len(candidates)} (confidence={min_confidence})")
    return candidates


# ── Overnight report ──────────────────────────────────────────────────────────

def generate_overnight_report(
    enrichment_before: int = 69,
    enrichment_total: int = 370,
) -> dict:
    """Aggregate overnight batch stats for owner morning review."""
    today = date.today().isoformat()

    # Enrichment stats from evidence dir
    ev_files = list(Path(RESULTS_DIR.parent / "downloads" / "evidence").glob("evidence_*.json"))
    enrichment_now = len(ev_files)

    card_status_counts: dict[str, int] = {}
    for ev_path in ev_files:
        try:
            b = json.loads(ev_path.read_text(encoding="utf-8"))
            cs = b.get("card_status", "unknown")
            card_status_counts[cs] = card_status_counts.get(cs, 0) + 1
        except Exception:
            pass

    # Research stats
    audit = audit_research_results()
    candidates = prepare_merge_candidates()
    budget_spent = _get_today_spent_usd()

    # Price sanity audit
    sanity_log = Path(RESULTS_DIR.parent / "shadow_log" / f"price_sanity_audit_{today[:7]}.jsonl")
    sanity_count = 0
    if sanity_log.exists():
        with open(sanity_log, encoding="utf-8") as f:
            sanity_count = sum(1 for line in f if line.strip())

    report = {
        "report_date": today,
        "generated_at": _now_iso(),
        "enrichment": {
            "total_sku": enrichment_total,
            "processed_before": enrichment_before,
            "processed_now": enrichment_now,
            "newly_processed": enrichment_now - enrichment_before,
            "card_status_breakdown": card_status_counts,
        },
        "research": {
            "queue_total": _count_queue(),
            "researched": audit.get("total_results", 0),
            "high_confidence": audit.get("high_confidence", 0),
            "medium_confidence": audit.get("medium_confidence", 0),
            "low_confidence": audit.get("low_confidence", 0),
            "merge_candidates": len(candidates),
            "parse_errors": audit.get("parse_errors", 0),
        },
        "price_sanity": {
            "flagged_skus": sanity_count,
        },
        "budget": {
            "daily_total_usd": round(budget_spent, 4),
            "daily_limit_usd": DAILY_BUDGET_USD,
            "remaining_usd": round(DAILY_BUDGET_USD - budget_spent, 4),
        },
        "action_items_for_owner": [
            f"Review merge candidates in research_results/merge_candidates_{today}.json",
            "Approve/reject research results before merge to evidence",
            f"Check price sanity flags in shadow_log/price_sanity_audit_{today[:7]}.jsonl",
            f"Enrichment: {enrichment_now}/{enrichment_total} SKU processed",
        ],
    }

    report_path = Path(RESULTS_DIR.parent / "shadow_log" / f"overnight_report_{today}.json")
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 60)
    print("OVERNIGHT REPORT")
    print("=" * 60)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report


def _count_queue() -> int:
    if not QUEUE_JSONL.exists():
        return 0
    with open(QUEUE_JSONL, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Research runner for enrichment gaps")
    sub = parser.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="Run batch research")
    run_p.add_argument("--max-items", type=int, default=50)
    run_p.add_argument("--priority", default="high", help="high|medium|low|all")
    run_p.add_argument("--mock", action="store_true", help="Use mock provider (no API)")

    sub.add_parser("audit", help="Audit research result quality")
    sub.add_parser("candidates", help="Show merge-ready candidates")
    sub.add_parser("report", help="Generate overnight report")

    args = parser.parse_args()

    if args.cmd == "run":
        provider = MockResearchProvider() if getattr(args, "mock", False) else None
        pfilter = None if args.priority == "all" else args.priority
        stats = run_batch_research(
            max_items=args.max_items,
            priority_filter=pfilter,
            provider=provider,
        )
        print(f"Completed: {stats['success']}/{stats['total']}")
        if stats.get("budget_stop"):
            print("Budget stop triggered.")
    elif args.cmd == "audit":
        audit = audit_research_results()
        print(json.dumps(audit, indent=2, ensure_ascii=False))
    elif args.cmd == "candidates":
        cands = prepare_merge_candidates()
        print(f"Merge-ready: {len(cands)}")
    elif args.cmd == "report":
        generate_overnight_report()
    else:
        parser.print_help()
