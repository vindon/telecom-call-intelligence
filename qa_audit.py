"""
qa_audit.py
-----------
QA audit engine for pipeline outputs.

Scoring model (100 points per call)
-------------------------------------
  Completeness  30 pts — required fields are non-null and non-empty
  Enum validity 25 pts — string fields match the allowed value set
  Consistency   25 pts — cross-field logical rules hold
  Plausibility  20 pts — numeric ranges and derived relationships are sane

Aggregate report is written to:
  outputs/qa_report_{ts}.json

Pass threshold: calls scoring < 60 are flagged as LOW_QUALITY.
A dataset is considered PASS if ≥90% of calls score ≥60.

Usage
-----
  python qa_audit.py                        # audit latest full_results_*.json
  python qa_audit.py --file outputs/full_results_combined_20260517_123456.json
  python qa_audit.py --threshold 70         # stricter pass threshold
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from pipeline.config import (
    OUTPUT_DIR,
    PHASE_RECONCILIATION_TOLERANCE_PCT,
    PHASE_RECONCILIATION_TOLERANCE_S,
    QA_HIGH_THRESHOLD,
    QA_PASS_THRESHOLD,
    TIMESTAMP_GROUND_TRUTH_TOLERANCE_PCT,
    TIMESTAMP_GROUND_TRUTH_TOLERANCE_S,
)

# ── Schema ────────────────────────────────────────────────────────────

# Fields that must be present and non-null/non-empty for a well-formed record
REQUIRED_FIELDS: list[str] = [
    "call_id",
    "total_duration_seconds",
    "total_issues_count",
    "primary_issue_resolved",
    "all_issues_resolved",
    "fcr_indicator",
    "escalation_required",
    "customer_sentiment_start",
    "customer_sentiment_end",
    "customer_sentiment_improved",
    "agent_skill_rating",
    "primary_cost_driver",
    "avoidable_call",
    "could_be_self_served",
    "agentic_ai_resolvable",
    "proactive_outreach_applicable",
    "repeat_call_risk",
    "handle_time_efficiency",
    "call_summary",
]

# Allowed values for each string enum field (None = any non-null string is OK)
ENUM_RULES: dict[str, set[str]] = {
    "channel":                         {"voice", "chat"},
    "account_type":                    {"prepaid", "postpaid", "business", "unknown"},
    "upsell_outcome":                  {"accepted", "declined", "pending", "not_attempted"},
    "upsell_scripted_or_personalized": {"scripted", "personalized", "unclear"},
    "agent_skill_rating":              {"proficient", "adequate", "needs_improvement"},
    "agent_disproportionate_time_phase": {
        "welcome", "discovery", "diagnosis", "resolution", "none",
    },
    "customer_sentiment_start":        {"positive", "neutral", "negative", "frustrated", "distressed"},
    "customer_sentiment_end":          {"positive", "neutral", "negative", "frustrated", "distressed"},
    "repeat_call_risk":                {"high", "medium", "low"},
    "self_serve_channel_applicable":   {"IVR", "app", "website", "chatbot", "none"},
    "primary_cost_driver":             {
        "billing", "technical", "plan_change", "device", "information_only", "complaint",
    },
    "handle_time_efficiency":          {"efficient", "average", "inefficient"},
    **{f"issue_{i}_category": {
        "billing", "technical", "plan", "account",
        "device", "information", "complaint", "other",
    } for i in range(1, 6)},
    **{f"issue_{i}_resolution_method": {
        "agent_action", "self_serve_guidance", "escalated", "workaround", "unresolved",
    } for i in range(1, 6)},
}

# Phases that are contiguous, non-overlapping segments of wall-clock time —
# their start/end timestamps chain end-to-end (welcome_start == call_start,
# welcome_end == discovery_start, ..., closing_end == call_end) and must sum
# to total_duration_seconds. Hold is included: the LLM is instructed to fold
# hold time into whichever phase it interrupted, not report it as additional
# time (prompts/system_prompt.txt rule 3) — confirmed against 200 real
# 2026-08-09 extractions: every record with hold_total>0 still had its 6
# sequential fields sum exactly to total.
SEQUENTIAL_PHASE_FIELDS: list[str] = [
    "phase_welcome_duration_seconds",
    "phase_discovery_duration_seconds",
    "phase_diagnosis_duration_seconds",
    "phase_resolution_duration_seconds",
    "phase_hold_total_seconds",
    "phase_closing_duration_seconds",
]

# Phases that describe activity happening DURING a sequential phase (an
# upsell pitch mid-diagnosis, an empathetic aside mid-discovery) — not
# additional wall-clock time. Do NOT include these in a sum against
# total_duration_seconds: confirmed against 200 real 2026-08-09 extractions
# that the LLM already reports these as overlapping with the sequential
# timeline (e.g. phase_upsell_start/end identical to the enclosing phase's
# range) — summing them in produced false-positive reconciliation failures
# on ~73% of otherwise-correct records.
OVERLAY_PHASE_FIELDS: list[str] = [
    "phase_upsell_duration_seconds",
    "phase_relationship_building_duration_seconds",
]

# All named phase-duration fields from the extraction schema (prompts/system_prompt.txt).
# Used by score_plausibility() (non-negativity applies to every phase field
# regardless of category). Keep in sync with the OUTPUT JSON SCHEMA phase block.
PHASE_DURATION_FIELDS: list[str] = SEQUENTIAL_PHASE_FIELDS + OVERLAY_PHASE_FIELDS


# ── Scoring functions ─────────────────────────────────────────────────

def _is_null(val) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and val.lower() in {"null", "none", "nan", ""}:
        return True
    return False


def score_completeness(record: dict) -> tuple[float, list[str]]:
    """30 pts: required fields present and non-null."""
    issues: list[str] = []
    missing = 0
    for field in REQUIRED_FIELDS:
        if _is_null(record.get(field)):
            missing += 1
            issues.append(f"missing: {field}")

    score = round((len(REQUIRED_FIELDS) - missing) / len(REQUIRED_FIELDS) * 30, 1)
    return score, issues


def score_enum_validity(record: dict) -> tuple[float, list[str]]:
    """25 pts: string enum fields match their allowed value sets."""
    issues:  list[str] = []
    checked = 0
    invalid = 0

    for field, allowed in ENUM_RULES.items():
        val = record.get(field)
        if _is_null(val):
            continue   # null/missing is handled by completeness check
        checked += 1
        if str(val) not in allowed:
            invalid += 1
            issues.append(f"invalid {field}='{val}' (allowed: {sorted(allowed)})")

    if checked == 0:
        return 25.0, []   # no enum fields present → neutral

    score = round((checked - invalid) / checked * 25, 1)
    return score, issues


def score_consistency(record: dict) -> tuple[float, list[str]]:
    """25 pts: cross-field logical rules."""
    penalties: list[str] = []
    max_pts = 25
    deduct  = 0

    # Rule 1: FCR requires no escalation (can't have both)
    if record.get("fcr_indicator") is True and record.get("escalation_required") is True:
        deduct += 10
        penalties.append("fcr_indicator=true conflicts with escalation_required=true")

    # Rule 2: upsell_outcome must match upsell_attempted
    attempted = record.get("upsell_attempted")
    outcome   = record.get("upsell_outcome")
    if attempted is False and not _is_null(outcome) and str(outcome) in {"accepted", "declined", "pending"}:
        deduct += 8
        penalties.append(
            f"upsell_attempted=false but upsell_outcome='{outcome}'"
        )

    # Rule 3: If total_issues_count > 0, issue_1_description should exist
    issue_count = record.get("total_issues_count", 0)
    try:
        issue_count = int(issue_count)
    except (TypeError, ValueError):
        issue_count = 0

    if issue_count > 0 and _is_null(record.get("issue_1_description")):
        deduct += 7
        penalties.append(
            f"total_issues_count={issue_count} but issue_1_description is null"
        )

    # Rule 4: all_issues_resolved=true and repeat_call_risk=high is contradictory
    if record.get("all_issues_resolved") is True and record.get("repeat_call_risk") == "high":
        deduct += 5
        penalties.append("all_issues_resolved=true conflicts with repeat_call_risk='high'")

    # Rule 5: could_be_self_served=true requires a channel
    if record.get("could_be_self_served") is True:
        channel = record.get("self_serve_channel_applicable")
        if _is_null(channel) or str(channel).lower() == "none":
            deduct += 5
            penalties.append(
                "could_be_self_served=true but self_serve_channel_applicable is null/none"
            )

    score = max(0.0, round(max_pts - deduct, 1))
    return score, penalties


def score_plausibility(record: dict) -> tuple[float, list[str]]:
    """20 pts: numeric ranges and derived sanity checks."""
    issues:  list[str] = []
    max_pts  = 20
    deduct   = 0

    # Duration in plausible range [30s, 7200s]
    duration = record.get("total_duration_seconds")
    if not _is_null(duration):
        try:
            d = float(duration)
            if d < 30:
                deduct += 5
                issues.append(f"total_duration_seconds={d} < 30s (implausibly short)")
            elif d > 7200:
                deduct += 4
                issues.append(f"total_duration_seconds={d} > 7200s (2h — implausibly long)")
        except (TypeError, ValueError):
            deduct += 5
            issues.append(f"total_duration_seconds='{duration}' is not numeric")

    # Hold count non-negative
    hold_count = record.get("hold_count", 0)
    try:
        if int(hold_count) < 0:
            deduct += 3
            issues.append(f"hold_count={hold_count} < 0")
    except (TypeError, ValueError):
        pass

    # Empathy statements non-negative
    empathy = record.get("agent_empathy_statements_count", 0)
    try:
        if int(empathy) < 0:
            deduct += 3
            issues.append(f"agent_empathy_statements_count={empathy} < 0")
    except (TypeError, ValueError):
        pass

    # Issue count in [0, 5]
    try:
        ic = int(record.get("total_issues_count", 0))
        if not (0 <= ic <= 5):
            deduct += 4
            issues.append(f"total_issues_count={ic} outside [0,5]")
    except (TypeError, ValueError):
        pass

    # Phase durations non-negative
    neg_phases = []
    for col in PHASE_DURATION_FIELDS:
        val = record.get(col)
        if not _is_null(val):
            try:
                if float(val) < 0:
                    neg_phases.append(col)
            except (TypeError, ValueError):
                pass
    if neg_phases:
        deduct += min(5, len(neg_phases) * 2)
        issues.append(f"negative phase durations: {', '.join(neg_phases)}")

    score = max(0.0, round(max_pts - deduct, 1))
    return score, issues


# ── Data quality gate (deterministic, non-LLM) ─────────────────────────
#
# These checks are kept separate from the 100-pt QA score above: a phase-sum
# or timestamp mismatch is a data-integrity fact (pass/fail), not a quality
# nuance to blend into a weighted score. QualityAgent runs both per call and
# excludes failures from aggregation the same way LOW-grade QA records are
# excluded — see CLAUDE.md's "What success looks like" data-quality disclaimer.

def _to_float(val) -> float | None:
    if _is_null(val):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def check_phase_reconciliation(record: dict) -> dict:
    """
    Regression check: sum of the 6 SEQUENTIAL phases (welcome, discovery,
    diagnosis, resolution, hold, closing) must not exceed total_duration_seconds
    (within a small tolerance for LLM rounding). Missing/null phase fields
    count as 0.

    OVERLAY_PHASE_FIELDS (upsell, relationship_building) are deliberately
    excluded from this sum — they describe activity happening DURING a
    sequential phase, not additional wall-clock time. Confirmed against 200
    real 2026-08-09 extractions: summing all 8 fields produced false-positive
    failures on ~73% of records whose 6 sequential fields already summed
    exactly to total. See check_overlay_plausibility() for their own bound.

    Returns:
        {"passed": bool, "phase_sum_s": float, "total_duration_s": float | None,
         "tolerance_s": float, "delta_s": float}
    """
    total = _to_float(record.get("total_duration_seconds"))
    phase_sum = sum(
        (_to_float(record.get(field)) or 0.0) for field in SEQUENTIAL_PHASE_FIELDS
    )

    if total is None:
        # No total to reconcile against — not this check's failure mode
        # (score_completeness already penalises a missing total_duration_seconds).
        return {
            "passed": True, "phase_sum_s": round(phase_sum, 1),
            "total_duration_s": None, "tolerance_s": 0.0, "delta_s": 0.0,
        }

    tolerance = max(PHASE_RECONCILIATION_TOLERANCE_S, PHASE_RECONCILIATION_TOLERANCE_PCT * total)
    delta = phase_sum - total
    passed = delta <= tolerance + 1e-9  # float-precision guard at the exact boundary

    return {
        "passed":           passed,
        "phase_sum_s":      round(phase_sum, 1),
        "total_duration_s": round(total, 1),
        "tolerance_s":      round(tolerance, 1),
        "delta_s":          round(delta, 1),
    }


def check_overlay_plausibility(record: dict) -> dict:
    """
    Lightweight sanity bound for OVERLAY_PHASE_FIELDS (upsell,
    relationship_building): each can't individually exceed
    total_duration_seconds — you can't have more upsell-pitch time than the
    call lasted. This is NOT a reconciliation (they're allowed, expected, to
    overlap with the sequential phases) — just a bound against nonsense
    values. Warning-level signal only; does not gate _dq_gate_passed.

    Returns:
        {"passed": bool, "violations": list[str]}
    """
    total = _to_float(record.get("total_duration_seconds"))
    if total is None:
        return {"passed": True, "violations": []}

    violations = []
    for field in OVERLAY_PHASE_FIELDS:
        val = _to_float(record.get(field))
        if val is not None and val > total + 1e-9:
            violations.append(f"{field}={val}s exceeds total_duration_seconds={total}s")

    return {"passed": not violations, "violations": violations}


def check_timestamp_ground_truth(record: dict) -> dict:
    """
    Cross-checks the LLM's total_duration_seconds against raw_duration_seconds —
    the actual first-to-last-turn span from the source dataset's own timestamps
    (see pipeline/hf_loader.py::_build_transcripts). Skips (passes) when no
    ground-truth duration is available, e.g. an enterprise source that doesn't
    supply per-turn timestamps.

    Returns:
        {"passed": bool, "total_duration_s": float | None,
         "raw_duration_s": float | None, "tolerance_s": float, "delta_s": float}
    """
    total = _to_float(record.get("total_duration_seconds"))
    raw   = _to_float(record.get("_raw_duration_seconds"))

    if total is None or raw is None:
        return {
            "passed": True, "total_duration_s": total,
            "raw_duration_s": raw, "tolerance_s": 0.0, "delta_s": 0.0,
        }

    tolerance = max(TIMESTAMP_GROUND_TRUTH_TOLERANCE_S, TIMESTAMP_GROUND_TRUTH_TOLERANCE_PCT * raw)
    delta = abs(total - raw)
    passed = delta <= tolerance + 1e-9  # float-precision guard at the exact boundary

    return {
        "passed":           passed,
        "total_duration_s": round(total, 1),
        "raw_duration_s":   round(raw, 1),
        "tolerance_s":      round(tolerance, 1),
        "delta_s":          round(delta, 1),
    }


# Weak, free-to-compute completeness signal: a call transcript that ends
# without any closing-phrase pattern in its final turns was plausibly cut
# off before a resolution/closing phase. Corroborating evidence only — the
# LLM-graded transcript_truncated field (prompts/system_prompt.txt) is the
# primary signal used by check_transcript_completeness() below. Shared by
# DataIngestionAgent (live pipeline) and retroactive_dq_audit.py (historical
# runs that predate the transcript_truncated schema field and have no
# primary signal to fall back on).
CLOSING_PATTERNS = (
    "thank you for calling", "thanks for calling", "have a great day",
    "have a good day", "anything else i can help", "anything else i can do",
    "is there anything else", "goodbye", "bye now", "take care",
    "reference number", "have a nice day",
)


def looks_truncated_heuristic(transcript_text: str, tail_turns: int = 3) -> bool:
    """Heuristic: True if none of the last `tail_turns` lines contain a closing phrase."""
    lines = [ln for ln in transcript_text.strip().splitlines() if ln.strip()]
    tail = " ".join(lines[-tail_turns:]).lower()
    return not any(pattern in tail for pattern in CLOSING_PATTERNS)


def check_transcript_completeness(record: dict) -> dict:
    """
    Surfaces the LLM-graded transcript_truncated field (schema fields added
    to prompts/system_prompt.txt) as a pass/fail data-quality check. A
    transcript the model judged truncated produces unreliable phase economics
    even though extraction otherwise "succeeded".

    Returns:
        {"passed": bool, "truncated": bool, "reason": str | None}
    """
    truncated_raw = record.get("transcript_truncated")
    truncated = str(truncated_raw).strip().lower() == "true" if not _is_null(truncated_raw) else False

    return {
        "passed":    not truncated,
        "truncated": truncated,
        "reason":    record.get("truncation_reason") if truncated else None,
    }


def check_data_quality(record: dict) -> dict:
    """
    Runs all deterministic data-quality checks and returns a combined
    verdict. Called once per record by QualityAgent.

    check_overlay_plausibility() is included for visibility (surfaced in
    decision-log evidence and retroactive audits) but is intentionally never
    added to `failures` / never affects `passed` — overlap between upsell or
    relationship-building time and the sequential phases is expected, not a
    data-integrity fault; only a value that individually exceeds the whole
    call is worth flagging, and only as a warning signal.

    Returns:
        {"passed": bool, "failures": list[str], "checks": {...}}
    """
    phase_check      = check_phase_reconciliation(record)
    timestamp_check  = check_timestamp_ground_truth(record)
    truncation_check = check_transcript_completeness(record)
    overlay_check    = check_overlay_plausibility(record)

    failures: list[str] = []
    if not phase_check["passed"]:
        failures.append("phase_reconciliation")
    if not timestamp_check["passed"]:
        failures.append("timestamp_ground_truth")
    if not truncation_check["passed"]:
        failures.append("transcript_truncation")

    return {
        "passed":   not failures,
        "failures": failures,
        "checks": {
            "phase_reconciliation":   phase_check,
            "timestamp_ground_truth": timestamp_check,
            "transcript_truncation":  truncation_check,
            "overlay_plausibility":   overlay_check,
        },
    }


# ── Per-call audit ────────────────────────────────────────────────────

def audit_record(record: dict) -> dict:
    """Compute QA scores for a single result record."""
    c_score, c_issues = score_completeness(record)
    e_score, e_issues = score_enum_validity(record)
    x_score, x_issues = score_consistency(record)
    p_score, p_issues = score_plausibility(record)

    total = round(c_score + e_score + x_score + p_score, 1)

    return {
        "call_id":             str(record.get("call_id", "UNKNOWN")),
        "total_score":         total,
        "grade": (
            "HIGH"   if total >= QA_HIGH_THRESHOLD else
            "MEDIUM" if total >= QA_PASS_THRESHOLD else
            "LOW"
        ),
        "dimension_scores": {
            "completeness":  c_score,
            "enum_validity": e_score,
            "consistency":   x_score,
            "plausibility":  p_score,
        },
        "issues": {
            "completeness":  c_issues,
            "enum_validity": e_issues,
            "consistency":   x_issues,
            "plausibility":  p_issues,
        },
        "total_issues": len(c_issues) + len(e_issues) + len(x_issues) + len(p_issues),
    }


# ── Aggregate QA report ───────────────────────────────────────────────

def build_report(
    results: list[dict],
    source_file: str,
    pass_threshold: int = QA_PASS_THRESHOLD,
) -> dict:
    """Generate the full QA report from audited records."""
    audited   = [audit_record(r) for r in results]
    n         = len(audited)
    scores    = [a["total_score"] for a in audited]

    high   = sum(1 for a in audited if a["grade"] == "HIGH")
    medium = sum(1 for a in audited if a["grade"] == "MEDIUM")
    low    = sum(1 for a in audited if a["grade"] == "LOW")

    avg_score   = round(sum(scores) / n, 1) if n else 0
    pass_rate   = round(sum(1 for s in scores if s >= pass_threshold) / n * 100, 1) if n else 0
    dataset_pass = pass_rate >= 90.0

    # Average per-dimension scores
    avg_dims = {
        dim: round(
            sum(a["dimension_scores"][dim] for a in audited) / n, 1
        )
        for dim in ("completeness", "enum_validity", "consistency", "plausibility")
    }

    # Most common issues
    all_issues: list[str] = []
    for a in audited:
        for dim_issues in a["issues"].values():
            all_issues.extend(dim_issues)

    issue_freq: dict[str, int] = {}
    for issue in all_issues:
        # Normalise to first 60 chars to group similar messages
        key = issue[:60]
        issue_freq[key] = issue_freq.get(key, 0) + 1

    top_issues = sorted(issue_freq.items(), key=lambda x: x[1], reverse=True)[:15]

    # Low-quality call IDs for targeted review
    low_quality_ids = [a["call_id"] for a in audited if a["grade"] == "LOW"]

    return {
        "qa_report_timestamp":  datetime.now().isoformat(),
        "source_file":          source_file,
        "total_calls_audited":  n,
        "pass_threshold":       pass_threshold,
        "dataset_verdict":      "PASS" if dataset_pass else "FAIL",
        "summary": {
            "avg_score":          avg_score,
            "pass_rate_pct":      pass_rate,
            "grade_HIGH":         high,
            "grade_MEDIUM":       medium,
            "grade_LOW":          low,
            "pct_HIGH":           round(high   / n * 100, 1) if n else 0,
            "pct_MEDIUM":         round(medium / n * 100, 1) if n else 0,
            "pct_LOW":            round(low    / n * 100, 1) if n else 0,
        },
        "avg_dimension_scores":   avg_dims,
        "top_issues":             [{"pattern": k, "count": v} for k, v in top_issues],
        "low_quality_call_ids":   low_quality_ids,
        "per_call_scores":        [
            {
                "call_id":    a["call_id"],
                "score":      a["total_score"],
                "grade":      a["grade"],
                "n_issues":   a["total_issues"],
                "dimensions": a["dimension_scores"],
            }
            for a in audited
        ],
        "per_call_detail":        audited,
    }


# ── Main ──────────────────────────────────────────────────────────────

def _latest_results_file() -> Path | None:
    """Return the most recent full_results_*.json (combined preferred)."""
    combined = sorted(OUTPUT_DIR.glob("full_results_combined_*.json"))
    if combined:
        return combined[-1]
    batch = sorted(OUTPUT_DIR.glob("full_results_[0-9]*.json"))
    return batch[-1] if batch else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Telecom Call Intelligence — QA audit engine"
    )
    parser.add_argument(
        "--file", type=str, default=None,
        help="Path to full_results JSON to audit (default: latest in outputs/)",
    )
    parser.add_argument(
        "--threshold", type=int, default=QA_PASS_THRESHOLD,
        help="Minimum score to count as 'passing' (default: 60)",
    )
    args = parser.parse_args()

    print("\n" + "═" * 60)
    print("  QA AUDIT — Telecom Call Intelligence")
    print("═" * 60)

    if args.file:
        source = Path(args.file)
    else:
        source = _latest_results_file()

    if source is None or not source.exists():
        print("\n  ✗ No results file found.")
        print("    Run run_pipeline.py or merge_outputs.py first.")
        return

    print(f"\n  Source file   : {source}")
    print(f"  Pass threshold: {args.threshold} / 100")

    with open(source, encoding="utf-8") as fh:
        results = json.load(fh)

    if not isinstance(results, list) or not results:
        print("\n  ✗ Source file is empty or not a list of records.")
        return

    print(f"  Records loaded: {len(results)}")
    print("\n  Running audit …")

    report = build_report(results, str(source), args.threshold)

    # ── Console summary ───────────────────────────────────────────────
    summary = report["summary"]
    dims    = report["avg_dimension_scores"]
    verdict = report["dataset_verdict"]

    print(f"\n  {'─' * 50}")
    print(f"  VERDICT          : {'✓ PASS' if verdict == 'PASS' else '✗ FAIL'}  "
          f"(pass_rate={summary['pass_rate_pct']}%  ≥90% required)")
    print(f"  {'─' * 50}")
    print(f"  Avg QA score     : {summary['avg_score']} / 100")
    print(f"  Grade breakdown  : HIGH {summary['grade_HIGH']}  "
          f"({summary['pct_HIGH']}%)   "
          f"MEDIUM {summary['grade_MEDIUM']}  ({summary['pct_MEDIUM']}%)   "
          f"LOW {summary['grade_LOW']}  ({summary['pct_LOW']}%)")
    print("\n  Dimension averages:")
    print(f"    Completeness   : {dims['completeness']:5.1f} / 30")
    print(f"    Enum validity  : {dims['enum_validity']:5.1f} / 25")
    print(f"    Consistency    : {dims['consistency']:5.1f} / 25")
    print(f"    Plausibility   : {dims['plausibility']:5.1f} / 20")

    if report["top_issues"]:
        print("\n  Top issues:")
        for item in report["top_issues"][:8]:
            print(f"    [{item['count']:>3}x]  {item['pattern']}")

    if report["low_quality_call_ids"]:
        sample = report["low_quality_call_ids"][:5]
        suffix = f" … (+{len(report['low_quality_call_ids']) - 5} more)" \
                 if len(report["low_quality_call_ids"]) > 5 else ""
        print(f"\n  LOW quality calls : {', '.join(str(c)[:12] for c in sample)}{suffix}")

    # ── Write report ──────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(exist_ok=True)
    ts           = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path  = OUTPUT_DIR / f"qa_report_{ts}.json"

    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print(f"\n  ✓ QA report written: {report_path}\n")


if __name__ == "__main__":
    main()
