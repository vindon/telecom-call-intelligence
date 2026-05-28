"""
dashboard/app.py — Telecom Call Intelligence
Executive brief: makes the case for autonomous AI resolution of contact centre calls.

Run:  streamlit run dashboard/app.py
"""

import html
import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Telecom Call Intelligence",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

  html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background: #F8FAFC;
    color: #0F172A;
  }
  .main { background: #F8FAFC; }
  .block-container { padding-top: 0 !important; padding-bottom: 2rem; }

  .hero {
    background: linear-gradient(135deg, #0F172A 0%, #1E3A5F 55%, #1D4ED8 100%);
    padding: 40px 44px 36px;
    margin: -1rem -1rem 0;
    border-radius: 0 0 20px 20px;
  }
  .hero-title { font-size:2.8rem; font-weight:900; color:#fff; letter-spacing:-0.03em; margin:0 0 6px; }
  .hero-sub   { font-size:1rem;  font-weight:400; color:#93C5FD; margin:0; }
  .hero-stat  { font-size:3.6rem; font-weight:900; color:#34D399; letter-spacing:-0.04em; line-height:1; }
  .hero-stat-label { font-size:0.95rem; color:#93C5FD; font-weight:500; }
  .hero-badge {
    display:inline-block; padding:4px 14px; border-radius:20px; font-size:0.7rem;
    font-weight:700; letter-spacing:0.1em; text-transform:uppercase;
  }
  .badge-live { background:rgba(16,185,129,.2); border:1px solid rgba(16,185,129,.4); color:#34D399; }
  .badge-demo { background:rgba(99,102,241,.2); border:1px solid rgba(99,102,241,.4); color:#A5B4FC; }

  .section-label {
    font-size:0.65rem; font-weight:800; letter-spacing:0.18em; text-transform:uppercase;
    color:#94A3B8; margin: 32px 0 16px; padding-bottom:8px;
    border-bottom: 1px solid #E2E8F0;
  }

  /* KPI card */
  .kcard {
    background:#fff; border-radius:12px; padding:22px 20px 18px;
    box-shadow:0 1px 3px rgba(15,23,42,.07);
    border-left:4px solid #E2E8F0;
  }
  .kcard.green  { border-left-color:#059669; }
  .kcard.red    { border-left-color:#DC2626; }
  .kcard.amber  { border-left-color:#D97706; }
  .kcard.teal   { border-left-color:#0D9488; }
  .kcard.purple { border-left-color:#7C3AED; }
  .kcard.blue   { border-left-color:#2563EB; }
  .kcard-val   { font-size:2.4rem; font-weight:800; color:#0F172A; letter-spacing:-0.03em; line-height:1.1; margin:6px 0 4px; }
  .kcard-label { font-size:0.65rem; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; color:#64748B; }
  .kcard-delta { font-size:0.72rem; color:#94A3B8; margin-top:5px; }

  /* Segment block */
  .seg {
    background:#fff; border-radius:12px; padding:28px 22px 22px;
    box-shadow:0 1px 3px rgba(15,23,42,.07); text-align:center;
  }
  .seg-badge {
    display:inline-block; padding:3px 12px; border-radius:20px;
    font-size:0.62rem; font-weight:700; letter-spacing:0.12em; text-transform:uppercase;
    margin-bottom:12px;
  }
  .seg-pct   { font-size:3.8rem; font-weight:900; letter-spacing:-0.05em; line-height:1; }
  .seg-calls { font-size:0.82rem; color:#94A3B8; margin:4px 0 14px; }
  .seg-money { font-size:1.25rem; font-weight:700; }
  .seg-desc  { font-size:0.78rem; color:#64748B; margin-top:10px; line-height:1.55; }

  /* Automation roadmap table */
  .road-table {
    width:100%; border-collapse:collapse; font-size:0.86rem;
    background:#fff; border-radius:12px; overflow:hidden;
    box-shadow:0 1px 3px rgba(15,23,42,.07);
  }
  .road-table thead tr { background:#0F172A; color:#E2E8F0; }
  .road-table thead th {
    padding:12px 16px; text-align:left; font-size:0.65rem;
    font-weight:700; letter-spacing:0.1em; text-transform:uppercase;
  }
  .road-table tbody tr { border-bottom:1px solid #F1F5F9; }
  .road-table tbody tr:last-child { border-bottom:none; }
  .road-table tbody td { padding:12px 16px; color:#1E293B; vertical-align:middle; }
  .road-table tbody tr:hover { background:#F8FAFC; }

  /* Scorecard table */
  .score-table {
    width:100%; border-collapse:collapse; font-size:0.86rem;
    background:#fff; border-radius:12px; overflow:hidden;
    box-shadow:0 1px 3px rgba(15,23,42,.07);
  }
  .score-table thead tr { background:#0F172A; color:#E2E8F0; }
  .score-table thead th {
    padding:12px 16px; font-size:0.65rem; font-weight:700;
    letter-spacing:0.1em; text-transform:uppercase; text-align:left;
  }
  .score-table tbody tr { border-bottom:1px solid #F1F5F9; }
  .score-table tbody td { padding:11px 16px; vertical-align:middle; }

  /* Action plan table */
  .action-table {
    width:100%; border-collapse:collapse; font-size:0.88rem;
    background:#fff; border-radius:12px; overflow:hidden;
    box-shadow:0 1px 3px rgba(15,23,42,.07);
  }
  .action-table thead tr { background:#0F172A; color:#E2E8F0; }
  .action-table thead th {
    padding:12px 18px; font-size:0.65rem; font-weight:700;
    letter-spacing:0.1em; text-transform:uppercase; text-align:left;
  }
  .action-table tbody tr { border-bottom:1px solid #F1F5F9; }
  .action-table tbody td { padding:14px 18px; color:#1E293B; vertical-align:middle; line-height:1.5; }

  .dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:7px; }
  .dot-red    { background:#DC2626; box-shadow:0 0 6px rgba(220,38,38,.5); }
  .dot-amber  { background:#D97706; box-shadow:0 0 6px rgba(217,119,6,.5); }
  .dot-green  { background:#059669; box-shadow:0 0 6px rgba(5,150,105,.5); }

  .pill {
    display:inline-flex; align-items:center; padding:3px 10px;
    border-radius:20px; font-size:0.7rem; font-weight:700; letter-spacing:.06em; white-space:nowrap;
  }
  .pill-crit  { background:#FEF2F2; color:#991B1B; border:1px solid #FECACA; }
  .pill-high  { background:#FFFBEB; color:#92400E; border:1px solid #FDE68A; }
  .pill-quick { background:#ECFDF5; color:#065F46; border:1px solid #6EE7B7; }

  .callout {
    background:#EFF6FF; border-left:4px solid #2563EB; border-radius:8px;
    padding:14px 18px; font-size:0.86rem; color:#1E3A8A; line-height:1.6;
  }
  .callout.green { background:#ECFDF5; border-left-color:#059669; color:#064E3B; }
  .callout.amber { background:#FFFBEB; border-left-color:#D97706; color:#78350F; }

  .footer { font-size:0.68rem; color:#94A3B8; display:flex; justify-content:space-between; flex-wrap:wrap; gap:4px; padding-top:8px; }

  #MainMenu,footer,header { visibility:hidden; }
</style>
""", unsafe_allow_html=True)

# ── Palette ───────────────────────────────────────────────────────────
TEAL   = "#0D9488"
PURPLE = "#7C3AED"
BLUE   = "#2563EB"
GREEN  = "#059669"
RED    = "#DC2626"
AMBER  = "#D97706"
SLATE  = "#64748B"

PLOTLY = dict(
    paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
    font=dict(family="Inter, sans-serif", color="#334155", size=12),
)

# ── Benchmark targets ─────────────────────────────────────────────────
BENCHMARKS = [
    ("First Call Resolution",     "fcr_rate_pct",             75,  "%",    True),
    ("Avg Handle Time",           "avg_handle_time_minutes",  6.0, " min", False),
    ("Escalation Rate",           "escalation_rate_pct",      10,  "%",    False),
    ("Issues Resolved",           "all_issues_resolved_pct",  80,  "%",    True),
    ("Sentiment Improvement",     "sentiment_improved_pct",   70,  "%",    True),
    ("Agent Tool Struggle",       "agent_tool_struggle_pct",  15,  "%",    False),
    ("Self-Serve Eligible",       "self_serve_deflection_pct",30,  "%",    True),
    ("Agentic AI Resolvable",     "agentic_ai_resolvable_pct",40,  "%",    True),
    ("Proactive Outreach",        "proactive_outreach_pct",   20,  "%",    True),
]

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
        "avg_handle_time_seconds": 524, "avg_handle_time_minutes": 8.7,
        "fcr_rate_pct": 68.0, "avoidable_call_rate_pct": 41.0,
        "self_serve_deflection_pct": 37.0, "agentic_ai_resolvable_pct": 29.0,
        "proactive_outreach_pct": 24.0, "all_issues_resolved_pct": 71.0,
        "escalation_rate_pct": 14.0, "upsell_attempted_pct": 52.0,
        "upsell_conversion_pct": 18.0, "sentiment_improved_pct": 61.0,
        "agent_tool_struggle_pct": 23.0, "multi_issue_call_pct": 38.0,
        "avg_issues_per_call": 1.4, "avg_hold_time_seconds": 87,
        "avg_hold_count": 1.2, "avg_empathy_statements": 3.1,
    },
    "phase_avg_seconds": {
        "Welcome & Auth": 46, "Discovery": 108, "Diagnosis": 152,
        "Resolution": 128, "Hold": 87, "Upsell": 44, "Closing": 54,
    },
    "distributions": {
        "issue_category": {
            "billing": 38, "technical": 31, "plan": 16,
            "account": 9,  "device": 4,    "information": 2,
        },
        "agent_skill":     {"proficient": "44.0", "adequate": "38.0", "needs_improvement": "18.0"},
        "repeat_call_risk":{"low": "43.0", "medium": "38.0", "high": "19.0"},
        "agent_disproportionate_phase": {
            "none": "48.0", "diagnosis": "26.0", "discovery": "14.0", "resolution": "12.0",
        },
    },
    "cost_levers": {
        "cost_per_call_usd": 6.0, "monthly_volume_estimate": 100000,
        "baseline_monthly_cost_usd": 600000,
        "self_serve_savings_usd": 188700, "agentic_ai_savings_usd": 121800,
        "proactive_care_savings_usd": 86400, "total_savings_opportunity_usd": 396900,
        "savings_pct_of_baseline": 66.2,
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
            data["cost_levers"] = _cost_levers(data["kpis"])
        return data, False
    return DEMO_DATA, True


def load_run_history() -> list[dict]:
    path = Path("outputs/agent_memory.json")
    if not path.exists():
        return []
    try:
        with open(path) as f:
            mem = json.load(f)
        runs = mem.get("run_history", [])
        for r in runs:
            ts = r.get("timestamp", "")
            r["_dt"] = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}" if len(ts) == 15 else ts
        return sorted(runs, key=lambda r: r.get("_dt", ""))
    except Exception:
        return []


def _cost_levers(kpis: dict) -> dict:
    cpp, vol = 6.0, 100_000
    base = cpp * vol
    ss  = base * kpis.get("self_serve_deflection_pct", 0) / 100
    ai  = base * kpis.get("agentic_ai_resolvable_pct",  0) / 100
    pro = base * kpis.get("proactive_outreach_pct",     0) / 100
    tot = ss + ai + pro
    return {
        "cost_per_call_usd": cpp, "monthly_volume_estimate": vol,
        "baseline_monthly_cost_usd": base, "self_serve_savings_usd": ss,
        "agentic_ai_savings_usd": ai, "proactive_care_savings_usd": pro,
        "total_savings_opportunity_usd": tot,
        "savings_pct_of_baseline": tot / base * 100 if base else 0,
    }


# ── Charts ────────────────────────────────────────────────────────────

def chart_segment_bar(proactive: float, digital: float, human: float, n: int) -> go.Figure:
    """Single stacked horizontal bar — the three segments at a glance."""
    p_n, d_n = round(n * proactive / 100), round(n * digital / 100)
    h_n = n - p_n - d_n
    fig = go.Figure()
    for name, pct, calls, color in [
        ("Proactive Care",          proactive, p_n, TEAL),
        ("Agentic AI / Self-Serve", digital,   d_n, PURPLE),
        ("Human Agent Required",    human,     h_n, BLUE),
    ]:
        lbl = f"  {pct:.0f}%  ({calls} calls)" if pct >= 6 else ""
        fig.add_trace(go.Bar(
            name=name, x=[pct], y=[""], orientation="h",
            marker_color=color, marker_line_width=0,
            text=[lbl], textposition="inside", insidetextanchor="start",
            textfont=dict(color="white", size=12, family="Inter"),
            hovertemplate=f"<b>{name}</b><br>{pct:.1f}% · {calls} calls<extra></extra>",
        ))
    fig.update_layout(
        **PLOTLY,
        barmode="stack", height=90,
        xaxis=dict(range=[0, 100], ticksuffix="%", gridcolor="#F1F5F9",
                   zeroline=False, tickfont=dict(size=11, color="#94A3B8")),
        yaxis=dict(showticklabels=False),
        margin=dict(l=8, r=8, t=8, b=28),
        showlegend=True,
        legend=dict(orientation="h", y=-0.8, x=0, yanchor="top",
                    font=dict(size=11, color="#475569")),
    )
    return fig


def chart_trend(runs: list, field: str, label: str, unit: str,
                target: float | None, color: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[r["_dt"] for r in runs], y=[r.get(field) for r in runs],
        mode="lines+markers",
        line=dict(color=color, width=2.5),
        marker=dict(size=7, color=color),
        hovertemplate=f"%{{x}}<br>{label}: %{{y}}{unit}<extra></extra>",
    ))
    if target is not None:
        fig.add_hline(y=target, line_dash="dot", line_color="#94A3B8", line_width=1.5,
                      annotation_text=f"Target {target}{unit}",
                      annotation_font_size=10, annotation_font_color="#94A3B8")
    fig.update_layout(
        **PLOTLY,
        title=dict(text=label, font=dict(size=13, color="#0F172A"), x=0),
        height=210,
        xaxis=dict(tickfont=dict(size=9, color="#94A3B8")),
        yaxis=dict(title=unit),
        margin=dict(l=32, r=12, t=40, b=28),
    )
    return fig


# ── HTML helpers ──────────────────────────────────────────────────────

def _sec(label: str) -> None:
    st.markdown(f'<div class="section-label">{label}</div>', unsafe_allow_html=True)


def _kcard(val: str, label: str, color: str = "", delta: str = "") -> str:
    d = f'<div class="kcard-delta">{delta}</div>' if delta else ""
    return (f'<div class="kcard {color}">'
            f'<div class="kcard-label">{label}</div>'
            f'<div class="kcard-val">{val}</div>{d}</div>')


def _seg(badge: str, badge_bg: str, badge_fg: str, pct: float, n: int,
         money: str, money_color: str, desc: str) -> str:
    return (
        f'<div class="seg">'
        f'<span class="seg-badge" style="background:{badge_bg};color:{badge_fg};">{badge}</span><br>'
        f'<div class="seg-pct" style="color:{badge_fg};">{pct:.0f}%</div>'
        f'<div class="seg-calls">{n:,} of calls analysed</div>'
        f'<div class="seg-money" style="color:{money_color};">{money}</div>'
        f'<div class="seg-desc">{desc}</div>'
        f'</div>'
    )


def _dot(cls: str) -> str:
    return f'<span class="dot {cls}"></span>'


def _pill(priority: str) -> str:
    m = {"Critical": ("dot-red", "pill-crit", "CRITICAL"),
         "High":     ("dot-amber","pill-high", "HIGH"),
         "Quick Win":("dot-green","pill-quick","QUICK WIN")}
    dc, pc, lbl = m.get(priority, ("dot-green", "pill-quick", priority.upper()))
    return f'<span class="pill {pc}"><span class="dot {dc}"></span>{lbl}</span>'


# ── Automation roadmap builder ────────────────────────────────────────

# Intents that map to each issue category with automation type and effort
_INTENTS = {
    "billing":     [("Bill explanation & itemised charges", "Agentic AI",  "Low",    0.10),
                    ("Payment / direct debit setup",        "Agentic AI",  "Low",    0.06),
                    ("Billing dispute investigation",       "Human Agent", "—",      0.22)],
    "technical":   [("Network / outage status check",      "Proactive",   "Medium", 0.12),
                    ("Service activation / provisioning",  "Agentic AI",  "Low",    0.08),
                    ("Complex fault diagnosis",            "Human Agent", "—",      0.25)],
    "plan":        [("Plan details & inclusions enquiry",  "Agentic AI",  "Low",    0.08),
                    ("Data balance & usage check",         "Agentic AI",  "Low",    0.07),
                    ("Plan upgrade / change",              "Human Agent", "—",      0.05)],
    "account":     [("Address / contact detail update",    "Agentic AI",  "Low",    0.05),
                    ("Account security & identity",        "Human Agent", "—",      0.04)],
    "information": [("General service enquiries",          "Agentic AI",  "Low",    0.02)],
    "device":      [("Order & delivery status",            "Agentic AI",  "Low",    0.02),
                    ("Device hardware fault",              "Human Agent", "—",      0.02)],
}

_TIER_COLOR = {
    "Proactive":   (TEAL,   "#CCFBF1", "#0F766E"),
    "Agentic AI":  (PURPLE, "#EDE9FE", "#6D28D9"),
    "Human Agent": (BLUE,   "#DBEAFE", "#1D4ED8"),
}


def _build_roadmap(issue_categories: dict, cost_per_call: float, monthly_vol: int) -> list[dict]:
    total_calls = sum(issue_categories.values()) or 1
    rows = []
    for cat, cat_count in issue_categories.items():
        intents = _INTENTS.get(cat, [])
        for intent, tier, effort, share in intents:
            if tier == "Human Agent":
                continue
            est_calls   = round(monthly_vol * (cat_count / total_calls) * share)
            est_saving  = est_calls * cost_per_call
            rows.append({
                "intent": intent, "tier": tier, "effort": effort,
                "monthly_calls": est_calls, "monthly_saving": est_saving,
            })
    rows.sort(key=lambda r: -r["monthly_saving"])
    return rows


# ── Main ──────────────────────────────────────────────────────────────

def main():
    data, is_demo = load_summary()
    kpis = data["kpis"]
    cl   = data["cost_levers"]
    meta = data["meta"]
    dist = data["distributions"]

    n_calls  = meta["total_calls_analyzed"]
    run_date = html.escape(meta.get("analysis_timestamp", "")[:10])
    model    = html.escape(meta.get("model", ""))
    provider = html.escape(meta.get("inference_provider", ""))

    # ── Segment arithmetic ────────────────────────────────────────────
    proactive_pct = float(kpis.get("proactive_outreach_pct",    0))
    selfserve_pct = float(kpis.get("self_serve_deflection_pct", 0))
    agentic_pct   = float(kpis.get("agentic_ai_resolvable_pct", 0))
    digital_pct   = min(selfserve_pct + agentic_pct, max(100.0 - proactive_pct, 0.0))
    human_pct     = max(100.0 - proactive_pct - digital_pct, 0.0)
    total_auto    = proactive_pct + digital_pct
    cpp           = cl["cost_per_call_usd"]
    vol           = cl["monthly_volume_estimate"]
    total_opp     = cl["total_savings_opportunity_usd"]

    # ── Hero ──────────────────────────────────────────────────────────
    badge = "DEMO DATA" if is_demo else "LIVE DATA"
    badge_cls = "badge-demo" if is_demo else "badge-live"
    st.markdown(f"""
    <div class="hero">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;
                  flex-wrap:wrap;gap:20px;">
        <div>
          <div class="hero-title">Telecom Call Intelligence</div>
          <div class="hero-sub">Autonomous Resolution Opportunity — Contact Centre Analysis</div>
          <div style="margin-top:20px;display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;">
            <span class="hero-stat">{total_auto:.0f}%</span>
            <div>
              <div class="hero-stat-label">of contacts are candidates for autonomous resolution</div>
              <div style="font-size:0.82rem;color:#64748B;margin-top:2px;">
                {n_calls:,} calls analysed &nbsp;·&nbsp; ${total_opp/1000:.0f}K/month opportunity
              </div>
            </div>
          </div>
        </div>
        <div style="text-align:right;">
          <span class="hero-badge {badge_cls}">{badge}</span>
          <div style="font-size:0.75rem;color:#475569;margin-top:8px;line-height:1.8;">
            {run_date}<br>{provider}<br>{model}
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if is_demo:
        st.markdown("""<div class="callout" style="margin-top:14px;">
          <strong>Demo mode.</strong> Run <code>python run_pipeline.py</code> to load live results.
        </div>""", unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════
    # 1 — TODAY'S BASELINE
    # ═══════════════════════════════════════════════════════════════
    _sec("1 — Current State")

    c1, c2, c3, c4, c5 = st.columns(5)
    pairs = [
        (c1, f"${cl['baseline_monthly_cost_usd']/1000:.0f}K",
              "Monthly Contact Cost", "red",
              f"${cpp:.2f}/call × {vol:,}/mo"),
        (c2, f"{kpis['fcr_rate_pct']:.0f}%",
              "First Call Resolution", "amber",
              "Target ≥ 75%"),
        (c3, f"{kpis['escalation_rate_pct']:.0f}%",
              "Escalation Rate", "red",
              "Target < 10%"),
        (c4, f"{kpis['avg_handle_time_minutes']:.1f} min",
              "Avg Handle Time", "amber",
              "Industry avg: 6–8 min"),
        (c5, f"{kpis['avoidable_call_rate_pct']:.0f}%",
              "Avoidable Call Rate", "purple",
              "Calls that shouldn't have happened"),
    ]
    for col, val, lbl, clr, dlt in pairs:
        with col:
            st.markdown(_kcard(val, lbl, clr, dlt), unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════
    # 2 — THE AUTOMATION OPPORTUNITY
    # ═══════════════════════════════════════════════════════════════
    _sec("2 — Autonomous Resolution Opportunity")

    c1, c2, c3 = st.columns(3)
    digital_savings = cl["self_serve_savings_usd"] + cl["agentic_ai_savings_usd"]
    residual = cl["baseline_monthly_cost_usd"] - total_opp

    with c1:
        st.markdown(_seg(
            badge="PREVENT", badge_bg="#CCFBF1", badge_fg="#0F766E",
            pct=proactive_pct, n=round(n_calls * proactive_pct / 100),
            money=f"${cl['proactive_care_savings_usd']/1000:.0f}K / month" if cl["proactive_care_savings_usd"] > 0 else "Opportunity not yet captured",
            money_color=TEAL,
            desc="System can detect and notify before the customer calls — network outage, "
                 "bill spike, data near exhaustion, payment failing.",
        ), unsafe_allow_html=True)
    with c2:
        st.markdown(_seg(
            badge="AUTOMATE", badge_bg="#EDE9FE", badge_fg="#6D28D9",
            pct=digital_pct, n=round(n_calls * digital_pct / 100),
            money=f"${digital_savings/1000:.0f}K / month",
            money_color=PURPLE,
            desc=f"Deterministic issues an AI agent can resolve end-to-end: "
                 f"plan enquiry, bill explanation, order status, payments, balance checks. "
                 f"({selfserve_pct:.0f}% self-serve · {agentic_pct:.0f}% full AI agent)",
        ), unsafe_allow_html=True)
    with c3:
        st.markdown(_seg(
            badge="HUMAN REQUIRED", badge_bg="#DBEAFE", badge_fg="#1D4ED8",
            pct=human_pct, n=round(n_calls * human_pct / 100),
            money=f"${residual/1000:.0f}K / month — irreducible",
            money_color=BLUE,
            desc="Complex faults, billing disputes, complaints, retention — "
                 "judgment-intensive situations that require an empathetic skilled agent. "
                 "Focus your human investment here.",
        ), unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.plotly_chart(
        chart_segment_bar(proactive_pct, digital_pct, human_pct, n_calls),
        use_container_width=True,
    )

    annual = total_opp * 12
    st.markdown(f"""
    <div class="callout green" style="margin-top:4px;">
      <strong>Automation business case:</strong> &nbsp;
      {total_auto:.0f}% of current contact volume ({round(vol * total_auto / 100):,} calls/month) is
      addressable through autonomous AI — proactive alerts and AI agent resolution.
      At ${cpp:.2f}/call that's <strong>${total_opp/1000:.0f}K/month · ${annual/1e6:.1f}M/year</strong>
      in recoverable cost, before any customer experience benefit is counted.
    </div>
    """, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════
    # 3 — AUTOMATION ROADMAP: WHICH AGENTS TO BUILD FIRST
    # ═══════════════════════════════════════════════════════════════
    _sec("3 — Which AI Agents to Build — Prioritised by ROI")

    ic   = dist.get("issue_category", {})
    rows = _build_roadmap(ic, cpp, vol)

    if rows:
        total_roadmap_saving = sum(r["monthly_saving"] for r in rows)
        road_rows_html = ""
        for i, r in enumerate(rows, 1):
            color, bg, fg = _TIER_COLOR.get(r["tier"], (SLATE, "#F1F5F9", "#334155"))
            tier_badge = (
                f'<span style="display:inline-block;padding:2px 9px;border-radius:12px;'
                f'font-size:0.7rem;font-weight:700;background:{bg};color:{fg};">'
                f'{r["tier"]}</span>'
            )
            effort_color = "#059669" if r["effort"] == "Low" else "#D97706"
            road_rows_html += (
                f"<tr>"
                f"<td style='font-weight:600;color:#0F172A;'>{r['intent']}</td>"
                f"<td style='text-align:right;color:#64748B;'>{r['monthly_calls']:,}</td>"
                f"<td>{tier_badge}</td>"
                f"<td style='text-align:right;font-weight:700;color:#059669;'>"
                f"${r['monthly_saving']/1000:.0f}K</td>"
                f"<td style='text-align:center;font-weight:600;color:{effort_color};'>"
                f"{r['effort']}</td>"
                f"</tr>"
            )

        st.markdown(f"""
        <table class="road-table">
          <thead><tr>
            <th>Call Intent</th>
            <th style='text-align:right;'>Calls / Month</th>
            <th>Resolution Type</th>
            <th style='text-align:right;'>Saving / Month</th>
            <th style='text-align:center;'>Build Effort</th>
          </tr></thead>
          <tbody>{road_rows_html}</tbody>
        </table>
        """, unsafe_allow_html=True)

        st.markdown(
            f"<p style='font-size:0.71rem;color:#94A3B8;margin-top:8px;'>"
            f"Call volumes estimated from analysis ({n_calls} calls) extrapolated to "
            f"{vol:,} monthly volume. Total addressable saving: "
            f"<strong>${total_roadmap_saving/1000:.0f}K/month</strong>. "
            f"Validate intents against your live IVR taxonomy before build.</p>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="callout">No issue category data available. '
            "Run the pipeline to populate the roadmap.</div>",
            unsafe_allow_html=True,
        )

    # ═══════════════════════════════════════════════════════════════
    # 4 — BENCHMARK SCORECARD
    # ═══════════════════════════════════════════════════════════════
    _sec("4 — Actual vs Industry Benchmark")

    c1, c2 = st.columns([1, 1])

    def _score_rows(fields):
        out = ""
        for lbl, field, target, unit, hb in fields:
            actual = float(kpis.get(field, 0))
            if hb:
                gap, on = actual - target, actual >= target
            else:
                gap, on = target - actual, actual <= target
            close = abs(actual - target) / (target or 1) < 0.20
            if on:
                dot, gc = "dot-green", "#059669"
                gs = f"▲ +{abs(gap):.1f}{unit}"
            elif close:
                dot, gc = "dot-amber", "#D97706"
                gs = f"{'▲' if gap >= 0 else '▼'} {abs(gap):.1f}{unit}"
            else:
                dot, gc = "dot-red", "#DC2626"
                gs = f"▼ {abs(gap):.1f}{unit}"
            out += (
                f"<tr>"
                f"<td><span class='dot {dot}'></span>{lbl}</td>"
                f"<td style='text-align:right;font-weight:700;'>{actual:.0f}{unit}</td>"
                f"<td style='text-align:right;color:#64748B;'>{target:.0f}{unit}</td>"
                f"<td style='text-align:right;font-weight:700;color:{gc};'>{gs}</td>"
                f"</tr>"
            )
        return out

    header = ("<thead><tr>"
              "<th>KPI</th>"
              "<th style='text-align:right;'>Actual</th>"
              "<th style='text-align:right;'>Target</th>"
              "<th style='text-align:right;'>Gap</th>"
              "</tr></thead>")

    mid = len(BENCHMARKS) // 2
    with c1:
        st.markdown(
            f'<table class="score-table">{header}<tbody>'
            f'{_score_rows(BENCHMARKS[:mid])}</tbody></table>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<table class="score-table">{header}<tbody>'
            f'{_score_rows(BENCHMARKS[mid:])}</tbody></table>',
            unsafe_allow_html=True,
        )

    # ═══════════════════════════════════════════════════════════════
    # 5 — ACTION PLAN
    # ═══════════════════════════════════════════════════════════════
    _sec("5 — Prioritised Action Plan")

    needs_imp = float(dist.get("agent_skill", {}).get("needs_improvement", 0))

    actions = [
        ("Critical", "Build Agentic AI Agents",
         f"{agentic_pct:.0f}% of calls automatable",
         f"${cl['agentic_ai_savings_usd']/1000:.0f}K / month",
         "Build LangGraph agent flows for the top 5 intents in the roadmap above: plan enquiry, "
         "bill explanation, service activation, order status, payments. Start with Low effort first."),
        ("Critical", "Deploy Proactive Care Notifications",
         f"{proactive_pct:.0f}% of calls preventable",
         f"${cl['proactive_care_savings_usd']/1000:.0f}K / month",
         "Wire event-driven alerts: network outage detected → SMS before customer calls. "
         "Bill spike → push notification. Data near exhaustion → in-app alert. "
         "Eliminates the contact entirely."),
        ("High", "Redirect Self-Serve Eligible Calls to Digital",
         f"{selfserve_pct:.0f}% of calls deflectable",
         f"${cl['self_serve_savings_usd']/1000:.0f}K / month",
         "Route IVR intents for balance, plan info, and order status directly to the app / chatbot. "
         "Publish in-app guides for the top 3 self-serve reasons identified in this analysis."),
        ("High", "Protect Agent Time for Human-Only Contacts",
         f"{human_pct:.0f}% genuinely needs agents",
         "Quality + NPS lift",
         "Once AI handles the automatable segment, agents focus entirely on disputes, complex faults, "
         "and retention. Redeploy or right-size agent capacity against the residual human volume."),
        ("Quick Win", "Coach Agents on Diagnosis-Phase Tooling",
         f"{needs_imp:.0f}% agents rated Needs Improvement",
         "15–20% AHT reduction",
         "Call analysis flags diagnosis-phase tool struggle as the primary AHT driver. "
         "Targeted knowledge-base and tooling coaching on top technical and billing categories."),
    ]

    rows_html = "".join(
        f"<tr>"
        f"<td style='width:90px;'>{_pill(p)}</td>"
        f"<td style='font-weight:700;'>{html.escape(init)}</td>"
        f"<td style='color:#64748B;font-size:0.84rem;'>{html.escape(scope)}</td>"
        f"<td style='font-weight:700;color:#059669;white-space:nowrap;'>{html.escape(impact)}</td>"
        f"<td style='color:#334155;font-size:0.84rem;max-width:340px;'>{html.escape(action)}</td>"
        f"</tr>"
        for p, init, scope, impact, action in actions
    )

    st.markdown(f"""
    <table class="action-table">
      <thead><tr>
        <th>Priority</th><th>Initiative</th><th>Scope</th>
        <th>Est. Impact</th><th>What to Do</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    """, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════
    # 6 — PERFORMANCE TRENDS (if data available)
    # ═══════════════════════════════════════════════════════════════
    runs = load_run_history()
    if len(runs) >= 2:
        _sec("6 — Performance Trends Across Runs")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.plotly_chart(chart_trend(runs, "fcr_rate_pct", "First Call Resolution",
                                        "%", 75, GREEN), use_container_width=True)
        with c2:
            st.plotly_chart(chart_trend(runs, "aht_minutes", "Avg Handle Time",
                                        " min", 6, AMBER), use_container_width=True)
        with c3:
            st.plotly_chart(chart_trend(runs, "qa_avg_score", "QA Score",
                                        "", 85, BLUE), use_container_width=True)

        latest, prev = runs[-1], runs[-2]
        def _d(v, hg):
            s = "+" if v >= 0 else ""
            c = "#059669" if (v >= 0) == hg else "#DC2626"
            return f"<span style='color:{c};font-weight:600;'>{'↑' if v>=0 else '↓'} {s}{v:.1f}</span>"

        st.markdown(f"""
        <div class="callout">
          {len(runs)} runs · {sum(r.get('n_analyzed',0) for r in runs):,} calls &nbsp;|&nbsp;
          Latest vs prior —
          FCR {_d(latest.get('fcr_rate_pct',0)-prev.get('fcr_rate_pct',0), True)} pp &nbsp;·&nbsp;
          AHT {_d(latest.get('aht_minutes',0)-prev.get('aht_minutes',0), False)} min &nbsp;·&nbsp;
          QA {_d(latest.get('qa_avg_score',0)-prev.get('qa_avg_score',0), True)} pts &nbsp;·&nbsp;
          Source: <strong>{html.escape(latest.get('insights_source','—'))}</strong>
        </div>
        """, unsafe_allow_html=True)

    # ── Footer ────────────────────────────────────────────────────────
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='footer'>"
        f"<span>Telecom Call Intelligence &nbsp;·&nbsp; {n_calls:,} calls analysed "
        f"&nbsp;·&nbsp; {html.escape(meta.get('dataset',''))}</span>"
        f"<span>{provider} &nbsp;·&nbsp; {model} &nbsp;·&nbsp; {run_date}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
