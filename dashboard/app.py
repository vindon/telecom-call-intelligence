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


  /* ── Section 6: Issue Tree ── */
  .it-queue {
    background: #FFFFFF; border-radius: 14px; padding: 22px 26px;
    margin-bottom: 18px; box-shadow: 0 1px 4px rgba(15,23,42,.08);
  }
  .it-queue-title { font-size: 1.1rem; font-weight: 900; letter-spacing: -0.01em; }
  .it-queue-sub   { font-size: 0.82rem; color: #64748B; font-weight: 600; margin: 2px 0 14px; }
  .it-queue-sub b { color: #0F172A; }
  .it-queue-row {
    display: flex; align-items: flex-start; gap: 16px; padding: 13px 0;
    border-top: 1px solid #F1F5F9;
  }
  .it-queue-row:first-child { border-top: none; padding-top: 4px; }
  .it-queue-rank {
    flex: 0 0 auto; width: 32px; height: 32px; border-radius: 50%;
    background: #0F172A; color: #fff; display: flex; align-items: center;
    justify-content: center; font-weight: 900; font-size: 0.92rem; margin-top: 1px;
  }
  .it-queue-body { flex: 1; min-width: 0; }
  .it-queue-head {
    display: flex; justify-content: space-between; align-items: baseline;
    gap: 12px; flex-wrap: wrap;
  }
  .it-queue-name   { font-weight: 800; font-size: 0.95rem; }
  .it-queue-dollar { font-weight: 900; font-size: 1.3rem; white-space: nowrap; }
  .it-queue-dollar small { font-size: 0.68rem; font-weight: 700; color: #94A3B8; }
  .it-dollar-prevent  { color: #0F766E; }
  .it-dollar-automate { color: #6D28D9; }
  .it-queue-meta { font-size: 0.78rem; color: #94A3B8; font-weight: 600; margin-top: 1px; }
  .it-queue-desc { font-size: 0.82rem; color: #334155; margin-top: 5px; line-height: 1.5; }
  .it-queue-desc b { color: #0F172A; }
  .it-queue-total {
    border-top: 2px solid #0F172A; margin-top: 4px; padding-top: 14px;
    display: flex; justify-content: space-between; align-items: baseline;
  }
  .it-queue-total-label { font-size: 0.85rem; font-weight: 800; color: #0F172A; }
  .it-queue-total-value { font-size: 1.5rem; font-weight: 900; color: #0F172A; }
  .it-queue-total-value small { font-size: 0.72rem; font-weight: 700; color: #94A3B8; margin-left: 6px; }

  .it-overview {
    background: #FFFFFF; border-radius: 14px; padding: 22px 26px;
    margin-bottom: 22px; box-shadow: 0 1px 4px rgba(15,23,42,.08);
  }
  .it-overview-title { font-size: 1rem; font-weight: 900; letter-spacing: -0.01em; }
  .it-overview-sub   { font-size: 0.82rem; color: #64748B; font-weight: 600; margin-top: 2px; }
  .it-obar { display: flex; height: 46px; border-radius: 10px; overflow: hidden; margin: 16px 0 10px; }
  .it-obar > div {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    color: #fff; line-height: 1.25;
  }
  .it-obar .pct { font-size: 0.95rem; font-weight: 900; }
  .it-obar .lbl {
    font-size: 0.62rem; font-weight: 700; letter-spacing: 0.08em;
    text-transform: uppercase; opacity: 0.9;
  }
  .it-seg-prevent  { background: #0D9488; }
  .it-seg-automate { background: #7C3AED; }  /* overridden inline with self-serve/agentic split */
  .it-seg-human    { background: #2563EB; }
  .it-legend { display: flex; gap: 18px; font-size: 0.74rem; color: #64748B; font-weight: 600; flex-wrap: wrap; }
  .it-legend span.it-dot {
    display: inline-block; width: 9px; height: 9px; border-radius: 3px;
    margin-right: 5px; vertical-align: middle;
  }
  .it-dot-simple  { background: #94A3B8; }
  .it-dot-complex { background: #F59E0B; }

  .it-category {
    background: #FFFFFF; border-radius: 14px; padding: 22px 26px;
    margin-bottom: 18px; box-shadow: 0 1px 4px rgba(15,23,42,.08);
  }
  .it-cat-head {
    display: flex; justify-content: space-between; align-items: baseline;
    margin-bottom: 8px; flex-wrap: wrap; gap: 6px;
  }
  .it-cat-name { font-size: 1.1rem; font-weight: 900; letter-spacing: -0.01em; }
  .it-cat-meta { font-size: 0.78rem; color: #64748B; font-weight: 600; }
  .it-pbar {
    display: flex; height: 9px; border-radius: 5px; overflow: hidden;
    margin: 10px 0 16px; background: #F1F5F9;
  }
  .it-pbar > div { height: 100%; }
  .it-pbar .pv  { background: #0D9488; }
  .it-pbar .ass { background: #7C3AED; }
  .it-pbar .aai { background: #A78BFA; }
  .it-pbar .hu  { background: #2563EB; }

  .it-branches { margin-left: 2px; padding-left: 22px; border-left: 2px solid #E2E8F0; }
  .it-branch { position: relative; padding: 0 0 16px 4px; }
  .it-branch:last-child { padding-bottom: 0; }
  .it-branch::before {
    content: ''; position: absolute; left: -22px; top: 11px;
    width: 20px; height: 2px; background: #E2E8F0;
  }
  .it-branch-top { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 6px; }
  .it-badge {
    display: inline-block; padding: 3px 12px; border-radius: 20px;
    font-size: 0.65rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase;
  }
  .it-badge-prevent  { background: #CCFBF1; color: #0F766E; }
  .it-badge-automate { background: #EDE9FE; color: #6D28D9; }
  .it-badge-human    { background: #DBEAFE; color: #1D4ED8; }
  .it-branch-pct { font-size: 1.3rem; font-weight: 900; letter-spacing: -0.02em; }
  .it-pct-prevent  { color: #0F766E; }
  .it-pct-automate { color: #6D28D9; }
  .it-pct-human    { color: #1D4ED8; }
  .it-branch-n { font-size: 0.74rem; color: #94A3B8; font-weight: 600; margin: 2px 0 8px; }

  .it-chip {
    display: inline-block; border-radius: 6px; padding: 2px 9px;
    font-size: 0.7rem; font-weight: 700; margin: 0 5px 5px 0; border: 1px solid;
  }
  .it-chip-simple  { background: #F8FAFC; color: #475569; border-color: #E2E8F0; }
  .it-chip-complex { background: #FFFBEB; color: #B45309; border-color: #FDE68A; }
  .it-chip-neutral { background: #F8FAFC; color: #94A3B8; border-color: #E2E8F0; }

  .it-note { font-size: 0.82rem; color: #334155; line-height: 1.55; margin-top: 6px; }
  .it-note b { color: #0F172A; }

  .it-compact-card {
    background: #FFFFFF; border-radius: 14px; padding: 18px 26px 8px;
    box-shadow: 0 1px 4px rgba(15,23,42,.08);
  }
  .it-compact-title {
    font-size: 0.78rem; font-weight: 800; letter-spacing: 0.12em;
    text-transform: uppercase; color: #94A3B8; margin-bottom: 14px;
  }
  .it-compact-row { padding: 12px 0; border-top: 1px solid #F1F5F9; }
  .it-compact-row:first-child { border-top: none; }
  .it-compact-head { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 6px; }
  .it-compact-name { font-size: 0.92rem; font-weight: 800; }
  .it-compact-meta { font-size: 0.76rem; color: #94A3B8; font-weight: 600; }
  .it-compact-row .it-pbar { margin: 6px 0 8px; height: 7px; }

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
        "model": "claude-haiku-4-5-20251001",
        "inference_provider": "Anthropic (Claude)",
    },
    "kpis": {
        "total_calls_analyzed": 100,
        "avg_handle_time_seconds": 524, "avg_handle_time_minutes": 8.7,
        "fcr_rate_pct": 68.0, "avoidable_call_rate_pct": 41.0,
        "self_serve_deflection_pct": 37.0, "agentic_ai_resolvable_pct": 29.0,
        "proactive_outreach_pct": 12.0, "all_issues_resolved_pct": 71.0,
        "escalation_rate_pct": 14.0, "sentiment_improved_pct": 61.0,
        "agent_tool_struggle_pct": 23.0,
        # Mutually-exclusive resolution segmentation (sums to 100) —
        # derived to match the cost_levers below (see _resolution_segments).
        "prevent_pct": 14.5, "automate_pct": 66.0, "human_required_pct": 19.5,
        "automate_self_serve_pct": 37.0, "automate_agentic_pct": 29.0,
    },
    "phase_avg_seconds": {
        "Welcome & Auth": 46, "Discovery": 108, "Diagnosis": 152,
        "Resolution": 128, "Hold": 87, "Upsell": 44, "Closing": 54,
    },
    "phase_drilldown": {
        "Discovery": [
            {"intent": "technical",   "avg_seconds": 135.0, "calls": 31, "stall_pct": 18.0},
            {"intent": "device",      "avg_seconds": 122.0, "calls": 4,  "stall_pct": 10.0},
            {"intent": "billing",     "avg_seconds": 110.0, "calls": 38, "stall_pct": 12.0},
            {"intent": "account",     "avg_seconds": 95.0,  "calls": 9,  "stall_pct": 5.0},
            {"intent": "plan",        "avg_seconds": 88.0,  "calls": 16, "stall_pct": 3.0},
        ],
        "Diagnosis": [
            {"intent": "technical",   "avg_seconds": 195.0, "calls": 31, "stall_pct": 35.0},
            {"intent": "device",      "avg_seconds": 178.0, "calls": 4,  "stall_pct": 20.0},
            {"intent": "billing",     "avg_seconds": 145.0, "calls": 38, "stall_pct": 22.0},
            {"intent": "account",     "avg_seconds": 120.0, "calls": 9,  "stall_pct": 10.0},
            {"intent": "information", "avg_seconds": 90.0,  "calls": 2,  "stall_pct": 0.0},
        ],
        "Resolution": [
            {"intent": "plan",        "avg_seconds": 160.0, "calls": 16, "stall_pct": 15.0},
            {"intent": "billing",     "avg_seconds": 140.0, "calls": 38, "stall_pct": 18.0},
            {"intent": "technical",   "avg_seconds": 125.0, "calls": 31, "stall_pct": 10.0},
            {"intent": "account",     "avg_seconds": 105.0, "calls": 9,  "stall_pct": 5.0},
            {"intent": "device",      "avg_seconds": 95.0,  "calls": 4,  "stall_pct": 0.0},
        ],
        "Upsell": [
            {"intent": "plan",        "avg_seconds": 70.0, "calls": 16, "stall_pct": 0.0},
            {"intent": "billing",     "avg_seconds": 50.0, "calls": 38, "stall_pct": 0.0},
            {"intent": "information", "avg_seconds": 35.0, "calls": 2,  "stall_pct": 0.0},
            {"intent": "account",     "avg_seconds": 28.0, "calls": 9,  "stall_pct": 0.0},
            {"intent": "device",      "avg_seconds": 15.0, "calls": 4,  "stall_pct": 0.0},
        ],
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
        # Phase-time P&L (Serve P1-P4 / Sell P5 / Retain cross-cutting) —
        # derived from phase_avg_seconds above via _phase_pnl (70.1/7.1/22.8% of 619s total).
        "serve_time_pct": 70.1, "serve_cost_usd": 420600,
        "sell_time_pct": 7.1,   "sell_cost_usd": 42600,
        "retain_time_pct": 22.8, "retain_cost_usd": 136800,
    },
    "issue_breakdown": {
        "categories": [
            {
                "category": "billing", "count": 38, "pct": 38.0, "dollars": 228000,
                "segments": {
                    "prevent":            {"count": 5,  "pct": 13.2, "methods": {"agent_action": 3, "self_serve_guidance": 2}},
                    "automate_self_serve":{"count": 20, "pct": 52.6, "methods": {"self_serve_guidance": 15, "agent_action": 5}},
                    "automate_agentic":   {"count": 8,  "pct": 21.1, "methods": {"agent_action": 8}},
                    "human":              {"count": 5,  "pct": 13.2, "methods": {"escalated": 3, "unresolved": 2}},
                },
            },
            {
                "category": "technical", "count": 31, "pct": 31.0, "dollars": 186000,
                "segments": {
                    "prevent":            {"count": 8,  "pct": 25.8, "methods": {"self_serve_guidance": 5, "agent_action": 3}},
                    "automate_self_serve":{"count": 5,  "pct": 16.1, "methods": {"self_serve_guidance": 4, "agent_action": 1}},
                    "automate_agentic":   {"count": 10, "pct": 32.3, "methods": {"agent_action": 7, "workaround": 3}},
                    "human":              {"count": 8,  "pct": 25.8, "methods": {"escalated": 5, "workaround": 2, "unresolved": 1}},
                },
            },
            {
                "category": "plan", "count": 16, "pct": 16.0, "dollars": 96000,
                "segments": {
                    "prevent":            {"count": 1, "pct": 6.2,  "methods": {"agent_action": 1}},
                    "automate_self_serve":{"count": 8, "pct": 50.0, "methods": {"self_serve_guidance": 6, "agent_action": 2}},
                    "automate_agentic":   {"count": 5, "pct": 31.2, "methods": {"agent_action": 5}},
                    "human":              {"count": 2, "pct": 12.5, "methods": {"escalated": 2}},
                },
            },
            {
                "category": "account", "count": 9, "pct": 9.0, "dollars": 54000,
                "segments": {
                    "automate_self_serve":{"count": 3, "pct": 33.3, "methods": {"self_serve_guidance": 2, "agent_action": 1}},
                    "automate_agentic":   {"count": 4, "pct": 44.4, "methods": {"agent_action": 4}},
                    "human":              {"count": 2, "pct": 22.2, "methods": {"escalated": 2}},
                },
            },
            {
                "category": "device", "count": 4, "pct": 4.0, "dollars": 24000,
                "segments": {
                    "automate_self_serve":{"count": 1, "pct": 25.0, "methods": {"self_serve_guidance": 1}},
                    "automate_agentic":   {"count": 2, "pct": 50.0, "methods": {"agent_action": 2}},
                    "human":              {"count": 1, "pct": 25.0, "methods": {"escalated": 1}},
                },
            },
            {
                "category": "information", "count": 2, "pct": 2.0, "dollars": 12000,
                "segments": {
                    "human": {"count": 2, "pct": 100.0, "methods": {"escalated": 1, "unresolved": 1}},
                },
            },
        ],
        "build_queue": [
            {
                "category": "billing", "segment": "automate", "count": 28, "pct": 73.7,
                "dollars": 168000, "category_count": 38, "self_serve_count": 20, "agentic_count": 8,
                "methods": {"self_serve_guidance": 15, "agent_action": 13},
            },
            {
                "category": "technical", "segment": "automate", "count": 15, "pct": 48.4,
                "dollars": 90000, "category_count": 31, "self_serve_count": 5, "agentic_count": 10,
                "methods": {"agent_action": 8, "self_serve_guidance": 4, "workaround": 3},
            },
            {
                "category": "plan", "segment": "automate", "count": 13, "pct": 81.2,
                "dollars": 78000, "category_count": 16, "self_serve_count": 8, "agentic_count": 5,
                "methods": {"self_serve_guidance": 6, "agent_action": 7},
            },
            {
                "category": "technical", "segment": "prevent", "count": 8, "pct": 25.8,
                "dollars": 48000, "category_count": 31,
                "methods": {"self_serve_guidance": 5, "agent_action": 3},
            },
        ],
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


def chart_drilldown_intents(rows: list[dict], color: str) -> go.Figure:
    """Top-N intents ranked by avg seconds spent in one phase, with stall rate."""
    rows   = list(reversed(rows))  # highest bar on top
    labels = [r["intent"].replace("_", " ").title() for r in rows]
    secs   = [r["avg_seconds"] for r in rows]
    calls  = [r["calls"] for r in rows]
    stalls = [r["stall_pct"] for r in rows]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=secs, orientation="h",
        marker=dict(color=color, line_width=0),
        text=[f"  {s:.0f}s" for s in secs],
        textposition="inside", insidetextanchor="start",
        textfont=dict(color="white", size=11, family="Inter"),
        customdata=list(zip(calls, stalls)),
        hovertemplate=(
            "<b>%{y}</b><br>%{x:.0f}s avg · %{customdata[0]} calls<br>"
            "%{customdata[1]:.0f}% flagged as agent stall<extra></extra>"
        ),
    ))
    fig.update_layout(
        **PLOTLY,
        height=240,
        xaxis=dict(title="Avg seconds in phase", gridcolor="#F1F5F9", zeroline=False),
        yaxis=dict(),
        margin=dict(l=10, r=20, t=12, b=40),
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


# ── Section 6: Issue-tree helpers ──────────────────────────────────────
# issue_1_resolution_method values, classified for chip coloring.
# Combo values (e.g. "workaround|escalated") are complex if any part is.
_METHOD_COMPLEX = {"escalated", "workaround", "unresolved"}
_METHOD_SIMPLE  = {"agent_action", "self_serve_guidance"}

# Render order for the 4-way proportion bar / overview bar.
_SEG_BAR_CLASS = {
    "prevent": "pv", "automate_self_serve": "ass",
    "automate_agentic": "aai", "human": "hu",
}


def _method_class(method: str) -> str:
    parts = method.split("|")
    if any(p in _METHOD_COMPLEX for p in parts):
        return "complex"
    if any(p in _METHOD_SIMPLE for p in parts):
        return "simple"
    return "neutral"


def _chips_html(methods: dict) -> str:
    return "".join(
        f'<span class="it-chip it-chip-{_method_class(m)}">{html.escape(m)} &times;{c}</span>'
        for m, c in methods.items()
    )


def _proportion_bar_html(segments: dict) -> str:
    bars = "".join(
        f'<div class="{bar_cls}" style="width:{segments[seg_key]["pct"]}%"></div>'
        for seg_key, bar_cls in _SEG_BAR_CLASS.items()
        if segments.get(seg_key, {}).get("pct", 0) > 0
    )
    return f'<div class="it-pbar">{bars}</div>'


def _combine_automate(segments: dict) -> dict | None:
    """Merge automate_self_serve + automate_agentic into one displayed
    tier — Prevent/Automate/Human — with the self-serve/agentic split
    retained for the badge label and build-queue title."""
    ss = segments.get("automate_self_serve")
    ai = segments.get("automate_agentic")
    if not ss and not ai:
        return None
    methods: dict = {}
    for seg in (ss, ai):
        if not seg:
            continue
        for m, c in seg["methods"].items():
            methods[m] = methods.get(m, 0) + c
    return {
        "count": (ss["count"] if ss else 0) + (ai["count"] if ai else 0),
        "pct":   round((ss["pct"] if ss else 0) + (ai["pct"] if ai else 0), 1),
        "methods": methods,
        "self_serve_count": ss["count"] if ss else 0,
        "agentic_count":    ai["count"] if ai else 0,
    }


def _automate_label(seg: dict) -> str:
    ss, ai = seg["self_serve_count"], seg["agentic_count"]
    if ss and ai:
        return f"Automate &middot; {ss} self-serve / {ai} agentic AI"
    if ai and not ss:
        return "Automate &middot; Agentic AI"
    return "Automate &middot; Self-Serve"


def _segment_note(seg_key: str, seg: dict) -> str:
    """Data-driven 'what the agent did vs. the build opportunity' line,
    derived from the resolution-method mix rather than hand-written
    per-category prose — stays correct as the dataset changes."""
    if seg_key == "prevent":
        return (
            "These calls shouldn't happen at all &mdash; <b>proactive outreach removes the "
            "contact entirely</b>, independent of how the agent handled it today."
        )
    if seg_key == "human":
        return (
            "Genuinely non-deterministic &mdash; escalations, disputes, and multi-system "
            "faults with no fixed script. <b>Concentrate human expertise here.</b>"
        )
    complex_n = sum(c for m, c in seg["methods"].items() if _method_class(m) == "complex")
    if complex_n:
        return (
            f"<b>{complex_n} of {seg['count']} were escalated or worked around even though "
            f"this is fully automatable</b> &mdash; the agent did more than the call needed."
        )
    return (
        "Deterministic, repeatable steps &mdash; a self-serve flow or AI agent can follow "
        "the same script end-to-end."
    )


def _branch_html(seg_key: str, label: str, seg: dict, category_count: int) -> str:
    return (
        f'<div class="it-branch">'
        f'<div class="it-branch-top">'
        f'<span class="it-badge it-badge-{seg_key}">{label}</span>'
        f'<span class="it-branch-pct it-pct-{seg_key}">{seg["pct"]:.0f}%</span>'
        f'</div>'
        f'<div class="it-branch-n">{seg["count"]} of {category_count} calls</div>'
        f'<div>{_chips_html(seg["methods"])}</div>'
        f'<div class="it-note">{_segment_note(seg_key, seg)}</div>'
        f'</div>'
    )


def _category_card_html(cat: dict) -> str:
    segments, n_cat = cat["segments"], cat["count"]
    branches = ""
    if "prevent" in segments:
        branches += _branch_html("prevent", "Prevent", segments["prevent"], n_cat)
    automate = _combine_automate(segments)
    if automate:
        branches += _branch_html("automate", _automate_label(automate), automate, n_cat)
    if "human" in segments:
        branches += _branch_html("human", "Human Required", segments["human"], n_cat)

    return (
        f'<div class="it-category">'
        f'<div class="it-cat-head">'
        f'<div class="it-cat-name">{html.escape(cat["category"].title())}</div>'
        f'<div class="it-cat-meta">{n_cat} calls &middot; {cat["pct"]:.0f}% of sample &middot; '
        f'&asymp; ${cat["dollars"]/1000:.0f}K / month at scale</div>'
        f'</div>'
        f'{_proportion_bar_html(segments)}'
        f'<div class="it-branches">{branches}</div>'
        f'</div>'
    )


def _compact_row_html(cat: dict) -> str:
    segments, n_cat = cat["segments"], cat["count"]
    automate = _combine_automate(segments)

    summary_parts = []
    if "prevent" in segments:
        summary_parts.append(f'<span class="it-pct-prevent">Prevent {segments["prevent"]["pct"]:.0f}%</span>')
    if automate:
        summary_parts.append(f'<span class="it-pct-automate">Automate {automate["pct"]:.0f}%</span>')
    if "human" in segments:
        summary_parts.append(f'<span class="it-pct-human">Human {segments["human"]["pct"]:.0f}%</span>')

    # Lead with whichever segment carries the most calls in this category.
    candidates = [("prevent", segments.get("prevent")), ("automate", automate), ("human", segments.get("human"))]
    dominant_key, dominant_seg = max(
        (c for c in candidates if c[1]), key=lambda kv: kv[1]["pct"]
    )

    return (
        f'<div class="it-compact-row">'
        f'<div class="it-compact-head">'
        f'<div class="it-compact-name">{html.escape(cat["category"].title())}</div>'
        f'<div class="it-compact-meta">{n_cat} calls &middot; {cat["pct"]:.0f}% &middot; '
        f'&asymp; ${cat["dollars"]/1000:.0f}K/mo &middot; {" &middot; ".join(summary_parts)}</div>'
        f'</div>'
        f'{_proportion_bar_html(segments)}'
        f'<div class="it-note">{_segment_note(dominant_key, dominant_seg)}</div>'
        f'</div>'
    )


def _build_queue_title(item: dict) -> str:
    cat_title = item["category"].title()
    if item["segment"] == "prevent":
        return f"{cat_title} &mdash; Proactive Outreach"
    ss, ai = item.get("self_serve_count", 0), item.get("agentic_count", 0)
    if ss and ai:
        return f"{cat_title} &mdash; Self-Serve + Agentic AI"
    if ai and not ss:
        return f"{cat_title} &mdash; Agentic AI Agent"
    return f"{cat_title} &mdash; Self-Serve Automation"


def _build_queue_desc(item: dict) -> str:
    cat_title = item["category"].title()
    count, total, pct = item["count"], item["category_count"], item["pct"]
    if item["segment"] == "prevent":
        return (
            f"{count} of {total} {cat_title} calls ({pct:.0f}%) &mdash; proactive outreach "
            f"<b>removes the call entirely</b>, regardless of how it's resolved today."
        )
    complex_n = sum(c for m, c in item["methods"].items() if _method_class(m) == "complex")
    desc = (
        f"{count} of {total} {cat_title} calls ({pct:.0f}%) follow "
        f"<b>deterministic, repeatable steps</b>"
    )
    if complex_n:
        desc += (
            f" &mdash; <b>{complex_n} of these are currently escalated or worked around</b> "
            f"even though the steps are automatable, the clearest efficiency gap in this category."
        )
    else:
        desc += "."
    return desc


def _build_queue_row_html(item: dict, rank: int) -> str:
    dollar_cls = f"it-dollar-{item['segment']}"
    return (
        f'<div class="it-queue-row">'
        f'<div class="it-queue-rank">{rank}</div>'
        f'<div class="it-queue-body">'
        f'<div class="it-queue-head">'
        f'<div class="it-queue-name">{_build_queue_title(item)}</div>'
        f'<div class="it-queue-dollar {dollar_cls}">${item["dollars"]/1000:.0f}K<small>/mo</small></div>'
        f'</div>'
        f'<div class="it-queue-meta">{item["count"]} of {item["category_count"]} '
        f'{html.escape(item["category"].title())} calls &middot; {item["pct"]:.0f}%</div>'
        f'<div class="it-queue-desc">{_build_queue_desc(item)}</div>'
        f'</div>'
        f'</div>'
    )


def _overview_bar_html(prevent_pct: float, automate_pct: float, human_pct: float,
                        selfserve_pct: float, agentic_pct: float, base: float) -> str:
    segs = []
    if prevent_pct > 0:
        segs.append(("it-seg-prevent", prevent_pct, "Prevent", ""))
    if automate_pct > 0:
        split = round(selfserve_pct / automate_pct * 100, 1)
        gradient = (
            f"background:linear-gradient(90deg,#7C3AED 0%,#7C3AED {split}%,"
            f"#A78BFA {split}%,#A78BFA 100%);"
        )
        segs.append(("", automate_pct, "Automate", gradient))
    if human_pct > 0:
        segs.append(("it-seg-human", human_pct, "Human", ""))

    bars = "".join(
        f'<div class="{cls}" style="width:{pct}%;{extra}">'
        f'<span class="pct">${round(base * pct / 100)/1000:.0f}K</span>'
        f'<span class="lbl">{label} &middot; {pct:.0f}%</span>'
        f'</div>'
        for cls, pct, label, extra in segs
    )
    return f'<div class="it-obar">{bars}</div>'


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

    # Segment arithmetic — mutually-exclusive segments computed in
    # pipeline/aggregator.py (_resolution_segments). These sum to 100%;
    # do not derive them from the overlapping marginal *_pct fields.
    prevent_pct   = float(kpis.get("prevent_pct", 0))
    automate_pct  = float(kpis.get("automate_pct", 0))
    human_pct     = float(kpis.get("human_required_pct", 0))
    selfserve_pct = float(kpis.get("automate_self_serve_pct", 0))
    agentic_pct   = float(kpis.get("automate_agentic_pct", 0))
    total_auto    = prevent_pct + automate_pct

    cpp      = cl["cost_per_call_usd"]
    vol      = cl["monthly_volume_estimate"]
    base     = cl["baseline_monthly_cost_usd"]
    opp      = cl["total_savings_opportunity_usd"]
    annual   = opp * 12

    # Phase insight stats
    total_secs = sum(phases.values()) or 1
    disc_secs  = phases.get("Discovery", 0)
    diag_secs  = phases.get("Diagnosis", 0)
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
    badge     = "DEMO DATA" if is_demo else "LIVE DATA"
    badge_cls = "badge-demo" if is_demo else "badge-live"

    # Phase-time-based P&L — Serve (P1-P4) / Sell (P5) / Retain (cross-cutting)
    # computed in pipeline/aggregator.py (_phase_pnl), stored in cost_levers.
    serve_time_pct = float(cl.get("serve_time_pct", 0))
    sell_time_pct  = float(cl.get("sell_time_pct", 0))
    retain_time_pct = float(cl.get("retain_time_pct", 0))
    serve_cost     = cl.get("serve_cost_usd", 0)
    sell_cost      = cl.get("sell_cost_usd", 0)
    retain_cost    = cl.get("retain_cost_usd", 0)

    # ── HERO ─────────────────────────────────────────────────────────
    # Hero — headline only
    hero_html = (
        '<div class="hero">'
        '<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;">'
        '<div>'
        '<div class="hero-eyebrow">Care Call Cost Analysis</div>'
        '<div class="hero-headline">Telecom <span>Cost Intelligence</span><br>for Care Calls</div>'
        '<div class="hero-subline">Identifying cost levers across the customer journey in care calls — '
        'surfacing cost-to-serve drivers and proactive issue-resolution opportunities, '
        '<strong style="color:#E2E8F0;">from real call transcripts.</strong></div>'
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
        f'<div style="font-size:0.75rem;color:#64748B;font-style:italic;margin-bottom:14px;">Cost allocated by where call handle time goes · forecast at {vol:,} calls/month · ${cpp:.2f}/call unit cost · from {n_calls}-call sample</div>'
        '<div style="display:flex;justify-content:space-between;align-items:baseline;padding:9px 0;border-bottom:1px solid #F1F5F9;">'
        '<span style="font-size:0.88rem;color:#0F172A;font-weight:600;">Cost to Serve <span style="color:#94A3B8;font-weight:500;">(P1–P4)</span></span>'
        f'<span style="font-size:0.8rem;color:#64748B;font-weight:600;">{serve_time_pct:.0f}% of AHT</span>'
        f'<span style="font-size:1.1rem;font-weight:800;color:#0F172A;">${serve_cost/1000:.0f}K/mo</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:baseline;padding:9px 0;border-bottom:1px solid #F1F5F9;">'
        '<span style="font-size:0.88rem;color:#0F172A;font-weight:600;">Cost to Sell <span style="color:#94A3B8;font-weight:500;">(P5)</span></span>'
        f'<span style="font-size:0.8rem;color:#64748B;font-weight:600;">{sell_time_pct:.0f}% of AHT</span>'
        f'<span style="font-size:1.1rem;font-weight:800;color:#0F172A;">${sell_cost/1000:.0f}K/mo</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:baseline;padding:9px 0;border-bottom:1px solid #F1F5F9;">'
        '<span style="font-size:0.88rem;color:#0F172A;font-weight:600;">Cost to Retain <span style="color:#94A3B8;font-weight:500;">(cross-cutting)</span></span>'
        f'<span style="font-size:0.8rem;color:#64748B;font-weight:600;">{retain_time_pct:.0f}% of AHT</span>'
        f'<span style="font-size:1.1rem;font-weight:800;color:#0F172A;">${retain_cost/1000:.0f}K/mo</span>'
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
    # 2 — PHASE DRILL-DOWN: WHAT'S DRIVING TIME INSIDE EACH PHASE
    # ═══════════════════════════════════════════════════════════════
    _sec("2 — Phase Drill-Down: What's Driving Time Inside Each Phase")

    st.markdown(
        "<div style='font-size:0.93rem;color:#334155;line-height:1.7;margin-bottom:14px;'>"
        "Section 1 shows <em>where</em> handle time goes. This breaks each cost-bearing phase "
        "down by <strong>which customer intent drives it</strong> — and how often agents got "
        "stuck there (<em>stall rate</em> = share of calls where this was the agent's most "
        "disproportionate phase).</div>",
        unsafe_allow_html=True,
    )

    drilldown  = data.get("phase_drilldown", {})
    dd_phases  = [p for p in ["Discovery", "Diagnosis", "Resolution", "Upsell"] if drilldown.get(p)]

    if dd_phases:
        tabs = st.tabs(dd_phases)
        for tab, phase in zip(tabs, dd_phases):
            with tab:
                rows = drilldown[phase]
                color, _ptype = PHASE_META.get(phase, ("#94A3B8", ""))
                top = rows[0]
                top_intent = top["intent"].replace("_", " ").title()
                stall_note = (
                    f", {top['stall_pct']:.0f}% flagged as agent stall"
                    if top["stall_pct"] > 0 else ""
                )
                st.markdown(
                    f"<div style='font-size:0.85rem;color:#475569;margin-bottom:8px;'>"
                    f"<strong style='color:{color};'>{top_intent}</strong> calls take longest in "
                    f"{phase} — averaging {top['avg_seconds']:.0f}s ({top['calls']} calls{stall_note}).</div>",
                    unsafe_allow_html=True,
                )
                st.plotly_chart(chart_drilldown_intents(rows, color), use_container_width=True)
    else:
        st.markdown("""<div class="callout" style="margin-top:4px;">
          Phase drill-down requires <code>phase_drilldown</code> in <code>summary.json</code> —
          run <code>python merge_outputs.py</code> to regenerate.
        </div>""", unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════
    # 3 — RESOLUTION OPPORTUNITY: WHAT THE DATA SAYS
    # ═══════════════════════════════════════════════════════════════
    _sec("3 — Resolution Opportunity: Insights from the Calls")

    st.markdown(
        f"<div style='font-size:0.93rem;color:#334155;line-height:1.7;margin-bottom:20px;'>"
        f"From <strong>{n_calls:,} calls analysed</strong>, every contact was classified by "
        f"whether a human agent was genuinely required — or whether autonomous AI could have "
        f"resolved it. <strong>{total_auto:.0f}%</strong> did not require a human.</div>",
        unsafe_allow_html=True,
    )

    # Build segment list — only show PREVENT if > 0
    segments_display = []
    if prevent_pct > 0:
        segments_display.append(("prevent", prevent_pct))
    segments_display.append(("automate", automate_pct))
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
    if prevent_pct == 0 and ic_clean:
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
    if prevent_pct > 0:
        seg_bar_data.append(("Proactive Care", prevent_pct, TEAL))
    seg_bar_data.append(("Agentic AI / Self-Serve", automate_pct, PURPLE))
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
    # 4 — WHICH AGENTS TO BUILD
    # ═══════════════════════════════════════════════════════════════
    _sec("4 — Which AI Agents to Build — Ranked by Monthly Saving")

    rows = _build_roadmap(ic_clean, cpp, vol)
    total_rm_saving = sum(r["monthly_saving"] for r in rows) if rows else 0

    if rows:
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
    # 5 — ACTUAL PERFORMANCE
    # ═══════════════════════════════════════════════════════════════
    _sec("5 — Actual Performance")

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
    # 6 — ISSUE TREE: CALL TYPE → AGENT ACTIVITY → BUILD SEGMENT
    # ═══════════════════════════════════════════════════════════════
    _sec("6 — Issue Tree: Call Type, Agent Activity & Build Order")

    ib          = data.get("issue_breakdown", {"categories": [], "build_queue": []})
    categories  = ib.get("categories", [])
    queue_items = ib.get("build_queue", [])

    if not categories:
        st.markdown(
            '<div class="callout">Issue-tree breakdown requires <code>issue_breakdown</code> in '
            '<code>summary.json</code> — run <code>python merge_outputs.py</code> to regenerate.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div style='font-size:0.93rem;color:#334155;line-height:1.7;margin-bottom:18px;'>"
            "For each call type, every call is grouped by what the agent <strong>actually did</strong> "
            "(<code>issue_1_resolution_method</code>) and which build segment it falls into — "
            "<strong>Prevent</strong> (proactive outreach removes the call), "
            "<strong>Automate</strong> (deterministic, repeatable — self-serve or agentic AI), or "
            "<strong>Human</strong> (genuinely needs judgment).</div>",
            unsafe_allow_html=True,
        )

        # ── Recommended Build Order ────────────────────────────────────
        if queue_items:
            total_dollars = sum(item["dollars"] for item in queue_items)
            total_pct = round(total_dollars / base * 100) if base else 0
            queue_rows_html = "".join(
                _build_queue_row_html(item, i + 1) for i, item in enumerate(queue_items)
            )
            st.markdown(
                f'<div class="it-queue">'
                f'<div class="it-queue-title">Recommended Build Order</div>'
                f'<div class="it-queue-sub">Top {len(queue_items)} Prevent / Automate opportunities '
                f'across all call types, ranked by monthly $ impact at {vol:,} calls/month</div>'
                f'{queue_rows_html}'
                f'<div class="it-queue-total">'
                f'<div class="it-queue-total-label">Top {len(queue_items)} combined</div>'
                f'<div class="it-queue-total-value">${total_dollars/1000:.0f}K/mo'
                f'<small>{total_pct}% of baseline</small></div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── Full picture ────────────────────────────────────────────────
        st.markdown(
            f'<div class="it-overview">'
            f'<div class="it-overview-title">Full Picture &mdash; All {n_calls:,} Calls</div>'
            f'<div class="it-overview-sub">How the ${base/1000:.0f}K/mo baseline splits across '
            f'Prevent / Automate / Human</div>'
            f'{_overview_bar_html(prevent_pct, automate_pct, human_pct, selfserve_pct, agentic_pct, base)}'
            f'<div class="it-legend">'
            f'<span><span class="it-dot it-dot-simple"></span>Simple / deterministic '
            f'(agent action, self-serve guidance)</span>'
            f'<span><span class="it-dot it-dot-complex"></span>Complex / judgment '
            f'(escalated, workaround, unresolved)</span>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── Featured call types (top 2 by volume) + compact rows for the rest ──
        featured, remaining = categories[:2], categories[2:]
        for cat in featured:
            st.markdown(_category_card_html(cat), unsafe_allow_html=True)

        if remaining:
            compact_rows_html = "".join(_compact_row_html(c) for c in remaining)
            st.markdown(
                f'<div class="it-compact-card">'
                f'<div class="it-compact-title">Other Call Types</div>'
                f'{compact_rows_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

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
