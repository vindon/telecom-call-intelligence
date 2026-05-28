"""
dashboard/app.py
----------------
Telecom Call Intelligence — Contact Segmentation & Deflection Dashboard

Run:
  streamlit run dashboard/app.py

Narrative: For every call analysed, the dashboard answers three questions for a
CX leader:
  1. Should this customer have needed to call at all? (Proactive Care)
  2. Could a digital channel or AI have resolved it?  (Self-Serve / Agentic AI)
  3. Did it genuinely require a skilled human agent?   (Human Support Required)

Loads outputs/summary.json if present.
Falls back to built-in DEMO DATA so the dashboard works on GitHub
without running the pipeline.
"""

import html
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="Telecom Call Intelligence",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styling ───────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

  html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background-color: #F1F5F9;
    color: #0F172A;
  }
  .main { background-color: #F1F5F9; }
  .block-container { padding-top: 0 !important; padding-bottom: 3rem; }

  /* ── Hero header banner ── */
  .hero-banner {
    background: linear-gradient(135deg, #0F172A 0%, #1E3A5F 60%, #1E40AF 100%);
    border-radius: 0 0 16px 16px;
    padding: 36px 40px 30px;
    margin: -1rem -1rem 0;
    position: relative;
    overflow: hidden;
  }
  .hero-banner::before {
    content: '';
    position: absolute;
    top: -60px; right: -60px;
    width: 280px; height: 280px;
    border-radius: 50%;
    background: rgba(59,130,246,0.12);
  }
  .hero-banner::after {
    content: '';
    position: absolute;
    bottom: -80px; left: 30%;
    width: 200px; height: 200px;
    border-radius: 50%;
    background: rgba(99,102,241,0.08);
  }
  .hero-title {
    font-size: 2.6rem;
    font-weight: 800;
    color: #FFFFFF;
    line-height: 1.15;
    letter-spacing: -0.02em;
    margin: 0 0 8px;
  }
  .hero-subtitle {
    font-size: 1.1rem;
    font-weight: 400;
    color: #93C5FD;
    letter-spacing: 0.01em;
    margin: 0 0 4px;
  }
  .hero-badge {
    display: inline-block;
    background: rgba(16,185,129,0.18);
    border: 1px solid rgba(16,185,129,0.45);
    border-radius: 20px;
    padding: 5px 14px;
    font-size: 0.72rem;
    font-weight: 700;
    color: #34D399;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .hero-badge.demo {
    background: rgba(99,102,241,0.18);
    border-color: rgba(99,102,241,0.45);
    color: #A5B4FC;
  }

  /* ── KPI Cards ── */
  .kpi-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-top: 4px solid #2563EB;
    border-radius: 10px;
    padding: 20px 16px 16px;
    text-align: center;
    box-shadow: 0 1px 4px rgba(15,23,42,0.07);
    transition: box-shadow 0.2s;
  }
  .kpi-card:hover { box-shadow: 0 4px 16px rgba(15,23,42,0.12); }
  .kpi-card.green  { border-top-color: #059669; }
  .kpi-card.red    { border-top-color: #DC2626; }
  .kpi-card.amber  { border-top-color: #D97706; }
  .kpi-card.purple { border-top-color: #7C3AED; }
  .kpi-card.teal   { border-top-color: #0D9488; }
  .kpi-card.indigo { border-top-color: #4F46E5; }

  .kpi-value {
    font-size: 2.6rem;
    font-weight: 800;
    line-height: 1.1;
    margin: 8px 0 5px;
    color: #0F172A;
    letter-spacing: -0.03em;
  }
  .kpi-label {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #64748B;
  }
  .kpi-delta {
    font-size: 0.72rem;
    color: #94A3B8;
    margin-top: 7px;
  }

  /* ── Section headers ── */
  .section-header {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #1E293B;
    margin: 36px 0 18px;
  }
  .section-header::after {
    content: '';
    flex: 1;
    height: 2px;
    background: linear-gradient(90deg, #E2E8F0, transparent);
  }

  /* ── Insight boxes ── */
  .insight-box {
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-left: 5px solid #2563EB;
    border-radius: 8px;
    padding: 14px 18px;
    font-size: 0.88rem;
    color: #1E3A8A;
    line-height: 1.6;
    margin: 10px 0 16px;
  }
  .insight-box.amber {
    background: #FFFBEB;
    border-color: #FDE68A;
    border-left-color: #D97706;
    color: #78350F;
  }
  .insight-box.green {
    background: #ECFDF5;
    border-color: #A7F3D0;
    border-left-color: #059669;
    color: #064E3B;
  }

  /* ── Traffic light table ── */
  .tl-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
    background: #FFFFFF;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 1px 4px rgba(15,23,42,0.07);
  }
  .tl-table thead tr {
    background: #1E293B;
    color: #E2E8F0;
  }
  .tl-table thead th {
    padding: 13px 16px;
    text-align: left;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }
  .tl-table tbody tr {
    border-bottom: 1px solid #F1F5F9;
    transition: background 0.15s;
  }
  .tl-table tbody tr:hover { background: #F8FAFC; }
  .tl-table tbody td {
    padding: 11px 16px;
    color: #1E293B;
    vertical-align: middle;
    line-height: 1.45;
  }
  .tl-table tbody td:first-child { white-space: nowrap; }

  /* ── Traffic lights ── */
  .tl-dot {
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 50%;
    vertical-align: middle;
    margin-right: 7px;
    flex-shrink: 0;
  }
  .tl-red    { background:#DC2626; box-shadow: 0 0 6px rgba(220,38,38,0.5); }
  .tl-amber  { background:#D97706; box-shadow: 0 0 6px rgba(217,119,6,0.5); }
  .tl-green  { background:#059669; box-shadow: 0 0 6px rgba(5,150,105,0.5); }

  .priority-pill {
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    white-space: nowrap;
  }
  .pill-red   { background:#FEF2F2; color:#991B1B; border:1px solid #FECACA; }
  .pill-amber { background:#FFFBEB; color:#92400E; border:1px solid #FDE68A; }
  .pill-green { background:#ECFDF5; color:#065F46; border:1px solid #6EE7B7; }

  /* ── Footer ── */
  .dash-footer {
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 6px;
    font-size: 0.7rem;
    color: #94A3B8;
    padding-top: 8px;
  }

  #MainMenu { visibility: hidden; }
  footer     { visibility: hidden; }
  header     { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Colour palette ─────────────────────────────────────────────────────
BLUE   = "#2563EB"
LBLUE  = "#3B82F6"
GREEN  = "#059669"
RED    = "#DC2626"
AMBER  = "#D97706"
PURPLE = "#7C3AED"
TEAL   = "#0D9488"
INDIGO = "#4F46E5"
SLATE  = "#64748B"

PHASE_COLORS = {
    "Welcome & Auth": LBLUE,
    "Discovery":      PURPLE,
    "Diagnosis":      RED,
    "Resolution":     GREEN,
    "Hold":           AMBER,
    "Upsell":         TEAL,
    "Closing":        SLATE,
}

PLOTLY_BASE = dict(
    paper_bgcolor="#FFFFFF",
    plot_bgcolor="#FFFFFF",
    font=dict(family="Inter, -apple-system, sans-serif", color="#334155", size=12),
    margin=dict(l=16, r=16, t=52, b=16),
    legend=dict(
        bgcolor="rgba(255,255,255,0)",
        font=dict(size=11, color="#475569"),
        orientation="h",
        yanchor="bottom", y=1.02,
        xanchor="right",  x=1,
    ),
)

# ── Industry benchmark targets ─────────────────────────────────────────
BENCHMARKS = {
    "fcr_rate_pct":             {"target": 75,  "label": "First Call Resolution",  "unit": "%",   "higher_better": True},
    "avg_handle_time_minutes":  {"target": 6.0, "label": "Avg Handle Time",        "unit": " min","higher_better": False},
    "escalation_rate_pct":      {"target": 10,  "label": "Escalation Rate",        "unit": "%",   "higher_better": False},
    "all_issues_resolved_pct":  {"target": 80,  "label": "Issues Resolved",        "unit": "%",   "higher_better": True},
    "sentiment_improved_pct":   {"target": 70,  "label": "Sentiment Improvement",  "unit": "%",   "higher_better": True},
    "agent_tool_struggle_pct":  {"target": 15,  "label": "Agent Tool Struggle",    "unit": "%",   "higher_better": False},
    "self_serve_deflection_pct":{"target": 30,  "label": "Self-Serve Eligible",    "unit": "%",   "higher_better": True},
    "agentic_ai_resolvable_pct":{"target": 40,  "label": "Agentic AI Resolvable",  "unit": "%",   "higher_better": True},
    "proactive_outreach_pct":   {"target": 20,  "label": "Proactive Outreach",     "unit": "%",   "higher_better": True},
    "avoidable_call_rate_pct":  {"target": 30,  "label": "Avoidable Call Rate",    "unit": "%",   "higher_better": True},
}

# ── Issue-to-segment routing guide (CX industry benchmarks) ───────────
# For each issue category: what % typically routes to each segment
ISSUE_ROUTING = {
    "technical":   {"proactive": 35, "digital": 20, "human": 45},
    "billing":     {"proactive": 20, "digital": 40, "human": 40},
    "plan":        {"proactive":  5, "digital": 70, "human": 25},
    "information": {"proactive":  0, "digital": 85, "human": 15},
    "account":     {"proactive": 10, "digital": 55, "human": 35},
    "device":      {"proactive":  5, "digital": 10, "human": 85},
    "complaint":   {"proactive":  0, "digital":  5, "human": 95},
    "roaming":     {"proactive": 30, "digital": 50, "human": 20},
    "other":       {"proactive":  5, "digital": 30, "human": 65},
}

# ── Demo data ─────────────────────────────────────────────────────────
DEMO_DATA = {
    "meta": {
        "total_calls_analyzed": 100,
        "analysis_timestamp": "2025-04-12T09:41:22.000000",
        "dataset": "talkmap/telecom-conversation-corpus",
        "model": "gemini-2.5-flash-lite",
        "inference_provider": "Google AI Studio",
    },
    "kpis": {
        "total_calls_analyzed": 100,
        "avg_handle_time_seconds": 524,
        "avg_handle_time_minutes": 8.7,
        "fcr_rate_pct": 68.0,
        "avoidable_call_rate_pct": 41.0,
        "self_serve_deflection_pct": 37.0,
        "agentic_ai_resolvable_pct": 29.0,
        "proactive_outreach_pct": 24.0,
        "all_issues_resolved_pct": 71.0,
        "escalation_rate_pct": 14.0,
        "upsell_attempted_pct": 52.0,
        "upsell_conversion_pct": 18.0,
        "sentiment_improved_pct": 61.0,
        "agent_tool_struggle_pct": 23.0,
        "multi_issue_call_pct": 38.0,
        "avg_issues_per_call": 1.4,
        "avg_hold_time_seconds": 87,
        "avg_hold_count": 1.2,
        "avg_empathy_statements": 3.1,
    },
    "phase_avg_seconds": {
        "Welcome & Auth": 46, "Discovery": 108, "Diagnosis": 152,
        "Resolution": 128,   "Hold": 87,        "Upsell": 44, "Closing": 54,
    },
    "distributions": {
        "issue_category": {
            "billing": 38, "technical": 31, "plan": 16,
            "account": 9,  "device": 4,    "information": 2,
        },
        "agent_skill": {
            "proficient": "44.0", "adequate": "38.0", "needs_improvement": "18.0",
        },
        "customer_sentiment_start": {
            "frustrated": "41.0", "negative": "22.0", "neutral": "28.0", "positive": "9.0",
        },
        "customer_sentiment_end": {
            "positive": "48.0", "neutral": "29.0", "negative": "15.0", "frustrated": "8.0",
        },
        "repeat_call_risk": {
            "low": "43.0", "medium": "38.0", "high": "19.0",
        },
        "agent_disproportionate_phase": {
            "none": "48.0", "diagnosis": "26.0", "discovery": "14.0", "resolution": "12.0",
        },
        "upsell_outcome": {
            "not_attempted": "48.0", "declined": "34.0", "accepted": "9.0", "pending": "9.0",
        },
    },
    "cost_levers": {
        "cost_per_call_usd":             6.0,
        "monthly_volume_estimate":       100000,
        "baseline_monthly_cost_usd":     600000,
        "self_serve_savings_usd":        188700,
        "agentic_ai_savings_usd":        121800,
        "proactive_care_savings_usd":     86400,
        "total_savings_opportunity_usd": 396900,
        "savings_pct_of_baseline":        66.2,
    },
}


# ── Data loading ──────────────────────────────────────────────────────

@st.cache_data
def load_summary() -> tuple[dict, bool]:
    path = Path("outputs/summary.json")
    if path.exists():
        with open(path) as f:
            data = json.load(f)
        if "cost_levers" not in data:
            data["cost_levers"] = _compute_cost_levers(data["kpis"])
        return data, False
    return DEMO_DATA, True


def load_run_history() -> list[dict]:
    """Return run_history from agent_memory.json, oldest-first, or [] if unavailable."""
    path = Path("outputs/agent_memory.json")
    if not path.exists():
        return []
    try:
        with open(path) as f:
            mem = json.load(f)
        runs = mem.get("run_history", [])
        for r in runs:
            ts = r.get("timestamp", "")
            if len(ts) == 15 and ts[8] == "_":
                r["_dt"] = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}"
            else:
                r["_dt"] = ts
        return sorted(runs, key=lambda r: r.get("_dt", ""))
    except Exception:
        return []


def _compute_cost_levers(kpis: dict) -> dict:
    cpp, vol = 6.0, 100_000
    base = cpp * vol
    ss   = base * kpis.get("self_serve_deflection_pct", 0) / 100
    ai   = base * kpis.get("agentic_ai_resolvable_pct",  0) / 100
    pro  = base * kpis.get("proactive_outreach_pct",     0) / 100
    tot  = ss + ai + pro
    return {
        "cost_per_call_usd": cpp, "monthly_volume_estimate": vol,
        "baseline_monthly_cost_usd": base, "self_serve_savings_usd": ss,
        "agentic_ai_savings_usd": ai, "proactive_care_savings_usd": pro,
        "total_savings_opportunity_usd": tot,
        "savings_pct_of_baseline": tot / base * 100 if base else 0,
    }


# ── Chart builders ─────────────────────────────────────────────────────

def _lay(**kw) -> dict:
    d = dict(PLOTLY_BASE)
    d.update(kw)
    return d


def _title(text: str) -> dict:
    return dict(text=text, font=dict(size=14, color="#0F172A", family="Inter"), x=0)


def chart_segment_funnel(proactive_pct: float, digital_pct: float,
                          human_pct: float, n_calls: int) -> go.Figure:
    """Stacked horizontal bar showing the 3 contact segments."""
    p_n = round(n_calls * proactive_pct / 100)
    d_n = round(n_calls * digital_pct   / 100)
    h_n = n_calls - p_n - d_n

    def _lbl(pct, n, name):
        return f"  {name}  {pct:.0f}%  ({n} calls)" if pct >= 8 else ""

    segs = [
        (f"Proactive Care — Prevent",       proactive_pct, p_n, TEAL,   "#CCFBF1"),
        (f"Self-Serve / Agentic AI — Deflect", digital_pct, d_n, PURPLE, "#EDE9FE"),
        (f"Human Support Required — Serve", human_pct,    h_n, BLUE,   "#DBEAFE"),
    ]
    fig = go.Figure()
    for name, pct, n, color, _ in segs:
        fig.add_trace(go.Bar(
            name=name,
            x=[pct], y=["Contact Volume"],
            orientation="h",
            marker_color=color, marker_line_width=0,
            text=[_lbl(pct, n, name.split("—")[0].strip())],
            textposition="inside", insidetextanchor="start",
            textfont=dict(color="white", size=11, family="Inter"),
            hovertemplate=f"<b>{name}</b><br>{pct:.1f}% of contacts ({n} calls)<extra></extra>",
        ))
    fig.update_layout(**_lay(
        title=_title(f"Contact Volume Segmentation — {n_calls:,} Calls Analysed"),
        barmode="stack",
        height=130,
        xaxis=dict(range=[0, 100], ticksuffix="%", gridcolor="#F1F5F9",
                   zeroline=False, tickfont=dict(color="#64748B", size=11)),
        yaxis=dict(showticklabels=False),
        margin=dict(l=16, r=16, t=48, b=24),
        legend=dict(orientation="h", y=-0.55, x=0, yanchor="top", xanchor="left",
                    font=dict(size=11)),
    ))
    return fig


def chart_issue_routing(issue_categories: dict) -> go.Figure:
    """Stacked horizontal bar per issue category showing proactive/digital/human split."""
    cats = [k for k in issue_categories if k in ISSUE_ROUTING]
    if not cats:
        return go.Figure()

    routing = [ISSUE_ROUTING[c] for c in cats]
    labels  = [c.capitalize() for c in cats]

    fig = go.Figure()
    for seg, color, name in [
        ("proactive", TEAL,   "Proactive Care"),
        ("digital",   PURPLE, "Self-Serve / Agentic AI"),
        ("human",     BLUE,   "Human Support Required"),
    ]:
        xs = [r[seg] for r in routing]
        fig.add_trace(go.Bar(
            name=name, y=labels, x=xs,
            orientation="h",
            marker_color=color, marker_line_width=0,
            text=[f"{x}%" if x >= 10 else "" for x in xs],
            textposition="inside", insidetextanchor="middle",
            textfont=dict(color="white", size=10),
            hovertemplate=f"<b>%{{y}}</b><br>{name}: %{{x}}%<extra></extra>",
        ))

    fig.update_layout(**_lay(
        title=_title("Resolution Pathway by Issue Type (% of each category)"),
        barmode="stack",
        height=max(260, len(cats) * 40 + 80),
        xaxis=dict(range=[0, 100], ticksuffix="%", gridcolor="#F1F5F9", zeroline=False,
                   tickfont=dict(color="#64748B", size=11)),
        yaxis=dict(tickfont=dict(size=11, color="#334155"), autorange="reversed"),
        margin=dict(l=16, r=16, t=52, b=16),
        legend=dict(orientation="h", y=-0.18, x=0, yanchor="top"),
    ))
    return fig


def chart_benchmark_bars(kpis: dict) -> go.Figure:
    """Grouped horizontal bar: Actual vs Benchmark for strategic KPIs."""
    chart_keys = [
        "fcr_rate_pct", "escalation_rate_pct", "all_issues_resolved_pct",
        "proactive_outreach_pct", "self_serve_deflection_pct", "agentic_ai_resolvable_pct",
    ]
    labels  = [BENCHMARKS[k]["label"] for k in chart_keys]
    actuals = [float(kpis.get(k, 0)) for k in chart_keys]
    targets = [float(BENCHMARKS[k]["target"]) for k in chart_keys]
    hbs     = [BENCHMARKS[k]["higher_better"]  for k in chart_keys]

    bar_colors = [
        GREEN if (a >= t) == hb else RED
        for a, t, hb in zip(actuals, targets, hbs)
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Actual", y=labels, x=actuals,
        orientation="h",
        marker_color=bar_colors, marker_line_width=0,
        text=[f"{a:.0f}%" for a in actuals],
        textposition="outside",
        textfont=dict(size=11, color="#334155"),
        hovertemplate="<b>%{y}</b><br>Actual: %{x:.1f}%<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        name="Benchmark Target",
        y=labels, x=targets,
        mode="markers",
        marker=dict(symbol="line-ns", size=22, color="#1E293B",
                    line=dict(width=3, color="#1E293B")),
        hovertemplate="<b>%{y}</b><br>Target: %{x:.1f}%<extra></extra>",
    ))
    fig.update_layout(**_lay(
        title=_title("Actual vs Industry Benchmark — 6 Strategic KPIs"),
        height=380,
        xaxis=dict(ticksuffix="%", gridcolor="#F1F5F9", zeroline=False, range=[0, 110]),
        yaxis=dict(tickfont=dict(size=11, color="#334155"), autorange="reversed"),
        margin=dict(l=16, r=60, t=52, b=16),
        legend=dict(orientation="h", y=1.12, x=0),
    ))
    return fig


def chart_phase_bar(phase_data: dict) -> go.Figure:
    phases  = list(phase_data.keys())
    seconds = [int(v) for v in phase_data.values()]
    colors  = [PHASE_COLORS.get(p, SLATE) for p in phases]
    labels  = [f"{s//60}m {s%60}s" if s >= 60 else f"{s}s" for s in seconds]

    fig = go.Figure(go.Bar(
        x=phases, y=seconds,
        marker_color=colors, marker_line_width=0,
        text=labels, textposition="outside",
        textfont=dict(size=11, color="#334155"),
        hovertemplate="<b>%{x}</b><br>%{y}s<extra></extra>",
    ))
    fig.update_layout(**_lay(
        title=_title("Average Time per Call Phase"),
        yaxis=dict(title="Seconds", gridcolor="#F1F5F9", zeroline=False,
                   tickfont=dict(color="#64748B", size=11)),
        xaxis=dict(tickfont=dict(size=11, color="#334155")),
        bargap=0.38,
    ))
    return fig


def chart_cost_waterfall(cl: dict) -> go.Figure:
    base = cl["baseline_monthly_cost_usd"]
    ss   = cl["self_serve_savings_usd"]
    ai   = cl["agentic_ai_savings_usd"]
    pro  = cl["proactive_care_savings_usd"]
    net  = base - ss - ai - pro

    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute", "relative", "relative", "relative", "total"],
        x=["Baseline\nCost", "Proactive\nCare", "Self-Serve\nDeflection",
           "Agentic AI\nAutomation", "Irreducible\nHuman Cost"],
        y=[base, -pro, -ss, -ai, net],
        connector=dict(line=dict(color="#E2E8F0", width=1.5)),
        decreasing=dict(marker_color=GREEN),
        increasing=dict(marker_color=RED),
        totals=dict(marker_color=BLUE),
        text=[f"${v/1000:.0f}K" for v in [base, pro, ss, ai, net]],
        textfont=dict(size=12, color="#0F172A"),
        hovertemplate="<b>%{x}</b><br>$%{value:,.0f}/mo<extra></extra>",
    ))
    fig.update_layout(**_lay(
        title=_title("Monthly Cost-to-Serve Waterfall  (est. 100K calls/mo)"),
        yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor="#F1F5F9",
                   zeroline=False, tickfont=dict(color="#64748B", size=11)),
        showlegend=False,
    ))
    return fig


def chart_donut(labels, values, title, colors=None) -> go.Figure:
    pal = colors or [BLUE, RED, GREEN, AMBER, PURPLE, TEAL, SLATE]
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.56,
        marker=dict(colors=pal[:len(labels)], line=dict(color="#FFFFFF", width=3)),
        textinfo="percent", textfont=dict(size=12, color="#FFFFFF"),
        hovertemplate="<b>%{label}</b><br>%{value} (%{percent})<extra></extra>",
    ))
    fig.update_layout(**_lay(
        title=_title(title),
        legend=dict(orientation="v", x=0.76, y=0.5, font=dict(size=11, color="#334155")),
        margin=dict(l=10, r=10, t=52, b=10),
    ))
    return fig


def chart_sentiment(start: dict, end: dict) -> go.Figure:
    cats  = ["positive", "neutral", "negative", "frustrated", "distressed"]
    cmap  = {"positive": GREEN, "neutral": LBLUE, "negative": AMBER,
              "frustrated": RED, "distressed": PURPLE}
    pres  = [c for c in cats if c in start or c in end]
    xl    = [c.capitalize() for c in pres]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Call Start", x=xl,
        y=[float(start.get(c, 0)) for c in pres],
        marker_color=[cmap[c] for c in pres], marker_line_width=0, opacity=0.3,
        hovertemplate="<b>%{x}</b> — Start<br>%{y:.1f}%<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Call End", x=xl,
        y=[float(end.get(c, 0)) for c in pres],
        marker_color=[cmap[c] for c in pres], marker_line_width=0,
        hovertemplate="<b>%{x}</b> — End<br>%{y:.1f}%<extra></extra>",
    ))
    fig.update_layout(**_lay(
        title=_title("Customer Sentiment: Start vs. End of Call"),
        barmode="group",
        yaxis=dict(ticksuffix="%", gridcolor="#F1F5F9", zeroline=False,
                   tickfont=dict(color="#64748B", size=11)),
        bargap=0.28,
    ))
    return fig


def chart_agent_skill(dist: dict) -> go.Figure:
    order  = ["proficient", "adequate", "needs_improvement"]
    labels = ["Proficient", "Adequate", "Needs Improvement"]
    vals   = [float(dist.get(k, 0)) for k in order]

    fig = go.Figure(go.Bar(
        x=labels, y=vals,
        marker_color=[GREEN, AMBER, RED], marker_line_width=0,
        text=[f"{v:.0f}%" for v in vals],
        textposition="outside", textfont=dict(size=13, color="#334155"),
        hovertemplate="<b>%{x}</b><br>%{y:.1f}%<extra></extra>",
    ))
    fig.update_layout(**_lay(
        title=_title("Agent Skill Distribution"),
        yaxis=dict(ticksuffix="%", gridcolor="#F1F5F9", zeroline=False,
                   range=[0, max(vals)*1.38], tickfont=dict(color="#64748B", size=11)),
        showlegend=False, bargap=0.45,
    ))
    return fig


def chart_trend(runs: list[dict], field: str, label: str, unit: str,
                target: float | None, color: str, target_color: str = "#94A3B8") -> go.Figure:
    xs = [r["_dt"] for r in runs]
    ys = [r.get(field) for r in runs]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines+markers",
        line=dict(color=color, width=2.5),
        marker=dict(size=7, color=color),
        hovertemplate=f"%{{x}}<br>{label}: %{{y}}{unit}<extra></extra>",
    ))
    if target is not None:
        fig.add_hline(y=target, line_dash="dot", line_color=target_color, line_width=1.5,
                      annotation_text=f"Target {target}{unit}",
                      annotation_font_size=10, annotation_font_color=target_color)
    fig.update_layout(**_lay(
        title=_title(label),
        height=220,
        xaxis=dict(showticklabels=len(xs) > 1, tickfont=dict(size=9)),
        yaxis=dict(title=unit if unit else None),
        margin=dict(l=32, r=16, t=44, b=32),
    ))
    return fig


# ── HTML helpers ───────────────────────────────────────────────────────

def kpi_card(value: str, label: str, accent: str = "blue", delta: str = "") -> str:
    delta_html = f'<div class="kpi-delta">{delta}</div>' if delta else ""
    return (
        f'<div class="kpi-card {accent}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'{delta_html}</div>'
    )


def segment_card(title: str, badge: str, border_color: str, pct: float,
                 n_total: int, savings_usd: float | None,
                 desc: str, subs: list[str]) -> str:
    n = round(n_total * pct / 100)
    if savings_usd is not None and savings_usd > 0:
        cost_line = (
            f'<div style="font-size:1.15rem;font-weight:700;color:#059669;margin:8px 0 4px;">'
            f'${savings_usd/1000:.0f}K / month</div>'
            f'<div style="font-size:0.72rem;color:#64748B;">savings opportunity</div>'
        )
    elif savings_usd == 0:
        cost_line = (
            f'<div style="font-size:0.85rem;font-weight:600;color:#94A3B8;margin:8px 0 4px;">'
            f'Eliminate at source</div>'
        )
    else:
        cost_line = (
            f'<div style="font-size:0.85rem;font-weight:600;color:#2563EB;margin:8px 0 4px;">'
            f'Irreducible — protect agent time</div>'
        )
    subs_html = "".join(
        f'<li style="font-size:0.75rem;color:#64748B;margin-bottom:3px;">{s}</li>'
        for s in subs
    )
    return f"""
    <div style="background:#FFFFFF;border-radius:12px;border-top:5px solid {border_color};
                padding:22px 18px 18px;box-shadow:0 1px 4px rgba(15,23,42,0.07);height:100%;">
      <span style="display:inline-block;padding:3px 10px;border-radius:20px;
                   font-size:0.65rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;
                   background:{border_color}22;color:{border_color};margin-bottom:10px;
                   border:1px solid {border_color}44;">{badge}</span>
      <div style="font-size:0.68rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;
                  color:#64748B;margin-bottom:4px;">{title}</div>
      <div style="font-size:3rem;font-weight:800;line-height:1.0;letter-spacing:-0.04em;
                  color:#0F172A;">{pct:.0f}%</div>
      <div style="font-size:0.82rem;color:#94A3B8;margin-bottom:8px;">
        {n} of {n_total:,} calls analysed
      </div>
      {cost_line}
      <div style="font-size:0.78rem;color:#475569;margin-top:12px;line-height:1.65;
                  border-top:1px solid #F1F5F9;padding-top:10px;">{desc}</div>
      <ul style="margin:10px 0 0;padding-left:14px;">{subs_html}</ul>
    </div>
    """


def _tl_pill(priority: str) -> str:
    cfg = {
        "Critical":  ("tl-red",   "pill-red",   "CRITICAL"),
        "High":      ("tl-amber", "pill-amber",  "HIGH"),
        "Quick Win": ("tl-green", "pill-green",  "QUICK WIN"),
    }
    dot_cls, pill_cls, label = cfg.get(priority, ("tl-green", "pill-green", priority.upper()))
    return (
        f'<span class="priority-pill {pill_cls}">'
        f'<span class="tl-dot {dot_cls}"></span>{label}</span>'
    )


def _issue_routing_table(ic: dict) -> str:
    total = sum(ic.values()) or 1
    rows  = []
    for cat in ic:
        count   = int(ic[cat])
        pct     = count / total * 100
        routing = ISSUE_ROUTING.get(cat, {"proactive": 5, "digital": 30, "human": 65})
        p, d, h = routing["proactive"], routing["digital"], routing["human"]
        rows.append(
            f"<tr>"
            f"<td><strong>{cat.capitalize()}</strong></td>"
            f"<td style='text-align:center;color:#64748B;font-size:0.82rem;'>"
            f"{count} &nbsp;<span style='color:#94A3B8;'>({pct:.0f}%)</span></td>"
            f"<td style='text-align:center;'>"
            f"<span style='color:#0D9488;font-weight:700;'>{p}%</span></td>"
            f"<td style='text-align:center;'>"
            f"<span style='color:#7C3AED;font-weight:700;'>{d}%</span></td>"
            f"<td style='text-align:center;'>"
            f"<span style='color:#2563EB;font-weight:700;'>{h}%</span></td>"
            f"</tr>"
        )
    return (
        f'<table class="tl-table">'
        f'<thead><tr>'
        f'<th>Issue Type</th><th style="text-align:center;">Volume</th>'
        f'<th style="text-align:center;color:#5EEAD4;">Proactive</th>'
        f'<th style="text-align:center;color:#C4B5FD;">Self-Serve/AI</th>'
        f'<th style="text-align:center;color:#93C5FD;">Human</th>'
        f'</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        f'</table>'
    )


def _benchmark_scorecard_html(kpis: dict) -> str:
    rows = []
    for field, cfg in BENCHMARKS.items():
        actual = float(kpis.get(field, 0))
        target = float(cfg["target"])
        unit   = cfg["unit"]
        hb     = cfg["higher_better"]
        label  = cfg["label"]

        if hb:
            gap = actual - target
            on  = actual >= target
        else:
            gap = target - actual
            on  = actual <= target

        close = abs(actual - target) / (target or 1) < 0.20

        if on:
            dot, gap_color = "tl-green", "#059669"
            gap_str = f"▲ +{abs(gap):.1f}{unit}"
        elif close:
            dot, gap_color = "tl-amber", "#D97706"
            gap_str = f"{'▼' if gap < 0 else '▲'} {abs(gap):.1f}{unit}"
        else:
            dot, gap_color = "tl-red", "#DC2626"
            gap_str = f"▼ {abs(gap):.1f}{unit}"

        rows.append(
            f"<tr>"
            f"<td style='font-size:0.81rem;'>"
            f"<span class='tl-dot {dot}'></span>{label}</td>"
            f"<td style='text-align:right;font-weight:700;font-size:0.88rem;'>"
            f"{actual:.0f}{unit}</td>"
            f"<td style='text-align:right;color:#64748B;font-size:0.81rem;'>"
            f"{target:.0f}{unit}</td>"
            f"<td style='text-align:right;color:{gap_color};font-weight:700;"
            f"font-size:0.81rem;'>{gap_str}</td>"
            f"</tr>"
        )
    return (
        f'<p style="font-size:0.68rem;font-weight:700;letter-spacing:0.1em;'
        f'text-transform:uppercase;color:#64748B;margin-bottom:8px;">Full KPI Scorecard</p>'
        f'<table class="tl-table">'
        f'<thead><tr>'
        f'<th>KPI</th>'
        f'<th style="text-align:right;">Actual</th>'
        f'<th style="text-align:right;">Target</th>'
        f'<th style="text-align:right;">vs Target</th>'
        f'</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        f'</table>'
    )


def section(label: str) -> None:
    st.markdown(f'<div class="section-header">{label}</div>', unsafe_allow_html=True)


# ── App ────────────────────────────────────────────────────────────────

def main():
    data, is_demo = load_summary()
    kpis  = data["kpis"]
    cl    = data["cost_levers"]
    phase = data["phase_avg_seconds"]
    dist  = data["distributions"]
    meta  = data["meta"]

    n_calls  = meta["total_calls_analyzed"]
    run_date = html.escape(meta.get("analysis_timestamp", "")[:10])
    model    = html.escape(meta.get("model", "gemini-2.5-flash-lite"))
    provider = html.escape(meta.get("inference_provider", "Google AI Studio"))

    # ── Segment arithmetic ────────────────────────────────────────────
    proactive_pct = float(kpis.get("proactive_outreach_pct",    0))
    selfserve_pct = float(kpis.get("self_serve_deflection_pct", 0))
    agentic_pct   = float(kpis.get("agentic_ai_resolvable_pct", 0))
    digital_pct   = min(selfserve_pct + agentic_pct, max(100.0 - proactive_pct, 0.0))
    human_pct     = max(100.0 - proactive_pct - digital_pct, 0.0)
    avoidable_pct = proactive_pct + digital_pct

    # ── Hero banner ───────────────────────────────────────────────────
    badge_cls  = "demo" if is_demo else ""
    badge_text = "DEMO DATA" if is_demo else "LIVE DATA"
    st.markdown(f"""
    <div class="hero-banner">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;
                  flex-wrap:wrap;gap:16px;">
        <div>
          <div class="hero-title">Telecom Call Intelligence</div>
          <div class="hero-subtitle">Customer Contact Segmentation &amp; Deflection Analysis</div>
          <div style="margin-top:14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
            <span style="font-size:2.2rem;font-weight:800;color:#34D399;
                         letter-spacing:-0.03em;">{avoidable_pct:.0f}%</span>
            <span style="font-size:0.95rem;color:#93C5FD;font-weight:500;">
              of contacts were unnecessary</span>
            <span style="color:#334155;margin:0 2px;">·</span>
            <span style="font-size:0.78rem;color:#64748B;">
              Proactive Care &nbsp;·&nbsp; Self-Serve Deflection &nbsp;·&nbsp;
              Human Contact Sizing</span>
          </div>
        </div>
        <div style="text-align:right;padding-top:4px;">
          <span class="hero-badge {badge_cls}">{badge_text}</span>
          <div style="font-size:0.78rem;color:#94A3B8;margin-top:10px;line-height:1.7;">
            {n_calls:,} calls analysed &nbsp;|&nbsp; {run_date}<br>
            {provider} &nbsp;·&nbsp; {model}
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if is_demo:
        st.markdown("""
        <div class="insight-box" style="margin-top:16px;">
          <strong>Demo mode:</strong> Displaying built-in sample data.
          Run <code>python run_pipeline.py</code> to analyse real transcripts
          and reload with live pipeline results.
        </div>
        """, unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════
    # SECTION 1 — Contact Triage: The 3 Segments
    # ═════════════════════════════════════════════════════════════════
    section("Contact Triage — Where Should Each Call Have Gone?")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(segment_card(
            title="Proactive Care",
            badge="PREVENT",
            border_color="#0D9488",
            pct=proactive_pct,
            n_total=n_calls,
            savings_usd=cl["proactive_care_savings_usd"],
            desc=(
                "These customers called because a system-detectable event — network outage, "
                "bill spike, data exhaustion — wasn't caught and communicated before it "
                "disrupted their service. A proactive alert eliminates the contact entirely."
            ),
            subs=[
                "Network / service outage in customer area",
                "Bill significantly higher than prior month",
                "Data or credit balance near exhaustion",
                "Payment overdue / direct debit about to fail",
                "Contract or plan expiring within 30 days",
            ],
        ), unsafe_allow_html=True)
    with c2:
        st.markdown(segment_card(
            title="Self-Serve / Agentic AI",
            badge="DEFLECT",
            border_color="#7C3AED",
            pct=digital_pct,
            n_total=n_calls,
            savings_usd=cl["self_serve_savings_usd"] + cl["agentic_ai_savings_usd"],
            desc=(
                "These contacts had a fully deterministic resolution — balance check, plan "
                "enquiry, order status, bill explanation, payment. The customer or an AI agent "
                "could have resolved it end-to-end through a digital channel without any "
                "human agent involvement."
            ),
            subs=[
                f"Self-serve eligible: {selfserve_pct:.0f}% · App / website / IVR",
                f"Agentic AI resolvable: {agentic_pct:.0f}% · AI agent end-to-end",
                "Order status, plan info, payments, balance checks",
                "Voicemail setup, SIM activation, address updates",
            ],
        ), unsafe_allow_html=True)
    with c3:
        st.markdown(segment_card(
            title="Human Support Required",
            badge="SERVE",
            border_color="#2563EB",
            pct=human_pct,
            n_total=n_calls,
            savings_usd=None,
            desc=(
                "Complex faults, billing disputes, complaints, escalations — these genuinely "
                "require an empathetic, skilled agent. This is where your human investment "
                "delivers irreplaceable value. Protect agent time by deflecting everything else."
            ),
            subs=[
                "Complex / intermittent technical faults",
                "Billing disputes & charge investigations",
                "Escalations, complaints & retention",
                "Device hardware diagnostics",
                "Vulnerable customer situations",
            ],
        ), unsafe_allow_html=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    st.plotly_chart(
        chart_segment_funnel(proactive_pct, digital_pct, human_pct, n_calls),
        use_container_width=True,
    )

    st.markdown(f"""
    <div class="insight-box">
      <strong>{avoidable_pct:.0f}% of contacts analysed were unnecessary.</strong>
      &nbsp;{proactive_pct:.0f}% could have been prevented entirely with proactive system
      notifications before the customer even picked up the phone.
      &nbsp;{digital_pct:.0f}% reached a human agent for issues fully resolvable through
      digital channels or an AI agent
      ({selfserve_pct:.0f}% self-serve · {agentic_pct:.0f}% agentic AI).
      Only <strong>{human_pct:.0f}% genuinely required human expertise.</strong>
      Every call in the first two segments is a failure of proactive care and digital
      self-serve strategy — and a direct, avoidable cost to your contact centre.
    </div>
    """, unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════
    # SECTION 2 — Issue-to-Resolution Pathway
    # ═════════════════════════════════════════════════════════════════
    section("Issue-to-Resolution Pathway — Where Each Issue Type Should Route")

    ic = dist.get("issue_category", {})
    c1, c2 = st.columns([3, 2])
    with c1:
        if ic:
            st.plotly_chart(chart_issue_routing(ic), use_container_width=True)
    with c2:
        if ic:
            st.markdown(_issue_routing_table(ic), unsafe_allow_html=True)
            st.markdown(
                "<p style='font-size:0.68rem;color:#94A3B8;margin-top:8px;'>"
                "Routing percentages are industry CX benchmarks. Validate against your "
                "actual contact driver taxonomy.</p>",
                unsafe_allow_html=True,
            )

    # ═════════════════════════════════════════════════════════════════
    # SECTION 3 — Monthly Cost Impact by Segment
    # ═════════════════════════════════════════════════════════════════
    section("Monthly Cost Impact by Segment — What's at Stake")

    digital_savings = cl["self_serve_savings_usd"] + cl["agentic_ai_savings_usd"]
    residual_cost   = cl["baseline_monthly_cost_usd"] - cl["total_savings_opportunity_usd"]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card(
            f"${cl['baseline_monthly_cost_usd']/1000:.0f}K",
            "Current Monthly Cost", "red",
            f"${cl['cost_per_call_usd']:.2f}/call × {cl['monthly_volume_estimate']:,}/mo",
        ), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card(
            f"${cl['proactive_care_savings_usd']/1000:.0f}K",
            "Proactive Care Savings", "teal",
            f"Prevent {proactive_pct:.0f}% of contacts at source",
        ), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card(
            f"${digital_savings/1000:.0f}K",
            "Self-Serve / Agentic Savings", "purple",
            f"Deflect {digital_pct:.0f}% to digital channels",
        ), unsafe_allow_html=True)
    with c4:
        st.markdown(kpi_card(
            f"${residual_cost/1000:.0f}K",
            "Irreducible Human Cost", "blue",
            f"{human_pct:.0f}% genuinely needs skilled agents",
        ), unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(chart_cost_waterfall(cl), use_container_width=True)
    with c2:
        total_opp = cl["total_savings_opportunity_usd"]
        st.markdown(f"""
        <div class="insight-box" style="margin-top:0;">
          <strong>Total Savings Opportunity: ${total_opp/1000:.0f}K / month
          ({cl['savings_pct_of_baseline']:.0f}% of
          ${cl['baseline_monthly_cost_usd']/1000:.0f}K baseline)</strong><br><br>

          <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:7px;">
            <span style="width:9px;height:9px;border-radius:50%;background:#0D9488;
                         flex-shrink:0;display:inline-block;margin-top:3px;"></span>
            <span><strong>Proactive Care</strong> — prevent {proactive_pct:.0f}% of calls
            before they happen: &nbsp;
            <strong style="color:#0D9488;">${cl['proactive_care_savings_usd']/1000:.0f}K/mo</strong></span>
          </div>
          <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:7px;">
            <span style="width:9px;height:9px;border-radius:50%;background:#7C3AED;
                         flex-shrink:0;display:inline-block;margin-top:3px;"></span>
            <span><strong>Self-Serve Deflection</strong> — route {selfserve_pct:.0f}% to
            app / web / IVR: &nbsp;
            <strong style="color:#7C3AED;">${cl['self_serve_savings_usd']/1000:.0f}K/mo</strong></span>
          </div>
          <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:14px;">
            <span style="width:9px;height:9px;border-radius:50%;background:#7C3AED;
                         flex-shrink:0;display:inline-block;margin-top:3px;"></span>
            <span><strong>Agentic AI Automation</strong> — automate {agentic_pct:.0f}%
            end-to-end: &nbsp;
            <strong style="color:#7C3AED;">${cl['agentic_ai_savings_usd']/1000:.0f}K/mo</strong></span>
          </div>

          <span style="font-size:0.72rem;color:#94A3B8;">
            Estimates use ${cl['cost_per_call_usd']:.2f}/call industry benchmark ×
            {cl['monthly_volume_estimate']:,} calls/month.
            Replace with actual ACD unit costs for planning.</span>
        </div>
        """, unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════
    # SECTION 4 — Actual vs Industry Benchmark Scorecard
    # ═════════════════════════════════════════════════════════════════
    section("Actual vs Industry Benchmark — Performance Scorecard")

    c1, c2 = st.columns([3, 2])
    with c1:
        st.plotly_chart(chart_benchmark_bars(kpis), use_container_width=True)
    with c2:
        st.markdown(_benchmark_scorecard_html(kpis), unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════
    # SECTION 5 — Core Performance KPIs (operational baseline)
    # ═════════════════════════════════════════════════════════════════
    section("Core Performance KPIs — Operational Baseline")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    kpi_defs = [
        (c1, f"{kpis['fcr_rate_pct']:.0f}%",              "First Call Resolution",  "green",  "Target ≥ 75%"),
        (c2, f"{kpis['avg_handle_time_minutes']:.1f} min", "Avg Handle Time",        "amber",  "Industry avg: 6–8 min"),
        (c3, f"{kpis['escalation_rate_pct']:.0f}%",        "Escalation Rate",        "red",    "Target < 10%"),
        (c4, f"{kpis['sentiment_improved_pct']:.0f}%",     "Sentiment Improvement",  "teal",   "Start → end of call"),
        (c5, f"{kpis['all_issues_resolved_pct']:.0f}%",    "Issues Fully Resolved",  "blue",   f"Avg {kpis['avg_issues_per_call']:.1f} issues/call"),
        (c6, f"{kpis['agent_tool_struggle_pct']:.0f}%",    "Agent Tool Struggle",    "purple", "Leading AHT inflation driver"),
    ]
    for col, val, label, accent, delta in kpi_defs:
        with col:
            st.markdown(kpi_card(val, label, accent, delta), unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════
    # SECTION 6 — Call Phase Breakdown
    # ═════════════════════════════════════════════════════════════════
    section("Call Phase Breakdown — Time Investment per Phase")

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(chart_phase_bar(phase), use_container_width=True)
    with c2:
        diag_s  = phase.get("Diagnosis", 0)
        disc_s  = phase.get("Discovery", 0)
        tot_s   = sum(phase.values()) or 1
        diag_pc = round(diag_s / tot_s * 100)
        diag_ov = float(dist.get("agent_disproportionate_phase", {}).get("diagnosis", 0))
        st.markdown(f"""
        <div class="insight-box" style="margin-top:0;">
          <strong>Phase Insight:</strong> Diagnosis represents
          <strong>{diag_pc}% of average handle time</strong> ({diag_s}s avg).
          {diag_ov:.0f}% of agents are flagged for disproportionate time in this phase —
          a primary indicator of knowledge base gaps or tool friction.
          Combined, Discovery and Diagnosis account for
          {round((disc_s + diag_s) / tot_s * 100)}% of total AHT.
        </div>
        """, unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════
    # SECTION 7 — Agent Performance & Customer Sentiment
    # ═════════════════════════════════════════════════════════════════
    section("Agent Performance & Customer Sentiment")

    c1, c2, c3 = st.columns(3)
    agent_dist = dist.get("agent_skill", {})
    rr_dist    = dist.get("repeat_call_risk", {})

    with c1:
        if agent_dist:
            st.plotly_chart(chart_agent_skill(agent_dist), use_container_width=True)
    with c2:
        sent_s = dist.get("customer_sentiment_start", {})
        sent_e = dist.get("customer_sentiment_end",   {})
        if sent_s or sent_e:
            st.plotly_chart(chart_sentiment(sent_s, sent_e), use_container_width=True)
    with c3:
        if rr_dist:
            order  = ["low", "medium", "high"]
            labels = ["Low Risk", "Medium Risk", "High Risk"]
            values = [float(rr_dist.get(k, 0)) for k in order]
            st.plotly_chart(
                chart_donut(labels, values, "Repeat Call Risk Profile", [GREEN, AMBER, RED]),
                use_container_width=True,
            )

    tool_pct  = kpis.get("agent_tool_struggle_pct", 0)
    needs_imp = float(agent_dist.get("needs_improvement", 0)) if agent_dist else 0
    high_risk = float(rr_dist.get("high", 0)) if rr_dist else 0

    st.markdown(f"""
    <div class="insight-box amber">
      <strong>Performance Alert:</strong> {tool_pct:.0f}% of agents show tool struggle on calls —
      directly inflating handle time and driving repeat-call risk.
      {needs_imp:.0f}% of agents rated Needs Improvement correlates with {high_risk:.0f}% high
      repeat-call risk. Targeted coaching on diagnosis-phase tooling could recover an estimated
      15–20% of inefficient AHT.
    </div>
    """, unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════
    # SECTION 8 — Upsell & Revenue Intelligence
    # ═════════════════════════════════════════════════════════════════
    section("Upsell & Revenue Intelligence")

    c1, c2, c3 = st.columns([1, 1, 1])
    uo_dist = dist.get("upsell_outcome", {})
    with c1:
        if uo_dist:
            labels = [k.replace("_", " ").capitalize() for k in uo_dist]
            values = [float(v) for v in uo_dist.values()]
            st.plotly_chart(
                chart_donut(labels, values, "Upsell Outcome", [SLATE, RED, GREEN, AMBER]),
                use_container_width=True,
            )
    with c2:
        st.markdown(kpi_card(
            f"{kpis['upsell_attempted_pct']:.0f}%", "Upsell Attempted", "amber",
            "of eligible calls"
        ), unsafe_allow_html=True)
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        st.markdown(kpi_card(
            f"{kpis['upsell_conversion_pct']:.0f}%", "Upsell Conversion Rate", "green",
            "when attempted"
        ), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card(
            f"{kpis['avoidable_call_rate_pct']:.0f}%", "Avoidable Call Rate", "red",
            "Deflectable or preventable"
        ), unsafe_allow_html=True)
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        st.markdown(kpi_card(
            f"{kpis['proactive_outreach_pct']:.0f}%", "Proactive Outreach Eligible", "teal",
            "Preventable via notification"
        ), unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════
    # SECTION 9 — Executive Action Plan
    # ═════════════════════════════════════════════════════════════════
    section("Executive Action Plan")

    st.markdown("""
    <div style="display:flex;align-items:center;gap:20px;font-size:0.78rem;
                color:#475569;margin-bottom:14px;flex-wrap:wrap;">
      <span style="font-weight:600;color:#1E293B;">Priority Signal:</span>
      <span style="display:flex;align-items:center;gap:6px;">
        <span style="width:12px;height:12px;display:inline-block;border-radius:50%;
                     background:#DC2626;box-shadow:0 0 7px rgba(220,38,38,0.55);"></span>
        <strong style="color:#991B1B;">Critical</strong> — Immediate action required
      </span>
      <span style="display:flex;align-items:center;gap:6px;">
        <span style="width:12px;height:12px;display:inline-block;border-radius:50%;
                     background:#D97706;box-shadow:0 0 7px rgba(217,119,6,0.55);"></span>
        <strong style="color:#92400E;">High</strong> — Plan within this quarter
      </span>
      <span style="display:flex;align-items:center;gap:6px;">
        <span style="width:12px;height:12px;display:inline-block;border-radius:50%;
                     background:#059669;box-shadow:0 0 7px rgba(5,150,105,0.55);"></span>
        <strong style="color:#065F46;">Quick Win</strong> — Low effort, fast ROI
      </span>
    </div>
    """, unsafe_allow_html=True)

    digital_savings = cl["self_serve_savings_usd"] + cl["agentic_ai_savings_usd"]
    needs_imp = float(agent_dist.get("needs_improvement", 0)) if agent_dist else 0

    rows = [
        ("Critical", "Proactive Care Programme",
         f"{proactive_pct:.0f}% of calls preventable",
         f"${cl['proactive_care_savings_usd']/1000:.0f}K / month",
         "Deploy event-driven notifications: outage alerts, bill spike SMS, data-exhaustion "
         "push. Prevent the contact before it reaches the queue."),
        ("Critical", "Agentic AI Call Automation",
         f"{agentic_pct:.0f}% of calls automatable",
         f"${cl['agentic_ai_savings_usd']/1000:.0f}K / month",
         "Build LangGraph agent flows for top deterministic intents: order status, plan "
         "enquiry, bill explanation, payments, SIM activation."),
        ("Critical", "Self-Serve App Deflection",
         f"{selfserve_pct:.0f}% of calls deflectable",
         f"${cl['self_serve_savings_usd']/1000:.0f}K / month",
         "Publish in-app bill explanation, plan comparison, and APN reset. Redirect IVR "
         "to digital for balance, order, and plan enquiry intents."),
        ("High", "Focus Agents on Human-Only Contacts",
         f"{human_pct:.0f}% genuinely needs agents",
         "Quality & NPS lift",
         "With proactive and digital handling the first two segments, agents focus entirely "
         "on complex faults, disputes, and retention — their highest-value work."),
        ("High", "Agent Knowledge Base & Tooling",
         f"{needs_imp:.0f}% of agents rated Needs Improvement",
         "AHT reduction ~15–20%",
         "Identify Diagnosis-phase gaps from call analysis. Deliver targeted coaching "
         "and knowledge-base updates for technical and billing categories."),
        ("Quick Win", "Upsell Personalisation Engine",
         f"{kpis['upsell_attempted_pct']:.0f}% attempted currently",
         "Revenue lift",
         "Surface personalised offers during human contacts using eligibility and usage "
         "propensity signals — for the calls that genuinely needed an agent."),
    ]

    rows_html = "".join(
        f"<tr>"
        f"<td>{_tl_pill(p)}</td>"
        f"<td><strong>{html.escape(init)}</strong></td>"
        f"<td style='color:#475569;font-size:0.84rem;'>{html.escape(scope)}</td>"
        f"<td><strong style='color:#059669;'>{html.escape(impact)}</strong></td>"
        f"<td style='color:#334155;font-size:0.84rem;'>{html.escape(action)}</td>"
        f"</tr>"
        for p, init, scope, impact, action in rows
    )

    st.markdown(f"""
    <table class="tl-table">
      <thead>
        <tr>
          <th>Priority</th><th>Initiative</th><th>Scope</th>
          <th>Est. Impact</th><th>Recommended Next Step</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    """, unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════
    # SECTION 10 — Performance Trends Across Runs
    # ═════════════════════════════════════════════════════════════════
    runs = load_run_history()
    section("Performance Trends Across Runs")

    if len(runs) < 2:
        st.markdown(
            "<div class='insight-box'>Run the pipeline at least twice to see trend charts. "
            f"{'1 run recorded so far.' if len(runs) == 1 else 'No runs recorded yet.'}</div>",
            unsafe_allow_html=True,
        )
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.plotly_chart(
                chart_trend(runs, "fcr_rate_pct", "First Call Resolution", "%", 75, GREEN),
                use_container_width=True,
            )
        with c2:
            st.plotly_chart(
                chart_trend(runs, "aht_minutes", "Avg Handle Time", " min", 6, AMBER),
                use_container_width=True,
            )
        with c3:
            st.plotly_chart(
                chart_trend(runs, "qa_avg_score", "QA Score", "", 85, BLUE),
                use_container_width=True,
            )

        cum = {}
        try:
            mem_path = Path("outputs/agent_memory.json")
            if mem_path.exists():
                with open(mem_path) as f:
                    cum = json.load(f).get("cumulative", {})
        except Exception:
            pass

        latest    = runs[-1]
        prev      = runs[-2]
        fcr_delta = latest.get("fcr_rate_pct", 0) - prev.get("fcr_rate_pct", 0)
        aht_delta = latest.get("aht_minutes",  0) - prev.get("aht_minutes",  0)
        qa_delta  = latest.get("qa_avg_score", 0) - prev.get("qa_avg_score", 0)

        def _delta_str(v: float, higher_is_good: bool) -> str:
            arrow = "↑" if v >= 0 else "↓"
            sign  = "+" if v >= 0 else ""
            color = "color:#059669" if (v >= 0) == higher_is_good else "color:#DC2626"
            return f"<span style='{color};font-weight:600'>{arrow} {sign}{v:.1f}</span>"

        total_runs  = len(runs)
        total_calls = cum.get("total_calls_analyzed", sum(r.get("n_analyzed", 0) for r in runs))
        total_cost  = cum.get("total_cost_usd", sum(r.get("total_cost_usd", 0) for r in runs))
        src         = html.escape(latest.get("insights_source", "unknown"))

        st.markdown(f"""
        <div class="insight-box">
          <strong>Trend Summary:</strong> &nbsp;
          {total_runs} runs · {total_calls:,} calls analysed · ${total_cost:.4f} total cost
          &nbsp;|&nbsp; Latest vs prior run —
          FCR {_delta_str(fcr_delta, True)} pp &nbsp;·&nbsp;
          AHT {_delta_str(aht_delta, False)} min &nbsp;·&nbsp;
          QA {_delta_str(qa_delta, True)} pts &nbsp;·&nbsp;
          Insights source: <strong>{src}</strong>
        </div>
        """, unsafe_allow_html=True)

    # ── Footer ────────────────────────────────────────────────────────
    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='dash-footer'>"
        f"<span>Telecom Call Intelligence &nbsp;·&nbsp; Contact Segmentation &amp; "
        f"Deflection Analysis &nbsp;·&nbsp; {n_calls:,} calls analysed &nbsp;·&nbsp; "
        f"{html.escape(meta['dataset'])}</span>"
        f"<span>{provider} &nbsp;·&nbsp; {model} &nbsp;·&nbsp; {run_date}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
