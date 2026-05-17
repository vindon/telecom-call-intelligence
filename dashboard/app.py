"""
dashboard/app.py
----------------
Executive CX Intelligence Dashboard
Telecom Call Analytics — Cost-to-Serve Optimization

Run:
  streamlit run dashboard/app.py

Loads outputs/summary.json if present.
Falls back to built-in DEMO DATA so the dashboard works on GitHub
without running the pipeline.
"""

import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="CX Call Intelligence | Telecom Analytics",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styling ───────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

  html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #0C1220;
    color: #E8EDF5;
  }

  .main { background-color: #0C1220; }
  .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

  /* KPI Cards */
  .kpi-card {
    background: linear-gradient(145deg, #131D2E, #0F1828);
    border: 1px solid #1E3050;
    border-radius: 12px;
    padding: 20px 22px;
    text-align: center;
  }
  .kpi-value {
    font-size: 2.2rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    line-height: 1.1;
    margin: 4px 0;
  }
  .kpi-label {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #6B7FA0;
    margin-bottom: 4px;
  }
  .kpi-delta {
    font-size: 0.75rem;
    color: #6B7FA0;
    margin-top: 4px;
  }

  /* Section headers */
  .section-header {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #C9A84C;
    border-left: 3px solid #C9A84C;
    padding-left: 10px;
    margin: 28px 0 14px;
  }

  /* Alert banners */
  .insight-banner {
    background: rgba(201, 168, 76, 0.08);
    border: 1px solid rgba(201, 168, 76, 0.3);
    border-radius: 8px;
    padding: 14px 18px;
    font-size: 0.85rem;
    color: #D4B870;
    margin-bottom: 10px;
  }

  /* Demo mode badge */
  .demo-badge {
    background: rgba(91, 141, 184, 0.15);
    border: 1px solid rgba(91, 141, 184, 0.4);
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 0.72rem;
    color: #5B8DB8;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.08em;
  }

  /* Savings highlight */
  .savings-card {
    background: linear-gradient(135deg, #0E2218, #0C1A12);
    border: 1px solid #1A4030;
    border-radius: 12px;
    padding: 22px;
    text-align: center;
  }

  /* Hide Streamlit branding */
  #MainMenu {visibility: hidden;}
  footer {visibility: hidden;}
  header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ── Plotly theme ──────────────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor="#0C1220",
    plot_bgcolor="#0C1220",
    font=dict(family="Inter, sans-serif", color="#C8D4E8", size=12),
    margin=dict(l=10, r=10, t=36, b=10),
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        font=dict(size=11),
        orientation="h",
        yanchor="bottom", y=1.02,
        xanchor="right",  x=1,
    ),
)

GOLD   = "#C9A84C"
BLUE   = "#3A78C9"
GREEN  = "#3DAD7F"
RED    = "#D45B5B"
PURPLE = "#8B6FCC"
TEAL   = "#3AADAD"
GREY   = "#4A5568"

PHASE_COLORS = {
    "Welcome & Auth": "#3A78C9",
    "Discovery":      "#8B6FCC",
    "Diagnosis":      "#D45B5B",
    "Resolution":     "#3DAD7F",
    "Hold":           "#C9A84C",
    "Upsell":         "#3AADAD",
    "Closing":        "#4A5568",
}


# ── Demo data ─────────────────────────────────────────────────────────
# Embedded so the dashboard runs immediately on GitHub without running the pipeline.
# These values are realistic for a telecom contact centre of this size.

DEMO_DATA = {
    "meta": {
        "total_calls_analyzed": 100,
        "analysis_timestamp": "2025-04-12T09:41:22.000000",
        "dataset": "talkmap/telecom-conversation-corpus",
        "model": "llama-3.3-70b-versatile",
        "inference_provider": "Groq",
        "cost_benchmark_note": "Cost estimates use $6.00/call industry benchmark.",
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
        "Welcome & Auth": 46,
        "Discovery":      108,
        "Diagnosis":      152,
        "Resolution":     128,
        "Hold":           87,
        "Upsell":         44,
        "Closing":        54,
    },
    "distributions": {
        "issue_category": {
            "billing":     38,
            "technical":   31,
            "plan":        16,
            "account":      9,
            "device":       4,
            "information":  2,
        },
        "cost_driver": {
            "billing":          "37.0",
            "technical":        "30.0",
            "plan_change":      "16.0",
            "device":           "9.0",
            "information_only": "5.0",
            "complaint":        "3.0",
        },
        "agent_skill": {
            "proficient":         "44.0",
            "adequate":           "38.0",
            "needs_improvement":  "18.0",
        },
        "customer_sentiment_start": {
            "frustrated": "41.0",
            "negative":   "22.0",
            "neutral":    "28.0",
            "positive":    "9.0",
        },
        "customer_sentiment_end": {
            "positive":   "48.0",
            "neutral":    "29.0",
            "negative":   "15.0",
            "frustrated":  "8.0",
        },
        "handle_time_efficiency": {
            "efficient":   "39.0",
            "average":     "43.0",
            "inefficient": "18.0",
        },
        "self_serve_channel": {
            "app":     "42.0",
            "website": "28.0",
            "IVR":     "18.0",
            "chatbot": "12.0",
        },
        "repeat_call_risk": {
            "low":    "43.0",
            "medium": "38.0",
            "high":   "19.0",
        },
        "agent_disproportionate_phase": {
            "none":      "48.0",
            "diagnosis": "26.0",
            "discovery": "14.0",
            "resolution":"12.0",
        },
        "upsell_outcome": {
            "not_attempted": "48.0",
            "declined":      "34.0",
            "accepted":       "9.0",
            "pending":        "9.0",
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
    """Load summary.json if it exists; otherwise return demo data."""
    summary_path = Path("outputs/summary.json")
    if summary_path.exists():
        with open(summary_path) as f:
            return json.load(f), False  # False = not demo
    return DEMO_DATA, True  # True = demo mode


# ── Chart helpers ─────────────────────────────────────────────────────

def make_phase_bar(phase_data: dict) -> go.Figure:
    phases  = list(phase_data.keys())
    seconds = list(phase_data.values())
    minutes = [round(s / 60, 1) for s in seconds]
    colors  = [PHASE_COLORS.get(p, GREY) for p in phases]

    fig = go.Figure(go.Bar(
        x=phases, y=seconds,
        marker_color=colors,
        text=[f"{m}m" for m in minutes],
        textposition="outside",
        textfont=dict(size=11, color="#C8D4E8"),
        hovertemplate="<b>%{x}</b><br>%{y}s (%{text})<extra></extra>",
    ))
    fig.update_layout(**PLOTLY_LAYOUT)
    fig.update_layout(
        title=dict(text="Average Time Spent per Call Phase (seconds)", font=dict(size=13, color=GOLD), x=0),
        yaxis_title="Seconds",
        yaxis=dict(gridcolor="#1A2A3A", showgrid=True),
        xaxis=dict(tickfont=dict(size=10)),
        bargap=0.35,
    )
    return fig


def make_cost_waterfall(cl: dict) -> go.Figure:
    baseline = cl["baseline_monthly_cost_usd"]
    ss       = cl["self_serve_savings_usd"]
    ai       = cl["agentic_ai_savings_usd"]
    pro      = cl["proactive_care_savings_usd"]
    net      = baseline - ss - ai - pro

    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute", "relative", "relative", "relative", "total"],
        x=["Baseline Cost", "Self-Serve\nDeflection", "Agentic AI\nResolution", "Proactive\nOutreach", "Optimised Cost"],
        y=[baseline, -ss, -ai, -pro, net],
        connector=dict(line=dict(color="#2A3A4A", width=1.5)),
        decreasing=dict(marker_color=GREEN),
        increasing=dict(marker_color=RED),
        totals=dict(marker_color=BLUE),
        text=[f"${v/1000:.0f}K" for v in [baseline, ss, ai, pro, net]],
        textfont=dict(size=11, color="white"),
        hovertemplate="<b>%{x}</b><br>$%{value:,.0f}<extra></extra>",
    ))
    fig.update_layout(**PLOTLY_LAYOUT)
    fig.update_layout(
        title=dict(text="Monthly Cost-to-Serve Waterfall (Est. 100K calls/mo)", font=dict(size=13, color=GOLD), x=0),
        yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor="#1A2A3A"),
        showlegend=False,
    )
    return fig


def make_donut(labels: list, values: list, title: str, colors: list = None) -> go.Figure:
    if colors is None:
        colors = [BLUE, RED, GREEN, GOLD, PURPLE, TEAL, GREY]
    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.58,
        marker=dict(colors=colors[:len(labels)], line=dict(color="#0C1220", width=2)),
        textinfo="percent",
        textfont=dict(size=11),
        hovertemplate="<b>%{label}</b><br>%{value} calls (%{percent})<extra></extra>",
    ))
    fig.update_layout(**PLOTLY_LAYOUT)
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color=GOLD), x=0),
        legend=dict(orientation="v", x=0.82, y=0.5, font=dict(size=10)),
        margin=dict(l=10, r=10, t=40, b=10),
    )
    return fig


def make_sentiment_compare(dist_start: dict, dist_end: dict) -> go.Figure:
    categories = ["positive", "neutral", "negative", "frustrated", "distressed"]
    cat_colors = {
        "positive":   GREEN,
        "neutral":    BLUE,
        "negative":   GOLD,
        "frustrated": RED,
        "distressed": PURPLE,
    }
    present = [c for c in categories if c in dist_start or c in dist_end]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Start of Call",
        x=present,
        y=[float(dist_start.get(c, 0)) for c in present],
        marker_color=[cat_colors[c] for c in present],
        opacity=0.45,
        hovertemplate="<b>%{x}</b> (start)<br>%{y}%<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="End of Call",
        x=present,
        y=[float(dist_end.get(c, 0)) for c in present],
        marker_color=[cat_colors[c] for c in present],
        opacity=1.0,
        hovertemplate="<b>%{x}</b> (end)<br>%{y}%<extra></extra>",
    ))
    fig.update_layout(**PLOTLY_LAYOUT)
    fig.update_layout(
        title=dict(text="Customer Sentiment: Start vs End of Call", font=dict(size=13, color=GOLD), x=0),
        barmode="group",
        yaxis=dict(ticksuffix="%", gridcolor="#1A2A3A"),
        bargap=0.25,
    )
    return fig


def make_agent_skill_bar(dist: dict) -> go.Figure:
    order  = ["proficient", "adequate", "needs_improvement"]
    colors = [GREEN, GOLD, RED]
    labels = ["Proficient", "Adequate", "Needs Improvement"]

    vals = [float(dist.get(k, 0)) for k in order]

    fig = go.Figure(go.Bar(
        x=labels,
        y=vals,
        marker_color=colors,
        text=[f"{v:.0f}%" for v in vals],
        textposition="outside",
        textfont=dict(size=12, color="#C8D4E8"),
        hovertemplate="<b>%{x}</b><br>%{y:.1f}%<extra></extra>",
    ))
    fig.update_layout(**PLOTLY_LAYOUT)
    fig.update_layout(
        title=dict(text="Agent Skill Rating Distribution", font=dict(size=13, color=GOLD), x=0),
        yaxis=dict(ticksuffix="%", gridcolor="#1A2A3A", range=[0, max(vals) * 1.3]),
        showlegend=False,
        bargap=0.4,
    )
    return fig


def make_deflection_opportunity(kpis: dict) -> go.Figure:
    categories = ["Self-Serve\nEligible", "Agentic AI\nResolvable", "Proactive\nOutreach", "Avoidable\nCalls"]
    values     = [
        kpis["self_serve_deflection_pct"],
        kpis["agentic_ai_resolvable_pct"],
        kpis["proactive_outreach_pct"],
        kpis["avoidable_call_rate_pct"],
    ]
    colors = [TEAL, PURPLE, BLUE, RED]

    fig = go.Figure(go.Bar(
        x=categories,
        y=values,
        marker_color=colors,
        text=[f"{v:.0f}%" for v in values],
        textposition="outside",
        textfont=dict(size=13, color="white", family="JetBrains Mono"),
        hovertemplate="<b>%{x}</b><br>%{y:.1f}% of calls<extra></extra>",
    ))
    fig.update_layout(**PLOTLY_LAYOUT)
    fig.update_layout(
        title=dict(text="Deflection & Automation Opportunity (% of Calls)", font=dict(size=13, color=GOLD), x=0),
        yaxis=dict(ticksuffix="%", gridcolor="#1A2A3A", range=[0, max(values) * 1.35]),
        showlegend=False,
        bargap=0.4,
    )
    return fig


def make_repeat_risk_donut(dist: dict) -> go.Figure:
    order  = ["low", "medium", "high"]
    labels = ["Low Risk", "Medium Risk", "High Risk"]
    values = [float(dist.get(k, 0)) for k in order]
    colors = [GREEN, GOLD, RED]
    return make_donut(labels, values, "Repeat Call Risk", colors)


def kpi_card(value: str, label: str, color: str = "#E8EDF5", delta: str = "") -> str:
    delta_html = f'<div class="kpi-delta">{delta}</div>' if delta else ""
    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value" style="color:{color};">{value}</div>
        {delta_html}
    </div>
    """


# ── App layout ────────────────────────────────────────────────────────

def main():
    data, is_demo = load_summary()
    kpis  = data["kpis"]
    cl    = data["cost_levers"]
    phase = data["phase_avg_seconds"]
    dist  = data["distributions"]
    meta  = data["meta"]

    # ── Header ────────────────────────────────────────────────────────
    col_title, col_badge = st.columns([6, 2])
    with col_title:
        st.markdown("""
        <div style="margin-bottom: 2px;">
            <span style="font-size:0.68rem;letter-spacing:0.18em;text-transform:uppercase;color:#C9A84C;font-weight:700;">
                TELECOM CX INTELLIGENCE
            </span>
        </div>
        <div style="font-size:1.9rem;font-weight:700;color:#F0F6FC;line-height:1.15;margin-bottom:4px;">
            Call Analytics Dashboard
        </div>
        <div style="font-size:0.82rem;color:#6B7FA0;">
            Cost-to-Serve Optimisation · Phase Intelligence · Agentic AI Opportunity
        </div>
        """, unsafe_allow_html=True)

    with col_badge:
        mode_label = "⚡ DEMO MODE — Sample Data" if is_demo else "✓ LIVE DATA — Pipeline Output"
        mode_color = "#5B8DB8" if is_demo else "#3DAD7F"
        provider   = meta.get("inference_provider", "Groq")
        model_name = meta.get("model", "llama-3.3-70b-versatile")
        st.markdown(f"""
        <div style="text-align:right;margin-top:12px;">
            <span style="background:rgba(0,0,0,0.3);border:1px solid {mode_color};border-radius:6px;
                         padding:6px 12px;font-size:0.7rem;color:{mode_color};font-family:monospace;">
                {mode_label}
            </span><br>
            <span style="font-size:0.68rem;color:#4A5568;margin-top:6px;display:block;">
                {meta['total_calls_analyzed']} calls · {provider} · {model_name}
            </span>
        </div>
        """, unsafe_allow_html=True)

    if is_demo:
        st.markdown("""
        <div class="insight-banner">
            📊 Displaying built-in demo data. Run <code>python run_pipeline.py</code> to analyse real transcripts
            and reload this dashboard with live results from <em>talkmap/telecom-conversation-corpus</em>.
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Executive KPIs — Row 1 ─────────────────────────────────────────
    st.markdown('<div class="section-header">Executive KPIs</div>', unsafe_allow_html=True)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    cards = [
        (c1, f"{kpis['avg_handle_time_minutes']}m",  "Avg Handle Time",   "#C9A84C", "Industry avg: 6-8m"),
        (c2, f"{kpis['fcr_rate_pct']:.0f}%",         "First Call Res.",   GREEN,     "Target: >75%"),
        (c3, f"{kpis['avoidable_call_rate_pct']:.0f}%","Avoidable Calls", RED,       "Cost reduction lever"),
        (c4, f"{kpis['escalation_rate_pct']:.0f}%",   "Escalation Rate",  "#C9A84C", "Below 10% is best"),
        (c5, f"{kpis['sentiment_improved_pct']:.0f}%", "Sentiment Lift",  TEAL,      "Start→End improvement"),
        (c6, f"{kpis['multi_issue_call_pct']:.0f}%",   "Multi-Issue Calls",PURPLE,   "Avg {:.1f} issues/call".format(kpis['avg_issues_per_call'])),
    ]
    for col, val, label, color, delta in cards:
        with col:
            st.markdown(kpi_card(val, label, color, delta), unsafe_allow_html=True)

    # ── Cost levers row ───────────────────────────────────────────────
    st.markdown('<div class="section-header">Cost-to-Serve Levers</div>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    cost_cards = [
        (c1, f"${cl['total_savings_opportunity_usd']/1000:.0f}K",
              "Monthly Savings Opportunity", GREEN, f"{cl['savings_pct_of_baseline']:.0f}% of baseline cost"),
        (c2, f"${cl['self_serve_savings_usd']/1000:.0f}K",
              "Self-Serve Deflection", TEAL,
              f"{kpis['self_serve_deflection_pct']:.0f}% of calls eligible"),
        (c3, f"${cl['agentic_ai_savings_usd']/1000:.0f}K",
              "Agentic AI Resolution", PURPLE,
              f"{kpis['agentic_ai_resolvable_pct']:.0f}% fully automatable"),
        (c4, f"${cl['proactive_care_savings_usd']/1000:.0f}K",
              "Proactive Outreach", BLUE,
              f"{kpis['proactive_outreach_pct']:.0f}% preventable calls"),
    ]
    for col, val, label, color, delta in cost_cards:
        with col:
            st.markdown(kpi_card(val, label, color, delta), unsafe_allow_html=True)

    st.markdown(
        f"""<div style="font-size:0.68rem;color:#4A5568;margin-top:6px;">
        ⚠ Estimates based on ${cl['cost_per_call_usd']:.2f}/call industry benchmark × {cl['monthly_volume_estimate']:,} calls/month.
        Replace with actual ACD data for production planning.
        </div>""",
        unsafe_allow_html=True,
    )

    # ── Main charts row 1 ─────────────────────────────────────────────
    st.markdown('<div class="section-header">Phase Analysis & Cost Waterfall</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1])
    with c1:
        st.plotly_chart(make_phase_bar(phase), use_container_width=True)
    with c2:
        st.plotly_chart(make_cost_waterfall(cl), use_container_width=True)

    # ── Phase insight callout ─────────────────────────────────────────
    diag_s = phase.get("Diagnosis", 0)
    disc_s = phase.get("Discovery", 0)
    total_s = sum(phase.values()) or 1
    diag_pct = round(diag_s / total_s * 100)
    disp_phase = data["distributions"].get("agent_disproportionate_phase", {})
    diag_over  = float(disp_phase.get("diagnosis", 0))

    st.markdown(f"""
    <div class="insight-banner">
        🔍 <strong>Phase Insight:</strong> Diagnosis accounts for <strong>{diag_pct}%</strong> of average handle time
        ({diag_s}s avg). <strong>{diag_over:.0f}%</strong> of agents are flagged for spending disproportionate time
        in this phase — a direct indicator of knowledge base gaps or tool friction.
        Discovery ({disc_s}s) and Hold ({phase.get('Hold', 0)}s) together add another{' '}
        {round((disc_s + phase.get('Hold',0)) / total_s * 100)}% of AHT.
    </div>
    """, unsafe_allow_html=True)

    # ── Main charts row 2 ─────────────────────────────────────────────
    st.markdown('<div class="section-header">Issue Distribution & Deflection Opportunity</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1])
    with c1:
        ic = dist.get("issue_category", {})
        if ic:
            labels = [k.title() for k in ic.keys()]
            values = list(ic.values())
            st.plotly_chart(
                make_donut(labels, values, "Issue Category Distribution",
                           [BLUE, RED, PURPLE, GOLD, GREEN, TEAL, GREY]),
                use_container_width=True,
            )
    with c2:
        st.plotly_chart(make_deflection_opportunity(kpis), use_container_width=True)

    # ── Agent performance ─────────────────────────────────────────────
    st.markdown('<div class="section-header">Agent Performance & Customer Sentiment</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        agent_dist = dist.get("agent_skill", {})
        if agent_dist:
            st.plotly_chart(make_agent_skill_bar(agent_dist), use_container_width=True)
    with c2:
        sent_s = dist.get("customer_sentiment_start", {})
        sent_e = dist.get("customer_sentiment_end", {})
        if sent_s or sent_e:
            st.plotly_chart(make_sentiment_compare(sent_s, sent_e), use_container_width=True)
    with c3:
        rr = dist.get("repeat_call_risk", {})
        if rr:
            st.plotly_chart(make_repeat_risk_donut(rr), use_container_width=True)

    # ── Agent performance callout ─────────────────────────────────────
    tool_pct = kpis.get("agent_tool_struggle_pct", 0)
    needs_imp = float(agent_dist.get("needs_improvement", 0)) if agent_dist else 0
    high_risk  = float(rr.get("high", 0)) if rr else 0

    st.markdown(f"""
    <div class="insight-banner">
        🎯 <strong>Agent Performance Insight:</strong> <strong>{tool_pct:.0f}%</strong> of agents show evidence of
        tool struggle during the call — a leading indicator of handle time inflation and customer dissatisfaction.
        <strong>{needs_imp:.0f}%</strong> are rated needs improvement, correlating with <strong>{high_risk:.0f}%</strong>
        of calls carrying high repeat-call risk. Targeted coaching on diagnosis tools could recover an estimated
        15-20% of inefficient AHT.
    </div>
    """, unsafe_allow_html=True)

    # ── Self-serve channel + upsell ───────────────────────────────────
    st.markdown('<div class="section-header">Self-Serve Channels & Upsell Intelligence</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1])
    with c1:
        ssc = dist.get("self_serve_channel", {})
        if ssc:
            labels = [k.upper() if len(k) <= 4 else k.title() for k in ssc.keys()]
            values = [float(v) for v in ssc.values()]
            st.plotly_chart(
                make_donut(labels, values, "Preferred Self-Serve Channel for Deflectable Calls",
                           [TEAL, BLUE, GOLD, PURPLE]),
                use_container_width=True,
            )
    with c2:
        uo = dist.get("upsell_outcome", {})
        if uo:
            labels = [k.replace("_", " ").title() for k in uo.keys()]
            values = [float(v) for v in uo.values()]
            st.plotly_chart(
                make_donut(labels, values, "Upsell Outcome Distribution",
                           [GREY, RED, GREEN, GOLD]),
                use_container_width=True,
            )
            st.markdown(f"""
            <div style="font-size:0.8rem;color:#6B7FA0;text-align:center;margin-top:-10px;">
                {kpis['upsell_attempted_pct']:.0f}% of calls had upsell attempted ·
                Conversion: <strong style="color:{GREEN}">{kpis['upsell_conversion_pct']:.0f}%</strong>
            </div>
            """, unsafe_allow_html=True)

    # ── Executive summary table ───────────────────────────────────────
    st.markdown('<div class="section-header">Executive Action Summary</div>', unsafe_allow_html=True)

    action_data = {
        "Priority": ["🔴 Critical", "🔴 Critical", "🟡 High", "🟡 High", "🟢 Quick Win"],
        "Lever": [
            "Agentic AI Automation",
            "Self-Serve App Deflection",
            "Proactive Outreach Programme",
            "Agent Diagnosis Coaching",
            "Upsell Personalisation",
        ],
        "Opportunity (% calls)": [
            f"{kpis['agentic_ai_resolvable_pct']:.0f}%",
            f"{kpis['self_serve_deflection_pct']:.0f}%",
            f"{kpis['proactive_outreach_pct']:.0f}%",
            f"{float(agent_dist.get('needs_improvement', 0) if agent_dist else 0):.0f}%",
            f"{kpis['upsell_attempted_pct']:.0f}% attempted",
        ],
        "Est. Monthly Savings": [
            f"${cl['agentic_ai_savings_usd']/1000:.0f}K",
            f"${cl['self_serve_savings_usd']/1000:.0f}K",
            f"${cl['proactive_care_savings_usd']/1000:.0f}K",
            "AHT reduction ~15%",
            "Revenue lift",
        ],
        "Next Action": [
            "Define API-resolvable use cases & build agent flows",
            "In-app APN reset, bill explanation, plan comparison tools",
            "Network event → proactive SMS/push notification triggers",
            "Knowledge base gaps identified — retrain on diagnosis phase",
            "Match offers to eligibility data at Discovery phase",
        ],
    }

    df_actions = pd.DataFrame(action_data)
    st.dataframe(
        df_actions,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Priority":                  st.column_config.TextColumn(width="small"),
            "Lever":                     st.column_config.TextColumn(width="medium"),
            "Opportunity (% calls)":     st.column_config.TextColumn(width="small"),
            "Est. Monthly Savings":      st.column_config.TextColumn(width="small"),
            "Next Action":               st.column_config.TextColumn(width="large"),
        },
    )

    # ── Footer ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
        <div style="font-size:0.68rem;color:#4A5568;letter-spacing:0.1em;">
            TELECOM CALL INTELLIGENCE · CALL TIME SEGMENTATION FRAMEWORK ·
            {meta['total_calls_analyzed']} CALLS ANALYSED · {meta['dataset']}
        </div>
        <div style="font-size:0.68rem;color:#4A5568;">
            {meta.get('inference_provider','Groq')} · {meta['model']} · {meta['analysis_timestamp'][:10]}
        </div>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
