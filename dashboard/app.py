"""
dashboard/app.py — Telecom Call Intelligence
Business case for autonomous AI resolution of customer contacts.
Narrative: bold finding → evidence → opportunity → roadmap.

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
    background: #F1F5F9;
    color: #0F172A;
  }
  .main { background: #F1F5F9; }
  .block-container { padding-top: 0 !important; padding-bottom: 2rem; }

  /* ── Hero ── */
  .hero {
    background: linear-gradient(135deg, #0F172A 0%, #1E3A5F 60%, #1D4ED8 100%);
    padding: 48px 52px 44px;
    margin: -1rem -1rem 0;
    border-radius: 0 0 24px 24px;
  }
  .hero-eyebrow {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.2em;
    text-transform: uppercase; color: #60A5FA; margin-bottom: 16px;
  }
  .hero-headline {
    font-size: 2.6rem; font-weight: 900; color: #FFFFFF;
    letter-spacing: -0.04em; line-height: 1.1; margin: 0 0 8px;
  }
  .hero-headline span { color: #34D399; }
  .hero-subline {
    font-size: 1rem; color: #93C5FD; font-weight: 400; margin: 0 0 32px;
  }
  .hero-meta {
    font-size: 0.72rem; color: #475569; margin-top: 12px; line-height: 1.8;
  }
  /* Hero cost panels */
  .hpanel {
    border-radius: 10px; padding: 18px 20px 16px;
  }
  .hpanel-incurred { background: rgba(0,0,0,0.28); }
  .hpanel-opp      { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); }
  .hpanel-title {
    font-size: 0.85rem; font-weight: 800; letter-spacing: 0.06em;
    text-transform: uppercase; margin-bottom: 14px; color: #FFFFFF;
  }
  .hbucket {
    display: flex; justify-content: space-between; align-items: baseline;
    gap: 12px; padding: 7px 0; border-bottom: 1px solid rgba(255,255,255,0.07);
  }
  .hbucket:last-of-type { border-bottom: none; }
  .hbucket-label { font-size: 0.78rem; color: #CBD5E1; font-weight: 500; flex: 1; }
  .hbucket-pct   { font-size: 0.75rem; color: #64748B; }
  .hbucket-cost  { font-size: 1.05rem; font-weight: 800; color: #F87171; white-space: nowrap; }
  .htotal {
    display: flex; justify-content: space-between; align-items: baseline;
    padding-top: 10px; margin-top: 4px; border-top: 1px solid rgba(255,255,255,0.15);
  }
  .htotal-label { font-size: 0.72rem; color: #94A3B8; font-weight: 600; letter-spacing: 0.05em; }
  .htotal-val   { font-size: 1.3rem; font-weight: 900; color: #FFFFFF; }
  .hopp-row {
    display: flex; justify-content: space-between; align-items: baseline;
    gap: 12px; padding: 7px 0; border-bottom: 1px solid rgba(52,211,153,0.12);
  }
  .hopp-row:last-of-type { border-bottom: none; }
  .hopp-label { font-size: 0.78rem; color: #CBD5E1; font-weight: 500; flex: 1; }
  .hopp-val   { font-size: 1.2rem; font-weight: 900; color: #FFFFFF; white-space: nowrap; }
  .hero-badge {
    display:inline-block; padding:3px 12px; border-radius:20px; font-size:0.65rem;
    font-weight:700; letter-spacing:0.1em; text-transform:uppercase;
    margin-bottom: 12px;
  }
  .badge-live { background:rgba(16,185,129,.2); border:1px solid rgba(16,185,129,.4); color:#34D399; }
  .badge-demo { background:rgba(99,102,241,.2); border:1px solid rgba(99,102,241,.4); color:#A5B4FC; }

  /* ── Section label ── */
  .section-label {
    font-size: 0.62rem; font-weight: 800; letter-spacing: 0.2em; text-transform: uppercase;
    color: #94A3B8; margin: 36px 0 18px; padding-bottom: 10px;
    border-bottom: 1px solid #E2E8F0;
  }

  /* ── Stat card ── */
  .scard {
    background: #FFFFFF; border-radius: 14px;
    padding: 24px 22px 20px;
    box-shadow: 0 1px 4px rgba(15,23,42,.08);
  }
  .scard-val {
    font-size: 2.6rem; font-weight: 900; letter-spacing: -0.04em; line-height: 1;
  }
  .scard-label {
    font-size: 0.65rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: #64748B; margin-bottom: 8px;
  }
  .scard-note { font-size: 0.75rem; color: #94A3B8; margin-top: 6px; }

  /* ── Insight panel ── */
  .insight {
    background: #FFFFFF; border-radius: 14px;
    padding: 28px 26px; box-shadow: 0 1px 4px rgba(15,23,42,.08);
    height: 100%;
  }
  .insight-title {
    font-size: 0.65rem; font-weight: 800; letter-spacing: 0.15em;
    text-transform: uppercase; color: #94A3B8; margin-bottom: 16px;
  }
  .insight-num {
    font-size: 3.2rem; font-weight: 900; letter-spacing: -0.05em; line-height: 1;
  }
  .insight-desc {
    font-size: 0.84rem; color: #475569; margin-top: 8px; line-height: 1.6;
  }

  /* ── Segment block ── */
  .seg {
    background: #FFFFFF; border-radius: 14px; padding: 28px 22px 24px;
    box-shadow: 0 1px 4px rgba(15,23,42,.08); text-align: center;
    height: 100%;
  }
  .seg-badge {
    display: inline-block; padding: 3px 12px; border-radius: 20px;
    font-size: 0.62rem; font-weight: 700; letter-spacing: 0.12em;
    text-transform: uppercase; margin-bottom: 14px;
  }
  .seg-pct   { font-size: 4rem; font-weight: 900; letter-spacing: -0.05em; line-height: 1; }
  .seg-calls { font-size: 0.82rem; color: #94A3B8; margin: 4px 0 14px; }
  .seg-money { font-size: 1.2rem; font-weight: 700; }
  .seg-desc  { font-size: 0.78rem; color: #64748B; margin-top: 10px; line-height: 1.6; }

  /* ── Roadmap table ── */
  .road-table {
    width: 100%; border-collapse: collapse; font-size: 0.87rem;
    background: #FFFFFF; border-radius: 14px; overflow: hidden;
    box-shadow: 0 1px 4px rgba(15,23,42,.08);
  }
  .road-table thead tr { background: #0F172A; color: #E2E8F0; }
  .road-table thead th {
    padding: 13px 18px; text-align: left; font-size: 0.62rem;
    font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase;
  }
  .road-table tbody tr { border-bottom: 1px solid #F1F5F9; }
  .road-table tbody tr:last-child { border-bottom: none; }
  .road-table tbody td { padding: 13px 18px; color: #1E293B; vertical-align: middle; }
  .road-table tbody tr:hover { background: #F8FAFC; }


  /* ── Action table ── */
  .action-table {
    width: 100%; border-collapse: collapse; font-size: 0.87rem;
    background: #FFFFFF; border-radius: 14px; overflow: hidden;
    box-shadow: 0 1px 4px rgba(15,23,42,.08);
  }
  .action-table thead tr { background: #0F172A; color: #E2E8F0; }
  .action-table thead th {
    padding: 13px 18px; font-size: 0.62rem; font-weight: 700;
    letter-spacing: 0.12em; text-transform: uppercase; text-align: left;
  }
  .action-table tbody tr { border-bottom: 1px solid #F1F5F9; }
  .action-table tbody td { padding: 14px 18px; color: #1E293B; vertical-align: middle; line-height: 1.5; }

  /* ── Misc ── */
  .dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:7px; }
  .dot-red   { background:#DC2626; box-shadow:0 0 6px rgba(220,38,38,.5); }
  .dot-amber { background:#D97706; box-shadow:0 0 6px rgba(217,119,6,.5); }
  .dot-green { background:#059669; box-shadow:0 0 6px rgba(5,150,105,.5); }

  .pill {
    display:inline-flex; align-items:center; padding:3px 10px;
    border-radius:20px; font-size:0.7rem; font-weight:700; letter-spacing:.06em; white-space:nowrap;
  }
  .pill-crit  { background:#FEF2F2; color:#991B1B; border:1px solid #FECACA; }
  .pill-high  { background:#FFFBEB; color:#92400E; border:1px solid #FDE68A; }
  .pill-quick { background:#ECFDF5; color:#065F46; border:1px solid #6EE7B7; }

  .callout {
    background: #EFF6FF; border-left: 4px solid #2563EB; border-radius: 10px;
    padding: 14px 18px; font-size: 0.86rem; color: #1E3A8A; line-height: 1.65;
  }
  .callout.green { background: #ECFDF5; border-left-color: #059669; color: #064E3B; }
  .callout.amber { background: #FFFBEB; border-left-color: #D97706; color: #78350F; }
  .callout.teal  { background: #F0FDFA; border-left-color: #0D9488; color: #134E4A; }

  .footer {
    font-size: 0.68rem; color: #94A3B8;
    display: flex; justify-content: space-between; flex-wrap: wrap; gap: 4px;
    padding-top: 8px;
  }

  #MainMenu, footer, header { visibility: hidden; }
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

# Phase display config: color, type label
PHASE_META = {
    "Welcome & Auth": ("#94A3B8", "Overhead"),
    "Discovery":      ("#F59E0B", "Customer explains issue"),
    "Diagnosis":      ("#F97316", "Agent investigates"),
    "Resolution":     ("#10B981", "Value delivery"),
    "Hold":           ("#EF4444", "Dead time"),
    "Upsell":         ("#3B82F6", "Revenue"),
    "Closing":        ("#CBD5E1", "Overhead"),
}
PHASE_ORDER = ["Welcome & Auth", "Discovery", "Diagnosis", "Resolution", "Hold", "Upsell", "Closing"]

# Issue category → automation tier + color
ISSUE_TIER = {
    "billing":     ("Agentic AI",  PURPLE),
    "technical":   ("Proactive",   TEAL),
    "plan":        ("Agentic AI",  PURPLE),
    "account":     ("Agentic AI",  PURPLE),
    "device":      ("Agentic AI",  BLUE),
    "information": ("Self-Serve",  SLATE),
    "information_only": ("Self-Serve", SLATE),
}

# Intents mapped to issue categories
_INTENTS = {
    "billing":     [("Bill explanation & itemised charges", "Agentic AI", "Low",    0.10),
                    ("Payment / direct debit setup",        "Agentic AI", "Low",    0.06),
                    ("Billing dispute investigation",       "Human Agent","—",      0.22)],
    "technical":   [("Network / outage status check",      "Proactive",  "Medium", 0.12),
                    ("Service activation / provisioning",  "Agentic AI", "Low",    0.08),
                    ("Complex fault diagnosis",            "Human Agent","—",      0.25)],
    "plan":        [("Plan details & inclusions enquiry",  "Agentic AI", "Low",    0.08),
                    ("Data balance & usage check",         "Agentic AI", "Low",    0.07),
                    ("Plan upgrade / change",              "Human Agent","—",      0.05)],
    "account":     [("Address / contact detail update",    "Agentic AI", "Low",    0.05),
                    ("Account security & identity",        "Human Agent","—",      0.04)],
    "information": [("General service enquiries",          "Agentic AI", "Low",    0.02)],
    "information_only": [("General service enquiries",     "Agentic AI", "Low",    0.02)],
    "device":      [("Order & delivery status",            "Agentic AI", "Low",    0.02),
                    ("Device hardware fault",              "Human Agent","—",      0.02)],
}

_TIER_COLOR = {
    "Proactive":   (TEAL,   "#CCFBF1", "#0F766E"),
    "Agentic AI":  (PURPLE, "#EDE9FE", "#6D28D9"),
    "Human Agent": (BLUE,   "#DBEAFE", "#1D4ED8"),
    "Self-Serve":  (SLATE,  "#F1F5F9", "#334155"),
}


# Demo data used when no pipeline output exists
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
        "proactive_outreach_pct": 12.0, "all_issues_resolved_pct": 71.0,
        "escalation_rate_pct": 14.0, "sentiment_improved_pct": 61.0,
        "agent_tool_struggle_pct": 23.0,
    },
    "phase_avg_seconds": {
        "Welcome & Auth": 46, "Discovery": 108, "Diagnosis": 152,
        "Resolution": 128, "Hold": 87, "Upsell": 44, "Closing": 54,
    },
    "distributions": {
        "issue_category": {
            "billing": 38, "technical": 31, "plan": 16,
            "account": 9, "device": 4, "information": 2,
        },
        "agent_skill":    {"proficient": "44.0", "adequate": "38.0", "needs_improvement": "18.0"},
        "agent_disproportionate_phase": {
            "none": "48.0", "diagnosis": "26.0", "discovery": "14.0", "resolution": "12.0",
        },
    },
    "cost_levers": {
        "cost_per_call_usd": 6.0, "monthly_volume_estimate": 100000,
        "baseline_monthly_cost_usd": 600000,
        "self_serve_savings_usd": 188700, "agentic_ai_savings_usd": 121800,
        "proactive_care_savings_usd": 52200, "total_savings_opportunity_usd": 362700,
        "savings_pct_of_baseline": 60.5,
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


# Issue → cost bucket mapping
_BUCKET = {
    "billing":          "serve",
    "technical":        "serve",
    "account":          "serve",
    "information":      "serve",
    "information_only": "serve",
    "device":           "serve",
    "plan":             "sell",
}


def _cost_buckets(issue_cats: dict, kpis: dict, baseline: float) -> dict:
    total = sum(issue_cats.values()) or 1
    serve = sum(v for k, v in issue_cats.items() if _BUCKET.get(k, "serve") == "serve")
    sell  = sum(v for k, v in issue_cats.items() if _BUCKET.get(k, "serve") == "sell")
    retain_pct = float(kpis.get("escalation_rate_pct", 0))

    # Retain = escalated/at-risk contacts; Serve+Sell split the remainder
    non_retain = max(100.0 - retain_pct, 0.0)
    denom = serve + sell or 1
    serve_pct = serve / denom * non_retain
    sell_pct  = sell  / denom * non_retain

    return {
        "serve":  {"pct": serve_pct,  "cost": baseline * serve_pct  / 100},
        "sell":   {"pct": sell_pct,   "cost": baseline * sell_pct   / 100},
        "retain": {"pct": retain_pct, "cost": baseline * retain_pct / 100},
    }


def _cost_levers(kpis: dict) -> dict:
    cpp, vol = 6.0, 100_000
    base = cpp * vol
    ss   = base * kpis.get("self_serve_deflection_pct", 0) / 100
    ai   = base * kpis.get("agentic_ai_resolvable_pct",  0) / 100
    pro  = base * kpis.get("proactive_outreach_pct",     0) / 100
    tot  = ss + ai + pro
    return {
        "cost_per_call_usd": cpp, "monthly_volume_estimate": vol,
        "baseline_monthly_cost_usd": base,
        "self_serve_savings_usd": ss, "agentic_ai_savings_usd": ai,
        "proactive_care_savings_usd": pro, "total_savings_opportunity_usd": tot,
        "savings_pct_of_baseline": tot / base * 100 if base else 0,
    }


# ── Charts ────────────────────────────────────────────────────────────

def chart_phases(phase_seconds: dict) -> go.Figure:
    total  = sum(phase_seconds.values()) or 1
    phases = [p for p in PHASE_ORDER if p in phase_seconds]
    secs   = [phase_seconds[p] for p in phases]
    pcts   = [s / total * 100 for s in secs]
    colors = [PHASE_META.get(p, ("#94A3B8", ""))[0] for p in phases]
    types  = [PHASE_META.get(p, ("", "Other"))[1] for p in phases]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=phases, y=secs,
        marker=dict(color=colors, line_width=0),
        text=[f"{s:.0f}s<br>{p:.0f}%" for s, p in zip(secs, pcts)],
        textposition="outside",
        textfont=dict(color="#334155", size=11, family="Inter"),
        customdata=[[t, f"{p:.1f}"] for t, p in zip(types, pcts)],
        hovertemplate=(
            "<b>%{x}</b><br>%{y:.0f}s · %{customdata[1]}% of call<br>"
            "<i>%{customdata[0]}</i><extra></extra>"
        ),
    ))
    fig.update_layout(
        **PLOTLY,
        height=320,
        xaxis=dict(tickfont=dict(size=11, color="#334155")),
        yaxis=dict(title="Average seconds", gridcolor="#F1F5F9", zeroline=False),
        margin=dict(l=48, r=16, t=36, b=16),
    )
    return fig


def chart_issue_mix(issue_dist: dict, n_calls: int) -> go.Figure:
    cats   = sorted(issue_dist.items(), key=lambda x: -x[1])
    total  = sum(v for _, v in cats) or 1
    labels = [c.title() for c, _ in cats]
    values = [v for _, v in cats]
    colors = [ISSUE_TIER.get(c, ("", SLATE))[1] for c, _ in cats]
    tiers  = [ISSUE_TIER.get(c, ("Other", ""))[0] for c, _ in cats]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=values, orientation="h",
        marker=dict(color=colors, line_width=0),
        text=[f"  {v}  ({v/total*100:.0f}%)" for v in values],
        textposition="inside", insidetextanchor="start",
        textfont=dict(color="white", size=11, family="Inter"),
        customdata=tiers,
        hovertemplate="<b>%{y}</b><br>%{x} calls · <i>%{customdata}</i><extra></extra>",
    ))
    fig.update_layout(
        **PLOTLY,
        height=280,
        xaxis=dict(title=f"Calls (n={n_calls})", gridcolor="#F1F5F9", zeroline=False),
        yaxis=dict(),
        margin=dict(l=10, r=70, t=12, b=44),
    )
    return fig


def chart_segment_bar(segments: list[tuple[str, float, str]]) -> go.Figure:
    """Stacked horizontal bar for resolution segments."""
    fig = go.Figure()
    for name, pct, color in segments:
        lbl = f"  {pct:.0f}%" if pct >= 5 else ""
        fig.add_trace(go.Bar(
            name=name, x=[pct], y=[""], orientation="h",
            marker_color=color, marker_line_width=0,
            text=[lbl], textposition="inside", insidetextanchor="start",
            textfont=dict(color="white", size=13, family="Inter"),
            hovertemplate=f"<b>{name}</b><br>{pct:.1f}%<extra></extra>",
        ))
    fig.update_layout(
        **PLOTLY,
        barmode="stack", height=80,
        xaxis=dict(range=[0, 100], ticksuffix="%", gridcolor="#F1F5F9",
                   zeroline=False, tickfont=dict(size=11, color="#94A3B8")),
        yaxis=dict(showticklabels=False),
        margin=dict(l=8, r=8, t=8, b=24),
        showlegend=True,
        legend=dict(orientation="h", y=-1.0, x=0, yanchor="top",
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


def _seg(badge: str, badge_bg: str, badge_fg: str,
         pct: float, calls_label: str,
         money: str, money_color: str, desc: str) -> str:
    return (
        f'<div class="seg">'
        f'<span class="seg-badge" style="background:{badge_bg};color:{badge_fg};">{badge}</span><br>'
        f'<div class="seg-pct" style="color:{badge_fg};">{pct:.0f}%</div>'
        f'<div class="seg-calls">{calls_label}</div>'
        f'<div class="seg-money" style="color:{money_color};">{money}</div>'
        f'<div class="seg-desc">{desc}</div>'
        f'</div>'
    )


def _pill(priority: str) -> str:
    m = {"Critical": ("dot-red",   "pill-crit",  "CRITICAL"),
         "High":     ("dot-amber", "pill-high",  "HIGH"),
         "Quick Win":("dot-green", "pill-quick", "QUICK WIN")}
    dc, pc, lbl = m.get(priority, ("dot-green", "pill-quick", priority.upper()))
    return f'<span class="pill {pc}"><span class="dot {dc}"></span>{lbl}</span>'


def _build_roadmap(issue_categories: dict, cost_per_call: float, monthly_vol: int) -> list[dict]:
    total_calls = sum(issue_categories.values()) or 1
    rows = []
    for cat, cat_count in issue_categories.items():
        for intent, tier, effort, share in _INTENTS.get(cat, []):
            if tier == "Human Agent":
                continue
            est_calls  = round(monthly_vol * (cat_count / total_calls) * share)
            est_saving = est_calls * cost_per_call
            rows.append({
                "intent": intent, "tier": tier, "effort": effort,
                "monthly_calls": est_calls, "monthly_saving": est_saving,
            })
    rows.sort(key=lambda r: -r["monthly_saving"])
    return rows


# ── Main ──────────────────────────────────────────────────────────────

def main():
    data, is_demo = load_summary()
    kpis   = data["kpis"]
    cl     = data["cost_levers"]
    meta   = data["meta"]
    dist   = data["distributions"]
    phases = data.get("phase_avg_seconds", {})

    n_calls  = meta["total_calls_analyzed"]
    run_date = html.escape(meta.get("analysis_timestamp", "")[:10])
    model    = html.escape(meta.get("model", ""))
    provider = html.escape(meta.get("inference_provider", ""))
    dataset  = html.escape(meta.get("dataset", ""))

    # Segment arithmetic
    proactive_pct = float(kpis.get("proactive_outreach_pct",    0))
    selfserve_pct = float(kpis.get("self_serve_deflection_pct", 0))
    agentic_pct   = float(kpis.get("agentic_ai_resolvable_pct", 0))
    digital_pct   = min(selfserve_pct + agentic_pct, max(100.0 - proactive_pct, 0.0))
    human_pct     = max(100.0 - proactive_pct - digital_pct, 0.0)
    total_auto    = proactive_pct + digital_pct

    cpp      = cl["cost_per_call_usd"]
    vol      = cl["monthly_volume_estimate"]
    base     = cl["baseline_monthly_cost_usd"]
    opp      = cl["total_savings_opportunity_usd"]
    annual   = opp * 12

    # Phase insight stats
    total_secs = sum(phases.values()) or 1
    disc_secs  = phases.get("Discovery", 0)
    diag_secs  = phases.get("Diagnosis", 0)
    hold_secs  = phases.get("Hold", 0)
    ai_phase_pct = (disc_secs + diag_secs + hold_secs) / total_secs * 100
    aht_min  = kpis.get("avg_handle_time_minutes", round(total_secs / 60, 1))

    # Issue category data
    ic = dist.get("issue_category", {})
    # Deduplicate categories that appear in both int and pct forms — keep int version
    ic_clean: dict[str, int] = {}
    for k, v in ic.items():
        try:
            vi = int(float(v))
        except (ValueError, TypeError):
            continue
        if vi > 0:
            # prefer earlier entry if duplicate base key
            base_k = k.replace("_only", "").replace("_pct", "")
            if base_k not in ic_clean:
                ic_clean[base_k] = vi
    if not ic_clean:
        ic_clean = ic  # fallback

    # Hero numbers
    auto_per_100 = round(total_auto)
    badge     = "DEMO DATA" if is_demo else "LIVE DATA"
    badge_cls = "badge-demo" if is_demo else "badge-live"

    # Cost buckets
    buckets = _cost_buckets(ic_clean, kpis, base)

    # ── HERO ─────────────────────────────────────────────────────────
    # Hero — headline only
    hero_html = (
        '<div class="hero">'
        '<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;">'
        '<div>'
        '<div class="hero-eyebrow">Telecom Call Intelligence</div>'
        f'<div class="hero-headline"><span>{auto_per_100} out of every 100</span> customer contacts<br>don\'t need a human agent.</div>'
        f'<div class="hero-subline">Autonomous AI can prevent or fully resolve them — based on analysis of <strong style="color:#E2E8F0;">{n_calls:,} real call transcripts.</strong></div>'
        '</div>'
        '<div style="text-align:right;">'
        f'<span class="hero-badge {badge_cls}">{badge}</span>'
        f'<div class="hero-meta">{n_calls:,} calls &nbsp;·&nbsp; {run_date}<br>{provider} &nbsp;·&nbsp; {model}</div>'
        '</div>'
        '</div>'
        '</div>'
    )
    st.markdown(hero_html, unsafe_allow_html=True)

    # Cost panels — outside hero, white background, side by side
    panels_html = (
        '<div style="display:flex;gap:20px;margin-top:20px;">'

        '<div style="flex:1;background:#FFFFFF;border-radius:14px;padding:24px 26px;box-shadow:0 1px 4px rgba(15,23,42,.08);">'
        f'<div style="font-size:0.95rem;font-weight:800;color:#DC2626;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">Insights from {n_calls:,} Calls Analysed</div>'
        f'<div style="font-size:0.75rem;color:#64748B;font-style:italic;margin-bottom:14px;">Cost breakdown forecast at {vol:,} calls/month · ${cpp:.2f}/call unit cost · extrapolated from {n_calls}-call sample</div>'
        '<div style="display:flex;justify-content:space-between;align-items:baseline;padding:9px 0;border-bottom:1px solid #F1F5F9;">'
        '<span style="font-size:0.88rem;color:#0F172A;font-weight:600;">Cost to Serve</span>'
        f'<span style="font-size:0.8rem;color:#64748B;font-weight:600;">{buckets["serve"]["pct"]:.0f}% of calls</span>'
        f'<span style="font-size:1.1rem;font-weight:800;color:#0F172A;">${buckets["serve"]["cost"]/1000:.0f}K/mo</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:baseline;padding:9px 0;border-bottom:1px solid #F1F5F9;">'
        '<span style="font-size:0.88rem;color:#0F172A;font-weight:600;">Cost to Sell</span>'
        f'<span style="font-size:0.8rem;color:#64748B;font-weight:600;">{buckets["sell"]["pct"]:.0f}% of calls</span>'
        f'<span style="font-size:1.1rem;font-weight:800;color:#0F172A;">${buckets["sell"]["cost"]/1000:.0f}K/mo</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:baseline;padding:9px 0;border-bottom:1px solid #F1F5F9;">'
        '<span style="font-size:0.88rem;color:#0F172A;font-weight:600;">Cost to Retain</span>'
        f'<span style="font-size:0.8rem;color:#64748B;font-weight:600;">{buckets["retain"]["pct"]:.0f}% of calls</span>'
        f'<span style="font-size:1.1rem;font-weight:800;color:#0F172A;">${buckets["retain"]["cost"]/1000:.0f}K/mo</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:baseline;padding-top:12px;margin-top:4px;border-top:2px solid #0F172A;">'
        '<span style="font-size:0.75rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:#64748B;">Total Monthly Cost</span>'
        f'<span style="font-size:1.6rem;font-weight:800;color:#DC2626;">${base/1000:.0f}K</span>'
        '</div>'
        '</div>'

        '<div style="flex:1;background:#FFFFFF;border-radius:14px;padding:24px 26px;box-shadow:0 1px 4px rgba(15,23,42,.08);">'
        '<div style="font-size:0.95rem;font-weight:800;color:#DC2626;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">AI Recovery Opportunity</div>'
        f'<div style="font-size:0.75rem;color:#64748B;font-style:italic;margin-bottom:14px;">Savings vs ${base/1000:.0f}K/month baseline · forecast at {vol:,} calls/month · from {n_calls}-call analysis</div>'
        '<div style="display:flex;justify-content:space-between;align-items:baseline;padding:9px 0;border-bottom:1px solid #F1F5F9;">'
        '<span style="font-size:0.88rem;color:#0F172A;font-weight:600;">Contacts resolvable without a human</span>'
        f'<span style="font-size:1.1rem;font-weight:800;color:#0F172A;">{total_auto:.0f}% of calls</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:baseline;padding:9px 0;border-bottom:1px solid #F1F5F9;">'
        f'<span style="font-size:0.88rem;color:#0F172A;font-weight:600;">Monthly saving at {vol:,} volume</span>'
        f'<span style="font-size:1.1rem;font-weight:800;color:#0F172A;">${opp/1000:.0f}K of ${base/1000:.0f}K</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:baseline;padding:9px 0;">'
        '<span style="font-size:0.88rem;color:#0F172A;font-weight:600;">Annual cost recovery</span>'
        f'<span style="font-size:1.1rem;font-weight:800;color:#0F172A;">${annual/1e6:.1f}M / year</span>'
        '</div>'
        '</div>'

        '</div>'
    )
    st.markdown(panels_html, unsafe_allow_html=True)

    if is_demo:
        st.markdown("""<div class="callout" style="margin-top:14px;">
          <strong>Demo mode.</strong> Run <code>python run_pipeline.py</code> to replace with live results.
        </div>""", unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════
    # 1 — THE EVIDENCE: WHY CUSTOMERS CALL AND WHERE TIME GOES
    # ═══════════════════════════════════════════════════════════════
    _sec("1 — The Evidence: What the Transcripts Reveal")

    col_issue, col_phase = st.columns([4, 6])

    with col_issue:
        st.markdown(
            "<div style='font-size:0.8rem;font-weight:700;color:#334155;margin-bottom:10px;'>"
            "What customers are calling about</div>",
            unsafe_allow_html=True,
        )
        # Tier legend
        seen, chips = set(), ""
        for cat in ic_clean:
            tier, color = ISSUE_TIER.get(cat, ("Other", SLATE))
            if tier not in seen:
                seen.add(tier)
                chips += (
                    f'<span style="display:inline-block;padding:2px 9px;border-radius:12px;'
                    f'font-size:0.68rem;font-weight:700;background:{color}22;color:{color};'
                    f'border:1px solid {color}44;margin-right:5px;margin-bottom:4px;">'
                    f'{tier}</span>'
                )
        st.markdown(f"<div style='margin-bottom:8px;'>{chips}</div>", unsafe_allow_html=True)
        if ic_clean:
            st.plotly_chart(chart_issue_mix(ic_clean, n_calls), use_container_width=True)

    with col_phase:
        st.markdown(
            "<div style='font-size:0.8rem;font-weight:700;color:#334155;margin-bottom:10px;'>"
            "Where agent time goes inside every call</div>",
            unsafe_allow_html=True,
        )
        # Phase legend
        seen, chips = set(), ""
        for phase in phases:
            color, ptype = PHASE_META.get(phase, ("#94A3B8", "Overhead"))
            if ptype not in seen:
                seen.add(ptype)
                chips += (
                    f'<span style="display:inline-block;padding:2px 9px;border-radius:12px;'
                    f'font-size:0.68rem;font-weight:700;background:{color}22;color:{color};'
                    f'border:1px solid {color}44;margin-right:5px;margin-bottom:4px;">'
                    f'{ptype}</span>'
                )
        st.markdown(f"<div style='margin-bottom:8px;'>{chips}</div>", unsafe_allow_html=True)
        if phases:
            st.plotly_chart(chart_phases(phases), use_container_width=True)

    # Evidence callout
    disc_pct_str = f"{disc_secs/total_secs*100:.0f}%"
    diag_pct_str = f"{diag_secs/total_secs*100:.0f}%"
    st.markdown(f"""
    <div class="callout amber">
      <strong>Discovery and Diagnosis account for {(disc_secs+diag_secs)/total_secs*100:.0f}%
      of every call</strong>
      ({disc_pct_str} customers explaining their issue + {diag_pct_str} agents investigating it)
      on a {aht_min:.1f}-minute average call.
      AI agents pre-empt Discovery with proactive outreach; grounded knowledge bases
      cut Diagnosis time. Together they compress the majority of call handle time.
    </div>
    """, unsafe_allow_html=True)

    # Phase imbalance signal
    disp     = dist.get("agent_disproportionate_phase", {})
    diag_ovr = float(disp.get("diagnosis", 0))
    disc_ovr = float(disp.get("discovery", 0))
    if diag_ovr + disc_ovr > 15:
        st.markdown(f"""
        <div class="callout" style="margin-top:10px;">
          <strong>Phase overrun detected:</strong> &nbsp;
          {diag_ovr:.0f}% of calls had agents over-spending in Diagnosis and
          {disc_ovr:.0f}% in Discovery — knowledge gaps and tool friction are inflating AHT.
          These are the highest-ROI targets for AI-assisted agent tooling.
        </div>
        """, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════
    # 2 — RESOLUTION OPPORTUNITY: WHAT THE DATA SAYS
    # ═══════════════════════════════════════════════════════════════
    _sec("2 — Resolution Opportunity: Insights from the Calls")

    st.markdown(
        f"<div style='font-size:0.93rem;color:#334155;line-height:1.7;margin-bottom:20px;'>"
        f"From <strong>{n_calls:,} calls analysed</strong>, every contact was classified by "
        f"whether a human agent was genuinely required — or whether autonomous AI could have "
        f"resolved it. <strong>{total_auto:.0f}%</strong> did not require a human.</div>",
        unsafe_allow_html=True,
    )

    # Build segment list — only show PREVENT if > 0
    segments_display = []
    if proactive_pct > 0:
        segments_display.append(("prevent", proactive_pct))
    segments_display.append(("automate", digital_pct))
    segments_display.append(("human",    human_pct))

    ncols = len(segments_display)
    cols  = st.columns(ncols)

    seg_configs = {
        "prevent": (
            "PREVENT",        "#CCFBF1", "#0F766E", TEAL,
            f"${cl['proactive_care_savings_usd']/1000:.0f}K / month",
            "Customer shouldn't have needed to call. Detect the trigger event first — "
            "outage, bill spike, data exhaustion — and push a proactive alert. "
            "Eliminates the contact before it starts.",
        ),
        "automate": (
            "AUTOMATE",       "#EDE9FE", "#6D28D9", PURPLE,
            f"${(cl['self_serve_savings_usd']+cl['agentic_ai_savings_usd'])/1000:.0f}K / month",
            f"Deterministic issue — AI agent resolves end-to-end: bill explanation, "
            f"plan enquiry, order status, payments, balance check. "
            f"({selfserve_pct:.0f}% self-serve · {agentic_pct:.0f}% full AI agent)",
        ),
        "human": (
            "HUMAN REQUIRED", "#DBEAFE", "#1D4ED8", BLUE,
            f"${(base - opp)/1000:.0f}K / month — irreducible",
            "Complex faults, billing disputes, complaints, retention — "
            "judgment-intensive situations that need an empathetic skilled agent. "
            "Concentrate your human investment here.",
        ),
    }

    for col, (key, pct) in zip(cols, segments_display):
        badge, bbg, bfg, money_clr, money, desc = seg_configs[key]
        n_seg = round(n_calls * pct / 100)
        with col:
            st.markdown(
                _seg(badge, bbg, bfg, pct,
                     f"{n_seg} of {n_calls} calls analysed",
                     money, money_clr, desc),
                unsafe_allow_html=True,
            )

    # Proactive potential note when proactive = 0
    if proactive_pct == 0 and ic_clean:
        tech_pct = ic_clean.get("technical", 0) / sum(ic_clean.values()) * 100
        if tech_pct > 0:
            st.markdown(f"""
            <div class="callout teal" style="margin-top:14px;">
              <strong>Proactive Care opportunity not yet activated.</strong> &nbsp;
              {tech_pct:.0f}% of analysed contacts are technical issues —
              network faults, outages, and service degradation that could be detected
              and communicated proactively before the customer calls.
              Implementing event-driven alerts could move an estimated 15–25% of contacts
              out of the care queue entirely.
            </div>
            """, unsafe_allow_html=True)

    # Stacked bar
    seg_bar_data = []
    if proactive_pct > 0:
        seg_bar_data.append(("Proactive Care", proactive_pct, TEAL))
    seg_bar_data.append(("Agentic AI / Self-Serve", digital_pct, PURPLE))
    seg_bar_data.append(("Human Agent Required", human_pct, BLUE))

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    st.plotly_chart(chart_segment_bar(seg_bar_data), use_container_width=True)

    st.markdown(f"""
    <div class="callout green" style="margin-top:6px;">
      <strong>Business case from {n_calls:,} calls:</strong> &nbsp;
      {total_auto:.0f}% of your contact volume — {round(vol * total_auto / 100):,} calls/month
      at scale — is addressable through autonomous AI.
      At ${cpp:.2f} per call that is
      <strong>${opp/1000:.0f}K/month · ${annual/1e6:.1f}M/year</strong>
      in recoverable cost, before any improvement in customer experience is counted.
    </div>
    """, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════
    # 3 — WHICH AGENTS TO BUILD
    # ═══════════════════════════════════════════════════════════════
    _sec("3 — Which AI Agents to Build — Ranked by Monthly Saving")

    rows = _build_roadmap(ic_clean, cpp, vol)

    if rows:
        total_rm_saving = sum(r["monthly_saving"] for r in rows)
        road_html = ""
        for r in rows:
            _, bg, fg = _TIER_COLOR.get(r["tier"], (SLATE, "#F1F5F9", "#334155"))
            tier_badge = (
                f'<span style="display:inline-block;padding:2px 9px;border-radius:12px;'
                f'font-size:0.7rem;font-weight:700;background:{bg};color:{fg};">'
                f'{r["tier"]}</span>'
            )
            effort_clr = "#059669" if r["effort"] == "Low" else "#D97706"
            road_html += (
                f"<tr>"
                f"<td style='font-weight:600;color:#0F172A;'>{html.escape(r['intent'])}</td>"
                f"<td style='text-align:right;color:#64748B;'>{r['monthly_calls']:,}</td>"
                f"<td>{tier_badge}</td>"
                f"<td style='text-align:right;font-weight:700;color:#059669;'>"
                f"${r['monthly_saving']/1000:.0f}K</td>"
                f"<td style='text-align:center;font-weight:600;color:{effort_clr};'>{r['effort']}</td>"
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
          <tbody>{road_html}</tbody>
        </table>
        """, unsafe_allow_html=True)
        st.markdown(
            f"<p style='font-size:0.7rem;color:#94A3B8;margin-top:8px;'>"
            f"Volumes estimated from {n_calls}-call sample extrapolated to {vol:,}/month. "
            f"Total addressable: <strong>${total_rm_saving/1000:.0f}K/month</strong>. "
            f"Validate against your live IVR taxonomy before build.</p>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="callout">Run the pipeline to populate the agent roadmap.</div>',
                    unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════
    # 4 — ACTUAL PERFORMANCE
    # ═══════════════════════════════════════════════════════════════
    _sec("4 — Actual Performance")

    perf_metrics = [
        ("First Call Resolution",  f"{kpis.get('fcr_rate_pct', 0):.0f}%",       GREEN,  "Calls resolved without a repeat contact"),
        ("Avg Handle Time",        f"{kpis.get('avg_handle_time_minutes', 0):.1f} min", AMBER, "Average duration per call"),
        ("Escalation Rate",        f"{kpis.get('escalation_rate_pct', 0):.0f}%", RED,    "Calls requiring senior / specialist escalation"),
        ("Issues Resolved",        f"{kpis.get('all_issues_resolved_pct', 0):.0f}%", GREEN, "Calls where all customer issues were resolved"),
        ("Sentiment Improved",     f"{kpis.get('sentiment_improved_pct', 0):.0f}%", GREEN, "Calls where customer sentiment improved"),
        ("Avoidable Call Rate",    f"{kpis.get('avoidable_call_rate_pct', 0):.0f}%", PURPLE,"Contacts that didn't need to reach care"),
    ]

    cols = st.columns(len(perf_metrics))
    for col, (label, val, color, note) in zip(cols, perf_metrics):
        with col:
            st.markdown(
                f'<div class="scard" style="border-top:3px solid {color};">'
                f'<div class="scard-label">{label}</div>'
                f'<div class="scard-val" style="color:{color};">{val}</div>'
                f'<div class="scard-note">{note}</div>'
                f'</div>',
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
         "Build LangGraph agent flows for the top 5 intents in the roadmap: plan enquiry, "
         "bill explanation, service activation, order status, payments. Start Low-effort first."),
        ("Critical", "Deploy Proactive Care Notifications",
         "Network, bill spike, data alerts",
         f"${cl['proactive_care_savings_usd']/1000:.0f}K / month + eliminates contacts",
         "Wire event-driven alerts: outage detected → SMS before customer calls; "
         "bill spike → push notification; data near exhaustion → in-app alert."),
        ("High", "Redirect Self-Serve Eligible Calls to Digital",
         f"{selfserve_pct:.0f}% of calls deflectable",
         f"${cl['self_serve_savings_usd']/1000:.0f}K / month",
         "Route IVR intents for balance, plan info, and order status to app / chatbot. "
         "Publish in-app guides for the top 3 self-serve reasons from this analysis."),
        ("High", "Protect Agent Time for Human-Only Contacts",
         f"{human_pct:.0f}% genuinely needs agents",
         "Quality + NPS lift",
         "Once AI handles the automatable segment, agents focus on disputes, complex faults, "
         "and retention. Right-size capacity against the residual human volume."),
        ("Quick Win", "Coach Agents on Diagnosis-Phase Tooling",
         f"{needs_imp:.0f}% agents rated Needs Improvement",
         "15–20% AHT reduction",
         "Diagnosis-phase tool struggle is the primary AHT driver from this analysis. "
         "Targeted knowledge-base coaching on top technical and billing categories."),
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
    # 6 — TRENDS (multi-run)
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

        def _d(v: float, hg: bool) -> str:
            c = "#059669" if (v >= 0) == hg else "#DC2626"
            return f"<span style='color:{c};font-weight:600;'>{'↑' if v>=0 else '↓'} {v:+.1f}</span>"

        st.markdown(f"""
        <div class="callout">
          {len(runs)} runs · {sum(r.get('n_analyzed',0) for r in runs):,} calls &nbsp;|&nbsp;
          Latest vs prior — FCR {_d(latest.get('fcr_rate_pct',0)-prev.get('fcr_rate_pct',0),True)} pp
          &nbsp;·&nbsp; AHT {_d(latest.get('aht_minutes',0)-prev.get('aht_minutes',0),False)} min
          &nbsp;·&nbsp; QA {_d(latest.get('qa_avg_score',0)-prev.get('qa_avg_score',0),True)} pts
          &nbsp;·&nbsp; Source: <strong>{html.escape(latest.get('insights_source','—'))}</strong>
        </div>
        """, unsafe_allow_html=True)

    # ── Footer ────────────────────────────────────────────────────────
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='footer'>"
        f"<span>Telecom Call Intelligence &nbsp;·&nbsp; {n_calls:,} calls analysed"
        f" &nbsp;·&nbsp; {dataset}</span>"
        f"<span>{provider} &nbsp;·&nbsp; {model} &nbsp;·&nbsp; {run_date}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
