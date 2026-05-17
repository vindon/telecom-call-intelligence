"""
aggregator.py  —  Node 4: Aggregate
--------------------------------------
Computes all executive KPIs, distributions, and cost-lever estimates
from the list of per-call JSON results produced by analyzer.py.

Cost model
----------
All monetary estimates use $6.00/call as the industry benchmark for
telecom contact center cost-to-serve. Replace with actual ACD data
in production — values here are clearly labelled as estimates.

Token usage
-----------
token_summary() is called here so the aggregated metrics include
a full inference cost breakdown alongside the business KPIs.
"""

from datetime import datetime

import numpy as np
import pandas as pd

from pipeline.token_tracker import token_summary as build_token_summary

# ── Industry benchmark — replace with actual cost data ────────────────
COST_PER_CALL_USD = 6.00

# Phase columns in display order (label, DataFrame column)
PHASE_COLS = [
    ("Welcome & Auth",  "phase_welcome_duration_seconds"),
    ("Discovery",       "phase_discovery_duration_seconds"),
    ("Diagnosis",       "phase_diagnosis_duration_seconds"),
    ("Resolution",      "phase_resolution_duration_seconds"),
    ("Hold",            "phase_hold_total_seconds"),
    ("Upsell",          "phase_upsell_duration_seconds"),
    ("Closing",         "phase_closing_duration_seconds"),
]


# ── Helpers ───────────────────────────────────────────────────────────

def _pct(df: pd.DataFrame, col: str, value=True) -> float:
    if col not in df.columns or len(df) == 0:
        return 0.0
    return round(df[col].eq(value).sum() / len(df) * 100, 1)


def _avg(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns:
        return 0.0
    return round(float(df[col].dropna().mean()), 1)


def _val_pct(df: pd.DataFrame, col: str) -> dict:
    """Value counts as percentages (descending)."""
    if col not in df.columns or len(df) == 0:
        return {}
    vc    = df[col].dropna().value_counts()
    total = vc.sum()
    return {str(k): round(v / total * 100, 1) for k, v in vc.items()}


def _issue_category_counts(df: pd.DataFrame) -> dict:
    """Aggregate issue_1..5_category across all calls."""
    counts: dict = {}
    for i in range(1, 6):
        col = f"issue_{i}_category"
        if col in df.columns:
            for val in df[col].dropna():
                val = str(val).strip()
                if val and val.lower() not in {"null", "none", "nan"}:
                    counts[val] = counts.get(val, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))


# ── Main aggregation ──────────────────────────────────────────────────

def aggregate_metrics(results: list[dict]) -> dict:
    """
    Compute all dashboard metrics from per-call JSON results.

    Args:
        results: Parsed JSON dicts from analyzer.analyze_batch()

    Returns:
        Dict consumed directly by dashboard/app.py and written to summary.json.
    """
    if not results:
        raise ValueError("No results to aggregate.")

    df = pd.DataFrame(results)
    n  = len(df)

    # ── Phase averages ────────────────────────────────────────────────
    phase_avg_seconds: dict = {}
    for label, col in PHASE_COLS:
        phase_avg_seconds[label] = _avg(df, col)

    # ── Upsell conversion ─────────────────────────────────────────────
    if "upsell_attempted" in df.columns and "upsell_outcome" in df.columns:
        attempted = df[df["upsell_attempted"].eq(True)]
        upsell_conversion = (
            round((attempted["upsell_outcome"] == "accepted").sum() / len(attempted) * 100, 1)
            if len(attempted) > 0 else 0.0
        )
    else:
        upsell_conversion = 0.0

    # ── Top-line KPIs ─────────────────────────────────────────────────
    avg_aht_s = _avg(df, "total_duration_seconds")

    kpis = {
        "total_calls_analyzed":       n,
        "avg_handle_time_seconds":    avg_aht_s,
        "avg_handle_time_minutes":    round(avg_aht_s / 60, 1),
        "fcr_rate_pct":               _pct(df, "fcr_indicator",             True),
        "avoidable_call_rate_pct":    _pct(df, "avoidable_call",            True),
        "self_serve_deflection_pct":  _pct(df, "could_be_self_served",      True),
        "agentic_ai_resolvable_pct":  _pct(df, "agentic_ai_resolvable",     True),
        "proactive_outreach_pct":     _pct(df, "proactive_outreach_applicable", True),
        "all_issues_resolved_pct":    _pct(df, "all_issues_resolved",       True),
        "escalation_rate_pct":        _pct(df, "escalation_required",       True),
        "upsell_attempted_pct":       _pct(df, "upsell_attempted",          True),
        "upsell_conversion_pct":      upsell_conversion,
        "sentiment_improved_pct":     _pct(df, "customer_sentiment_improved", True),
        "agent_tool_struggle_pct":    _pct(df, "agent_tool_struggle_detected", True),
        "multi_issue_call_pct": (
            round((df["total_issues_count"] > 1).sum() / n * 100, 1)
            if "total_issues_count" in df.columns else 0.0
        ),
        "avg_issues_per_call":        _avg(df, "total_issues_count"),
        "avg_hold_time_seconds":      _avg(df, "phase_hold_total_seconds"),
        "avg_hold_count":             _avg(df, "hold_count"),
        "avg_empathy_statements":     _avg(df, "agent_empathy_statements_count"),
    }

    # ── Distributions ─────────────────────────────────────────────────
    distributions = {
        "issue_category":               _issue_category_counts(df),
        "cost_driver":                  _val_pct(df, "primary_cost_driver"),
        "agent_skill":                  _val_pct(df, "agent_skill_rating"),
        "customer_sentiment_start":     _val_pct(df, "customer_sentiment_start"),
        "customer_sentiment_end":       _val_pct(df, "customer_sentiment_end"),
        "handle_time_efficiency":       _val_pct(df, "handle_time_efficiency"),
        "self_serve_channel":           _val_pct(df, "self_serve_channel_applicable"),
        "repeat_call_risk":             _val_pct(df, "repeat_call_risk"),
        "agent_disproportionate_phase": _val_pct(df, "agent_disproportionate_time_phase"),
        "upsell_outcome":               _val_pct(df, "upsell_outcome"),
        "resolution_method_issue1":     _val_pct(df, "issue_1_resolution_method"),
        "account_type":                 _val_pct(df, "account_type"),
    }

    # ── Cost levers ───────────────────────────────────────────────────
    # Illustrative scaling to 100K monthly calls.
    # Replace MONTHLY_VOLUME with your actual contact centre call volume.
    MONTHLY_VOLUME = 100_000

    baseline     = MONTHLY_VOLUME * COST_PER_CALL_USD
    ss_savings   = baseline * (kpis["self_serve_deflection_pct"]  / 100) * 0.85
    ai_savings   = baseline * (kpis["agentic_ai_resolvable_pct"]  / 100) * 0.70
    pro_savings  = baseline * (kpis["proactive_outreach_pct"]     / 100) * 0.60
    total_savings = ss_savings + ai_savings + pro_savings

    cost_levers = {
        "cost_per_call_usd":             COST_PER_CALL_USD,
        "monthly_volume_estimate":       MONTHLY_VOLUME,
        "baseline_monthly_cost_usd":     round(baseline),
        "self_serve_savings_usd":        round(ss_savings),
        "agentic_ai_savings_usd":        round(ai_savings),
        "proactive_care_savings_usd":    round(pro_savings),
        "total_savings_opportunity_usd": round(total_savings),
        "savings_pct_of_baseline":       round(total_savings / baseline * 100, 1),
    }

    # ── Inference cost ────────────────────────────────────────────────
    token_usage = build_token_summary(results)

    return {
        "meta": {
            "total_calls_analyzed":  n,
            "analysis_timestamp":    datetime.now().isoformat(),
            "dataset":               "talkmap/telecom-conversation-corpus",
            "model":                 "llama-3.3-70b-versatile",
            "inference_provider":    "Groq",
            "cost_benchmark_note": (
                "Cost estimates use $6.00/call industry benchmark. "
                "Replace with actual ACD data for production."
            ),
        },
        "kpis":              kpis,
        "phase_avg_seconds": phase_avg_seconds,
        "distributions":     distributions,
        "cost_levers":       cost_levers,
        "token_usage":       token_usage,
    }
