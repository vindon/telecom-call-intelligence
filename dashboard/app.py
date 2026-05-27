"""
dashboard/app.py
----------------
Telecom Contact Center Analytics
Customer Call Metadata Segmentation Dashboard

Run:
  streamlit run dashboard/app.py

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
  .hero-meta {
    font-size: 0.78rem;
    color: #64748B;
    margin-top: 10px;
    letter-spacing: 0.04em;
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
    padding: 13px 16px;
    color: #1E293B;
    vertical-align: middle;
    line-height: 1.45;
  }
  .tl-table tbody td:first-child { white-space: nowrap; }

  /* ── Traffic lights ── */
  .tl-dot {
    display: inline-block;
    width: 14px; height: 14px;
    border-radius: 50%;
    vertical-align: middle;
    margin-right: 8px;
    flex-shrink: 0;
  }
  .tl-red    { background:#DC2626; box-shadow: 0 0 8px rgba(220,38,38,0.6); }
  .tl-amber  { background:#D97706; box-shadow: 0 0 8px rgba(217,119,6,0.6); }
  .tl-green  { background:#059669; box-shadow: 0 0 8px rgba(5,150,105,0.6); }

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
        x=["Baseline", "Self-Serve\nDeflection", "Agentic AI\nAutomation",
           "Proactive\nOutreach", "Optimised\nCost"],
        y=[base, -ss, -ai, -pro, net],
        connector=dict(line=dict(color="#E2E8F0", width=1.5)),
        decreasing=dict(marker_color=GREEN),
        increasing=dict(marker_color=RED),
        totals=dict(marker_color=BLUE),
        text=[f"${v/1000:.0f}K" for v in [base, ss, ai, pro, net]],
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


def chart_deflection(kpis: dict) -> go.Figure:
    cats = ["Self-Serve\nEligible", "Agentic AI\nResolvable",
            "Proactive\nOutreach",  "Avoidable\nCalls"]
    vals = [kpis["self_serve_deflection_pct"], kpis["agentic_ai_resolvable_pct"],
            kpis["proactive_outreach_pct"],    kpis["avoidable_call_rate_pct"]]

    fig = go.Figure(go.Bar(
        x=cats, y=vals,
        marker_color=[TEAL, PURPLE, BLUE, RED], marker_line_width=0,
        text=[f"{v:.0f}%" for v in vals],
        textposition="outside", textfont=dict(size=14, color="#0F172A"),
        hovertemplate="<b>%{x}</b><br>%{y:.1f}% of calls<extra></extra>",
    ))
    fig.update_layout(**_lay(
        title=_title("Deflection & Automation Opportunity (% of Calls)"),
        yaxis=dict(ticksuffix="%", gridcolor="#F1F5F9", zeroline=False,
                   range=[0, max(vals)*1.42], tickfont=dict(color="#64748B", size=11)),
        showlegend=False, bargap=0.4,
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

    # ── Hero banner ───────────────────────────────────────────────────
    badge_cls  = "demo" if is_demo else ""
    badge_text = "DEMO DATA" if is_demo else "LIVE DATA"
    st.markdown(f"""
    <div class="hero-banner">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;">
        <div>
          <div class="hero-title">Telecom Call Intelligence</div>
          <div class="hero-subtitle">Customer Call Metadata Segmentation</div>
          <div class="hero-meta" style="color:#FFFFFF;font-size:0.88rem;font-weight:500;margin-top:10px;letter-spacing:0.02em;">
            Cost-to-Serve Optimisation &nbsp;·&nbsp;
            Phase Intelligence &nbsp;·&nbsp;
            Agentic AI Opportunity Sizing
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

    # ── Section 1: Core KPIs ──────────────────────────────────────────
    section("Core Performance KPIs")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    kpi_defs = [
        (c1, f"{kpis['fcr_rate_pct']:.0f}%",              "First Call Resolution",   "green",  "Target ≥ 75%"),
        (c2, f"{kpis['avg_handle_time_minutes']:.1f} min", "Avg Handle Time",         "amber",  "Industry avg: 6–8 min"),
        (c3, f"{kpis['escalation_rate_pct']:.0f}%",        "Escalation Rate",         "red",    "Target < 10%"),
        (c4, f"{kpis['sentiment_improved_pct']:.0f}%",     "Sentiment Improvement",   "teal",   "Start → end of call"),
        (c5, f"{kpis['all_issues_resolved_pct']:.0f}%",    "Issues Fully Resolved",   "blue",   f"Avg {kpis['avg_issues_per_call']:.1f} issues / call"),
        (c6, f"{kpis['agent_tool_struggle_pct']:.0f}%",    "Agent Tool Struggle",     "purple", "Leading AHT inflation indicator"),
    ]
    for col, val, label, accent, delta in kpi_defs:
        with col:
            st.markdown(kpi_card(val, label, accent, delta), unsafe_allow_html=True)

    # ── Section 2: Financial Opportunity ─────────────────────────────
    section("Monthly Cost-to-Serve Opportunity")

    c1, c2, c3, c4 = st.columns(4)
    cost_defs = [
        (c1, f"${cl['total_savings_opportunity_usd']/1000:.0f}K",
              "Total Savings Opportunity", "green",
              f"{cl['savings_pct_of_baseline']:.0f}% of ${cl['baseline_monthly_cost_usd']/1000:.0f}K baseline"),
        (c2, f"${cl['self_serve_savings_usd']/1000:.0f}K",
              "Self-Serve Deflection", "teal",
              f"{kpis['self_serve_deflection_pct']:.0f}% of calls deflectable"),
        (c3, f"${cl['agentic_ai_savings_usd']/1000:.0f}K",
              "Agentic AI Automation", "purple",
              f"{kpis['agentic_ai_resolvable_pct']:.0f}% fully automatable"),
        (c4, f"${cl['proactive_care_savings_usd']/1000:.0f}K",
              "Proactive Outreach", "blue",
              f"{kpis['proactive_outreach_pct']:.0f}% of calls preventable"),
    ]
    for col, val, label, accent, delta in cost_defs:
        with col:
            st.markdown(kpi_card(val, label, accent, delta), unsafe_allow_html=True)

    st.markdown(
        f"<p style='font-size:0.72rem;color:#94A3B8;margin-top:8px;'>"
        f"Estimates based on ${cl['cost_per_call_usd']:.2f}/call industry benchmark × "
        f"{cl['monthly_volume_estimate']:,} calls/month. Replace with actual ACD data for planning.</p>",
        unsafe_allow_html=True,
    )

    # ── Section 3: Phase & Waterfall ──────────────────────────────────
    section("Call Phase Breakdown & Cost Waterfall")

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(chart_phase_bar(phase), use_container_width=True)
    with c2:
        st.plotly_chart(chart_cost_waterfall(cl), use_container_width=True)

    diag_s  = phase.get("Diagnosis", 0)
    disc_s  = phase.get("Discovery", 0)
    tot_s   = sum(phase.values()) or 1
    diag_pc = round(diag_s / tot_s * 100)
    diag_ov = float(dist.get("agent_disproportionate_phase", {}).get("diagnosis", 0))

    st.markdown(f"""
    <div class="insight-box">
      <strong>Phase Insight:</strong> Diagnosis represents <strong>{diag_pc}% of average handle time</strong>
      ({diag_s}s avg). {diag_ov:.0f}% of agents are flagged for disproportionate time in this phase —
      a primary indicator of knowledge base gaps or tool friction.
      Combined, Discovery and Diagnosis account for
      {round((disc_s + diag_s) / tot_s * 100)}% of total AHT.
    </div>
    """, unsafe_allow_html=True)

    # ── Section 4: Issue Mix & Deflection ────────────────────────────
    section("Issue Distribution & Automation Opportunity")

    c1, c2 = st.columns(2)
    with c1:
        ic = dist.get("issue_category", {})
        if ic:
            st.plotly_chart(
                chart_donut(
                    [k.capitalize() for k in ic], list(ic.values()),
                    "Issue Category Breakdown",
                    [BLUE, RED, PURPLE, AMBER, GREEN, TEAL, SLATE],
                ),
                use_container_width=True,
            )
    with c2:
        st.plotly_chart(chart_deflection(kpis), use_container_width=True)

    # ── Section 5: Agent & Sentiment ──────────────────────────────────
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

    # ── Section 6: Upsell Intelligence ───────────────────────────────
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
            f"{kpis['upsell_attempted_pct']:.0f}%", "Upsell Attempted", "amber", "of eligible calls"
        ), unsafe_allow_html=True)
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        st.markdown(kpi_card(
            f"{kpis['upsell_conversion_pct']:.0f}%", "Upsell Conversion Rate", "green", "when attempted"
        ), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card(
            f"{kpis['avoidable_call_rate_pct']:.0f}%", "Avoidable Call Rate", "red",
            "Deflectable or preventable"
        ), unsafe_allow_html=True)
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        st.markdown(kpi_card(
            f"{kpis['proactive_outreach_pct']:.0f}%", "Proactive Outreach Eligible", "blue",
            "Preventable via notification"
        ), unsafe_allow_html=True)

    # ── Section 7: Executive Action Plan with Traffic Lights ─────────
    section("Executive Action Plan")

    # Legend
    st.markdown("""
    <div style="display:flex;align-items:center;gap:20px;font-size:0.78rem;
                color:#475569;margin-bottom:14px;flex-wrap:wrap;">
      <span style="font-weight:600;color:#1E293B;">Priority Signal:</span>
      <span style="display:flex;align-items:center;gap:6px;">
        <span class="tl-dot tl-red"   style="width:13px;height:13px;display:inline-block;border-radius:50%;background:#DC2626;box-shadow:0 0 8px rgba(220,38,38,0.6);"></span>
        <strong style="color:#991B1B;">Critical</strong> — Immediate action required
      </span>
      <span style="display:flex;align-items:center;gap:6px;">
        <span class="tl-dot tl-amber" style="width:13px;height:13px;display:inline-block;border-radius:50%;background:#D97706;box-shadow:0 0 8px rgba(217,119,6,0.6);"></span>
        <strong style="color:#92400E;">High</strong> — Plan within this quarter
      </span>
      <span style="display:flex;align-items:center;gap:6px;">
        <span class="tl-dot tl-green" style="width:13px;height:13px;display:inline-block;border-radius:50%;background:#059669;box-shadow:0 0 8px rgba(5,150,105,0.6);"></span>
        <strong style="color:#065F46;">Quick Win</strong> — Low effort, fast ROI
      </span>
    </div>
    """, unsafe_allow_html=True)

    rows = [
        ("Critical",  "Agentic AI Call Automation",
         f"{kpis['agentic_ai_resolvable_pct']:.0f}% of calls",
         f"${cl['agentic_ai_savings_usd']/1000:.0f}K / month",
         "Map API-resolvable intents; build LangGraph agent flows for top 3 use cases"),
        ("Critical",  "Self-Serve App Deflection",
         f"{kpis['self_serve_deflection_pct']:.0f}% of calls",
         f"${cl['self_serve_savings_usd']/1000:.0f}K / month",
         "Publish in-app APN reset, bill explanation, and plan comparison self-serve tools"),
        ("High",      "Proactive Outreach Programme",
         f"{kpis['proactive_outreach_pct']:.0f}% of calls",
         f"${cl['proactive_care_savings_usd']/1000:.0f}K / month",
         "Trigger SMS/push notifications on network events before customers call"),
        ("High",      "Agent Knowledge Base & Tooling",
         f"{needs_imp:.0f}% of agents rated NI",
         "AHT reduction ~15–20%",
         "Identify Diagnosis-phase gaps; deliver targeted coaching and knowledge-base updates"),
        ("Quick Win", "Upsell Personalisation Engine",
         f"{kpis['upsell_attempted_pct']:.0f}% attempted",
         "Revenue lift",
         "Surface personalised offers at Discovery using eligibility & usage propensity signals"),
    ]

    rows_html = "".join(
        f"<tr>"
        f"<td>{_tl_pill(p)}</td>"
        f"<td><strong>{init}</strong></td>"
        f"<td style='color:#475569;'>{scope}</td>"
        f"<td><strong style='color:#059669;'>{impact}</strong></td>"
        f"<td style='color:#334155;font-size:0.84rem;'>{action}</td>"
        f"</tr>"
        for p, init, scope, impact, action in rows
    )

    st.markdown(f"""
    <table class="tl-table">
      <thead>
        <tr>
          <th>Priority</th>
          <th>Initiative</th>
          <th>Scope</th>
          <th>Est. Impact</th>
          <th>Recommended Next Step</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    """, unsafe_allow_html=True)

    # ── Footer ────────────────────────────────────────────────────────
    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='dash-footer'>"
        f"<span>Telecom Call Intelligence &nbsp;·&nbsp; Customer Call Metadata Segmentation"
        f" &nbsp;·&nbsp; {n_calls:,} calls analysed &nbsp;·&nbsp; {html.escape(meta['dataset'])}</span>"
        f"<span>{provider} &nbsp;·&nbsp; {model} &nbsp;·&nbsp; {run_date}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
