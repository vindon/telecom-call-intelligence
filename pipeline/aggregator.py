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

import pandas as pd

from pipeline.config import EXTRACTION_MODEL
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


def _segment_masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    """
    Per-call boolean masks for the mutually-exclusive Prevent / Automate /
    Human segmentation, shared by _resolution_segments() (overall %) and
    _category_resolution_breakdown() (per issue-category breakdown).

    could_be_self_served, agentic_ai_resolvable, and
    proactive_outreach_applicable are independent per-call flags and can
    co-occur — summing their marginal percentages overstates automation
    coverage (and can exceed 100%). This applies a priority order so every
    call lands in exactly one bucket:

      1. PREVENT   — proactive outreach would have stopped the call
      2. AUTOMATE  — self-serve or agentic AI could resolve it
      3. HUMAN     — none of the above

    AUTOMATE is further split into self-serve vs full-agentic (self-serve
    takes priority when both apply) so the two segments sum exactly to
    the automate total.
    """
    def _flag(col: str) -> pd.Series:
        if col not in df.columns:
            return pd.Series(False, index=df.index)
        return df[col].eq(True)

    proactive  = _flag("proactive_outreach_applicable")
    self_serve = _flag("could_be_self_served")
    agentic    = _flag("agentic_ai_resolvable")

    prevent  = proactive
    automate = ~prevent & (self_serve | agentic)
    human    = ~prevent & ~automate

    return {
        "prevent":             prevent,
        "automate_self_serve": automate & self_serve,
        "automate_agentic":    automate & ~self_serve,
        "human":               human,
    }


def _resolution_segments(df: pd.DataFrame, n: int) -> dict:
    """Roll _segment_masks() up into overall percentages (sums to 100%)."""
    if n == 0:
        return {
            "prevent_pct": 0.0, "automate_pct": 0.0, "human_required_pct": 0.0,
            "automate_self_serve_pct": 0.0, "automate_agentic_pct": 0.0,
        }

    masks = _segment_masks(df)
    automate = masks["automate_self_serve"] | masks["automate_agentic"]

    return {
        "prevent_pct":             round(masks["prevent"].sum() / n * 100, 1),
        "automate_pct":            round(automate.sum() / n * 100, 1),
        "human_required_pct":      round(masks["human"].sum() / n * 100, 1),
        "automate_self_serve_pct": round(masks["automate_self_serve"].sum() / n * 100, 1),
        "automate_agentic_pct":    round(masks["automate_agentic"].sum()    / n * 100, 1),
    }


# Segment keys in display priority order — Prevent, then the two Automate
# sub-segments, then Human. Shared by _category_resolution_breakdown().
_SEGMENT_KEYS = ["prevent", "automate_self_serve", "automate_agentic", "human"]


def _category_resolution_breakdown(df: pd.DataFrame, n: int, baseline_monthly_cost: float) -> dict:
    """
    Cross-tab of issue_1_category x resolution segment (Prevent / Automate /
    Human) x issue_1_resolution_method — "what call type, what did the agent
    actually do, and which segment does that fall into" for the Section 6
    issue-tree view.

    build_queue ranks the Prevent and Automate opportunities (the segments
    that translate into a concrete build) across all categories by monthly
    $ impact and returns the top 4 — the recommended build order.
    """
    if (
        n == 0
        or "issue_1_category" not in df.columns
        or "issue_1_resolution_method" not in df.columns
    ):
        return {"categories": [], "build_queue": []}

    cat = df["issue_1_category"].astype(str).str.strip()
    valid = cat.str.lower().isin({"null", "none", "nan", ""}).eq(False)
    if not valid.any():
        return {"categories": [], "build_queue": []}

    masks   = _segment_masks(df)
    methods = df["issue_1_resolution_method"]

    categories: list[dict] = []
    build_queue: list[dict] = []

    for category, c_count in cat[valid].value_counts().items():
        in_cat = valid & cat.eq(category)
        c_count = int(c_count)

        segments: dict = {}
        for seg_key in _SEGMENT_KEYS:
            seg_mask  = in_cat & masks[seg_key]
            seg_count = int(seg_mask.sum())
            if seg_count == 0:
                continue
            segments[seg_key] = {
                "count":   seg_count,
                "pct":     round(seg_count / c_count * 100, 1),
                "methods": {
                    str(k): int(v)
                    for k, v in methods[seg_mask].dropna().value_counts().items()
                },
            }

        categories.append({
            "category": category,
            "count":    c_count,
            "pct":      round(c_count / n * 100, 1),
            "dollars":  round(baseline_monthly_cost * c_count / n),
            "segments": segments,
        })

        if "prevent" in segments:
            seg = segments["prevent"]
            build_queue.append({
                "category":       category,
                "segment":        "prevent",
                "count":          seg["count"],
                "pct":            seg["pct"],
                "dollars":        round(baseline_monthly_cost * seg["count"] / n),
                "category_count": c_count,
                "methods":        seg["methods"],
            })

        ss = segments.get("automate_self_serve")
        ai = segments.get("automate_agentic")
        if ss or ai:
            ss_count   = ss["count"] if ss else 0
            ai_count   = ai["count"] if ai else 0
            auto_count = ss_count + ai_count

            combined_methods: dict = {}
            for seg in (ss, ai):
                if not seg:
                    continue
                for m, c in seg["methods"].items():
                    combined_methods[m] = combined_methods.get(m, 0) + c

            build_queue.append({
                "category":        category,
                "segment":         "automate",
                "count":           auto_count,
                "pct":             round(auto_count / c_count * 100, 1),
                "dollars":         round(baseline_monthly_cost * auto_count / n),
                "category_count":  c_count,
                "self_serve_count": ss_count,
                "agentic_count":    ai_count,
                "methods":          combined_methods,
            })

    build_queue.sort(key=lambda item: item["dollars"], reverse=True)
    return {"categories": categories, "build_queue": build_queue[:4]}


# Phase groupings for the "Cost to Serve / Sell / Retain" P&L lens.
# P1-P4 (Welcome -> Resolution) is the core problem-solving work = Serve.
# P5 (Upsell) is revenue-generating = Sell.
# Hold + Closing is cross-cutting dead time/overhead = Retain.
_PHASE_PNL_GROUPS = {
    "serve":  ["Welcome & Auth", "Discovery", "Diagnosis", "Resolution"],
    "sell":   ["Upsell"],
    "retain": ["Hold", "Closing"],
}

# Phases worth drilling into for the "which intents drive this phase" view.
# Welcome/Hold/Closing are overhead phases with little intent-driven variance.
_DRILLDOWN_PHASE_COLS = {
    "Discovery":  "phase_discovery_duration_seconds",
    "Diagnosis":  "phase_diagnosis_duration_seconds",
    "Resolution": "phase_resolution_duration_seconds",
    "Upsell":     "phase_upsell_duration_seconds",
}


def _phase_pnl(phase_avg_seconds: dict, baseline_monthly_cost: float) -> dict:
    """
    Allocate the monthly cost baseline across Serve/Sell/Retain in proportion
    to average phase duration — a time-based P&L, distinct from the
    issue-category-based cost_levers above.
    """
    total = sum(phase_avg_seconds.values()) or 1
    out = {}
    for bucket, phase_names in _PHASE_PNL_GROUPS.items():
        secs = sum(phase_avg_seconds.get(p, 0.0) for p in phase_names)
        pct  = round(secs / total * 100, 1)
        out[f"{bucket}_time_pct"] = pct
        out[f"{bucket}_cost_usd"] = round(baseline_monthly_cost * pct / 100)
    return out


def _phase_drilldown(df: pd.DataFrame, n: int) -> dict:
    """
    For each cost-bearing phase, rank issue_1_category by average phase
    duration — "which intents drive this phase's handle time" — and report
    the stall rate (agent_disproportionate_time_phase == this phase) per
    intent. Top 5 intents per phase.
    """
    if n == 0 or "issue_1_category" not in df.columns:
        return {phase: [] for phase in _DRILLDOWN_PHASE_COLS}

    cat = df["issue_1_category"].astype(str).str.strip()
    valid = cat.str.lower().isin({"null", "none", "nan", ""}).eq(False)
    disp_col = "agent_disproportionate_time_phase"

    out = {}
    for phase, col in _DRILLDOWN_PHASE_COLS.items():
        if col not in df.columns:
            out[phase] = []
            continue

        grouped = df.loc[valid].groupby(cat[valid])[col].agg(["mean", "count"])
        if disp_col in df.columns:
            stall_flag = df[disp_col].astype(str).str.lower().eq(phase.lower())
            stall = stall_flag[valid].groupby(cat[valid]).mean() * 100
        else:
            stall = pd.Series(0.0, index=grouped.index)

        rows = []
        for intent, row in grouped.sort_values("mean", ascending=False).head(5).iterrows():
            rows.append({
                "intent":      intent,
                "avg_seconds": round(float(row["mean"]), 1),
                "calls":       int(row["count"]),
                "stall_pct":   round(float(stall.get(intent, 0.0)), 1),
            })
        out[phase] = rows
    return out


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

    # Mutually-exclusive resolution segmentation (sums to 100%) — see
    # _resolution_segments() docstring for why this can't be derived from
    # the marginal *_pct fields above.
    kpis.update(_resolution_segments(df, n))

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

    # Savings are computed from the non-overlapping resolution segments
    # (kpis["automate_self_serve_pct"] etc.), not the marginal *_pct
    # fields — those overlap and would double-count savings.
    baseline     = MONTHLY_VOLUME * COST_PER_CALL_USD
    ss_savings   = baseline * (kpis["automate_self_serve_pct"] / 100) * 0.85
    ai_savings   = baseline * (kpis["automate_agentic_pct"]    / 100) * 0.70
    pro_savings  = baseline * (kpis["prevent_pct"]             / 100) * 0.60
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

    # Phase-time-based Cost to Serve/Sell/Retain P&L — a different lens
    # from the issue-category-based savings above (see _phase_pnl).
    cost_levers.update(_phase_pnl(phase_avg_seconds, baseline))

    # ── Inference cost ────────────────────────────────────────────────
    token_usage = build_token_summary(results)

    return {
        "meta": {
            "total_calls_analyzed":  n,
            "analysis_timestamp":    datetime.now().isoformat(),
            "dataset":               "talkmap/telecom-conversation-corpus",
            "model":                 EXTRACTION_MODEL,
            "inference_provider":    "Anthropic (Claude)" if EXTRACTION_MODEL.startswith("claude") else "Google AI Studio",
            "cost_benchmark_note": (
                "Cost estimates use $6.00/call industry benchmark. "
                "Replace with actual ACD data for production."
            ),
        },
        "kpis":              kpis,
        "phase_avg_seconds": phase_avg_seconds,
        "phase_drilldown":   _phase_drilldown(df, n),
        "distributions":     distributions,
        "cost_levers":       cost_levers,
        "issue_breakdown":   _category_resolution_breakdown(df, n, baseline),
        "token_usage":       token_usage,
    }
