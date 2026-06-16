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
    background: #CD040B;
    padding: 20px 44px 18px;
    margin: -1rem -1rem 0;
    border-radius: 0 0 20px 20px;
  }
  .hero-top { text-align: center; margin-bottom: 16px; }
  .hero-bottom {
    display: flex; justify-content: space-between; align-items: flex-end;
    gap: 32px; border-top: 1px solid rgba(255,255,255,0.12); padding-top: 12px;
  }
  .hero-eyebrow {
    font-size: 0.62rem; font-weight: 700; letter-spacing: 0.22em;
    text-transform: uppercase; color: rgba(255,255,255,0.6); margin-bottom: 8px;
  }
  .hero-headline {
    font-size: 2.1rem; font-weight: 900; color: #FFFFFF;
    letter-spacing: -0.04em; line-height: 1.1; margin: 0 0 8px;
  }
  .hero-headline span { color: #FFFFFF; }
  .hero-subline {
    font-size: 0.85rem; color: rgba(255,255,255,0.75); font-weight: 400; margin: 0;
  }
  .hero-agentic {
    font-size: 0.73rem; font-weight: 500; color: rgba(255,255,255,0.85);
    line-height: 1.6; max-width: 540px;
  }
  .hero-agentic strong { color: #FFFFFF; font-weight: 800; }
  .hero-meta-row { text-align: right; }
  .hero-meta {
    font-size: 0.67rem; color: rgba(255,255,255,0.65); line-height: 1.7; white-space: nowrap;
  }
  .hero-disclaimer {
    font-size: 0.62rem; color: rgba(255,255,255,0.5); line-height: 1.65;
    white-space: nowrap; text-align: right; margin-top: 4px;
  }
  /* ── Tab bar — segmented button style ── */
  [data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 0 !important;
    background: #E2E8F0 !important;
    border-radius: 10px !important;
    padding: 5px !important;
    border-bottom: none !important;
    margin-top: 16px !important;
  }
  [data-testid="stTabs"] button[role="tab"] {
    flex: 1 !important;
    padding: 14px 0 !important;
    justify-content: center !important;
    border-radius: 7px !important;
    color: #64748B !important;
    background: transparent !important;
    border: none !important;
    transition: all 0.18s ease !important;
  }
  [data-testid="stTabs"] button[role="tab"] p,
  [data-testid="stTabs"] button[role="tab"] span,
  [data-testid="stTabs"] button[role="tab"] div {
    font-size: 1.15rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.01em !important;
  }
  [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    background: #FFFFFF !important;
    color: #0F172A !important;
    box-shadow: 0 1px 6px rgba(15,23,42,0.12) !important;
  }
  [data-testid="stTabs"] button[role="tab"][aria-selected="true"] p,
  [data-testid="stTabs"] button[role="tab"][aria-selected="true"] span,
  [data-testid="stTabs"] button[role="tab"][aria-selected="true"] div {
    color: #0F172A !important;
  }
  [data-testid="stTabs"] [data-baseweb="tab-highlight"],
  [data-testid="stTabs"] [data-baseweb="tab-border"] {
    display: none !important;
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
  .badge-live { background:rgba(255,255,255,0.15); border:1px solid rgba(255,255,255,0.5); color:#FFFFFF; }
  .badge-demo { background:rgba(99,102,241,.2); border:1px solid rgba(99,102,241,.4); color:#A5B4FC; }

  /* ── Section label ── */
  .section-label {
    font-size: 0.88rem; font-weight: 800; letter-spacing: 0.08em;
    text-transform: uppercase; color: #0F172A;
    margin: 48px 0 22px; padding: 14px 18px;
    background: #F1F5F9;
    border-left: 4px solid #0F172A;
    border-radius: 0 8px 8px 0;
    line-height: 1;
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
  .data-disclaimer {
    display: flex; align-items: flex-start; gap: 12px;
    background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 10px;
    padding: 14px 18px; margin: 18px 0 6px; font-size: 0.84rem;
    color: #78350F; line-height: 1.65;
  }
  .data-disclaimer-icon {
    font-size: 1.1rem; flex-shrink: 0; margin-top: 1px;
  }
  .data-disclaimer strong { color: #92400E; }
  .data-disclaimer code   { background: #FEF3C7; padding: 1px 5px; border-radius: 4px;
                             font-size: 0.82rem; color: #78350F; }
  .data-footnote {
    font-size: 0.74rem; color: #94A3B8; font-style: italic;
    margin-top: 10px; padding-top: 8px; border-top: 1px solid #F1F5F9;
    line-height: 1.55;
  }
  .data-footnote strong { color: #64748B; font-style: normal; }

  /* ── Cost Intelligence Deep Dive (cts-* / pah-*) ─────────── */
  .cts-legend { display:flex; align-items:center; gap:18px; flex-wrap:wrap;
    margin-bottom:20px; padding-bottom:18px; border-bottom:1px solid #E2E8F0; }
  .cts-legend-item { display:flex; align-items:center; gap:6px; }
  .cts-swatch { width:10px; height:10px; border-radius:2px; flex-shrink:0; }
  .cts-swatch-label { font-size:11px; color:#475569; font-weight:500; }
  .cts-eyebrow { font-size:10px; font-weight:700; letter-spacing:0.13em;
    text-transform:uppercase; color:#94A3B8; margin-bottom:12px; }
  .cts-hero-wrap { background:#fff; border-radius:12px; border:1px solid #E2E8F0;
    box-shadow:0 1px 4px rgba(15,23,42,.05); padding:22px 26px; margin-bottom:16px; }
  .cts-hero-row { display:flex; align-items:center; }
  .cts-hero-label { width:100px; flex-shrink:0; }
  .cts-hero-name { font-size:13.5px; font-weight:800; color:#0F172A; }
  .cts-hero-n { font-size:10px; color:#94A3B8; font-weight:500; margin-top:2px; }
  .cts-hero-bar-col { flex:1; }
  .cts-bar { height:72px; display:flex; border-radius:6px; overflow:hidden;
    box-shadow:inset 0 1px 2px rgba(0,0,0,.06); }
  .cts-seg { height:100%; display:flex; align-items:center; justify-content:center;
    font-weight:700; color:rgba(255,255,255,.95); white-space:nowrap; overflow:hidden;
    min-width:0; flex-direction:column; gap:1px; }
  .cts-seg .sp { font-size:11px; font-weight:800; }
  .cts-seg .sn { font-size:8px; font-weight:600; opacity:.85; }
  .cts-hero-meta { width:115px; flex-shrink:0; padding-left:18px; text-align:right; }
  .cts-hero-s { font-size:18px; font-weight:900; color:#0F172A; }
  .cts-hero-c { font-size:11px; color:#64748B; font-weight:500; margin-top:3px; }
  .cts-hero-m { font-size:10px; color:#94A3B8; font-weight:600; margin-top:2px; }
  .cts-callout { display:flex; gap:14px; align-items:flex-start; background:#FFFBEB;
    border:1px solid #FDE68A; border-radius:10px; padding:16px 20px; margin-bottom:28px; }
  .cts-callout-icon { width:32px; height:32px; border-radius:8px; background:#FEF3C7;
    display:flex; align-items:center; justify-content:center; font-size:16px; flex-shrink:0; margin-top:1px; }
  .cts-callout-head { font-size:12.5px; font-weight:800; color:#78350F; margin-bottom:4px; }
  .cts-callout-text { font-size:11.5px; color:#92400E; line-height:1.65; }
  .cts-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }
  .cts-card { background:#fff; border-radius:12px; border:1px solid #E2E8F0;
    box-shadow:0 1px 4px rgba(15,23,42,.05); overflow:hidden; }
  .cts-accent { height:4px; }
  .cts-body { padding:18px 18px 16px; }
  .cts-card-head { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:14px; }
  .cts-card-title { font-size:13px; font-weight:800; color:#0F172A; }
  .cts-card-n { font-size:9.5px; color:#94A3B8; font-weight:500; margin-top:2px; }
  .cts-card-cpp { font-size:16px; font-weight:900; }
  .cts-card-mo { font-size:9px; color:#94A3B8; font-weight:600; margin-top:2px; }
  .cts-mini { height:28px; display:flex; border-radius:4px; overflow:hidden;
    margin-bottom:14px; box-shadow:inset 0 1px 2px rgba(0,0,0,.06); }
  .cts-mseg { height:100%; display:flex; align-items:center; justify-content:center;
    font-size:8.5px; font-weight:700; color:rgba(255,255,255,.92);
    white-space:nowrap; overflow:hidden; min-width:0; padding:0 2px; }
  .cts-phase-row { display:flex; align-items:center; padding:3px 0;
    border-top:1px solid #F8FAFC; gap:5px; }
  .cts-phase-name { font-size:9.5px; color:#0F172A; font-weight:700; white-space:nowrap;
    display:flex; align-items:center; gap:4px; width:68px; flex-shrink:0; }
  .cts-phase-dot { width:6px; height:6px; border-radius:2px; flex-shrink:0; }
  .cts-micro-track { flex:1; height:4px; background:#F1F5F9; border-radius:2px; overflow:hidden; }
  .cts-micro-fill { height:100%; border-radius:2px; }
  .cts-phase-pct { width:26px; text-align:right; font-size:9.5px; font-weight:700; color:#334155; }
  .cts-phase-cost { width:34px; text-align:right; font-size:9px; font-weight:600; color:#64748B; }
  .cts-badge-row { margin-top:10px; display:flex; gap:4px; flex-wrap:wrap; }
  .cts-badge { font-size:8.5px; font-weight:700; padding:2px 7px; border-radius:20px; }
  /* P/A/H resolution cards */
  .pah-row { display:flex; gap:16px; margin-bottom:24px; }
  .pah-card { background:#fff; border-radius:14px; border:1px solid #E2E8F0;
    box-shadow:0 1px 6px rgba(15,23,42,.06); overflow:hidden; flex:1; }
  .pah-accent { height:5px; }
  .pah-body { padding:22px 20px 18px; }
  .pah-eyebrow { font-size:9px; font-weight:800; letter-spacing:0.14em;
    text-transform:uppercase; margin-bottom:5px; }
  .pah-pct { font-size:34px; font-weight:900; line-height:1.05; margin-bottom:3px; }
  .pah-label { font-size:12.5px; font-weight:700; color:#0F172A; margin-bottom:2px; }
  .pah-sub { font-size:10.5px; color:#64748B; line-height:1.55; margin-bottom:14px; }
  .pah-cost-row { display:flex; justify-content:space-between; align-items:baseline;
    padding:6px 0; border-top:1px solid #F1F5F9; }
  .pah-cost-label { font-size:10.5px; color:#64748B; font-weight:500; }
  .pah-cost-value { font-size:13px; font-weight:800; }
  .pah-action { background:#F8FAFC; border-radius:8px; padding:10px 12px; margin-top:12px; }
  .pah-action-eyebrow { font-size:8.5px; font-weight:700; text-transform:uppercase;
    letter-spacing:0.1em; color:#94A3B8; margin-bottom:3px; }
  .pah-action-text { font-size:10.5px; color:#334155; font-weight:600; line-height:1.5; }
  .pah-split-bar { height:34px; display:flex; border-radius:6px; overflow:hidden;
    box-shadow:inset 0 1px 2px rgba(0,0,0,.06); margin:0 0 6px; }
  .pah-split-seg { height:100%; display:flex; align-items:center; justify-content:center;
    font-size:10.5px; font-weight:700; color:#fff; flex-direction:column; gap:0; }
  .pah-split-seg .psn { font-size:8.5px; opacity:.85; }
  .pah-split-legend { display:flex; gap:16px; flex-wrap:wrap; margin-top:6px; }
  .pah-split-legend-item { display:flex; align-items:center; gap:5px;
    font-size:10px; color:#475569; font-weight:500; }

  .footer {
    font-size: 0.68rem; color: #94A3B8;
    display: flex; justify-content: space-between; flex-wrap: wrap; gap: 4px;
    padding-top: 8px;
  }

  #MainMenu, footer, header { visibility: hidden; }

  /* ── Responsive (≤768px) ── */
  @media (max-width: 768px) {
    .hero { padding: 16px 20px 14px; }
    .hero-headline { font-size: 1.5rem; }
    .hero-bottom { flex-direction: column; gap: 12px; }
    .hero-meta-row { text-align: left; }
    .hero-meta, .hero-disclaimer { white-space: normal; text-align: left; }
    .hero-agentic { max-width: 100%; }
    .cts-grid { grid-template-columns: 1fr !important; }
    .pah-row { flex-direction: column; }
    .pah-card { flex: none; }
    .it-queue-head { flex-direction: column; gap: 4px; }
    [data-testid="stTabs"] button[role="tab"] p,
    [data-testid="stTabs"] button[role="tab"] span,
    [data-testid="stTabs"] button[role="tab"] div { font-size: 0.85rem !important; }
    .roi-grid { grid-template-columns: 1fr 1fr !important; }
    .bench-grid { grid-template-columns: 1fr !important; }
  }

  /* ── Print / Export PDF ── */
  @media print {
    #MainMenu, footer, header, .stDeployButton { display: none !important; }
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stTabs"] [data-baseweb="tab-list"] { display: none !important; }
    [data-testid="stTabPanel"] { display: block !important; visibility: visible !important; }
    .hero { border-radius: 0; margin: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .block-container { padding: 0 !important; }
    .scard, .seg, .insight, .pah-card, .cts-card { break-inside: avoid; }
    @page { margin: 1.5cm; size: A4 landscape; }
  }
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
    aht_secs = round(kpis.get("avg_handle_time_seconds", total_secs))

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
        # ── top: centred title block ──
        '<div class="hero-top">'
        '<div class="hero-eyebrow">Care Call Cost Analysis</div>'
        '<div class="hero-headline">Cost Intelligence for Care Calls</div>'
        '<div class="hero-subline">Identifying cost levers across the customer journey — '
        'surfacing cost-to-serve drivers and proactive issue-resolution opportunities, '
        'from real call transcripts.</div>'
        '</div>'
        # ── bottom: agentic left · meta+disclaimer right ──
        '<div class="hero-bottom">'
        '<div class="hero-agentic">'
        '<strong>Agentic AI · Built with Claude Haiku 4.5 + LangGraph</strong><br>'
        '6 specialised agents process real transcripts end-to-end — extracting 70+ cost signals, '
        'scoring quality inline, and synthesising recommendations automatically.<br>'
        '<a href="https://telecom-call-intelligence.streamlit.app/" target="_blank" '
        'style="display:inline-block;margin-top:10px;padding:6px 16px;background:rgba(255,255,255,0.15);'
        'border:1px solid rgba(255,255,255,0.35);border-radius:20px;color:#FFFFFF;'
        'font-size:0.72rem;font-weight:700;letter-spacing:0.06em;text-decoration:none;'
        'text-transform:uppercase;">&#9654; View Live Demo</a>'
        '</div>'
        f'<div class="hero-meta-row">'
        f'<div class="hero-meta">{n_calls:,} calls &nbsp;·&nbsp; {run_date} &nbsp;·&nbsp; {provider} &nbsp;·&nbsp; {model}</div>'
        f'<div class="hero-disclaimer">'
        f'HuggingFace talkmap/telecom-conversation-corpus &nbsp;·&nbsp; avg {aht_secs}s (2.5 min) &nbsp;·&nbsp; '
        f'Enterprise calls 600–1,100s — 4–7× longer &nbsp;·&nbsp; $ figures scale with your AHT'
        f'</div>'
        f'</div>'
        '</div>'
        '</div>'
    )
    st.markdown(hero_html, unsafe_allow_html=True)

    # ── PANELS: split left→Tab 1, right→Tab 2 ────────────────────
    _left_panel = (
        '<div style="background:#FFFFFF;border-radius:14px;padding:24px 26px;'
        'box-shadow:0 1px 4px rgba(15,23,42,.08);margin-top:20px;">'
        f'<div style="font-size:0.95rem;font-weight:800;color:#DC2626;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">Insights from {n_calls:,} Calls Analysed</div>'
        f'<div style="font-size:0.75rem;color:#64748B;font-style:italic;margin-bottom:14px;">Cost allocated by where call handle time goes · forecast at {vol:,} calls/month · ${cpp:.2f}/call unit cost · from {n_calls}-call sample</div>'
        '<div style="display:grid;grid-template-columns:1fr 120px 100px;align-items:baseline;padding:9px 0;border-bottom:1px solid #F1F5F9;">'
        '<span style="font-size:0.88rem;color:#0F172A;font-weight:600;">Cost to Serve <span style="color:#94A3B8;font-weight:500;">(P1–P4)</span></span>'
        f'<span style="font-size:0.8rem;color:#64748B;font-weight:600;text-align:center;">{serve_time_pct:.0f}% of AHT</span>'
        f'<span style="font-size:1.1rem;font-weight:800;color:#0F172A;text-align:right;">${serve_cost/1000:.0f}K/mo</span>'
        '</div>'
        '<div style="display:grid;grid-template-columns:1fr 120px 100px;align-items:baseline;padding:9px 0;border-bottom:1px solid #F1F5F9;">'
        '<span style="font-size:0.88rem;color:#0F172A;font-weight:600;">Cost to Sell <span style="color:#94A3B8;font-weight:500;">(P5)</span></span>'
        f'<span style="font-size:0.8rem;color:#64748B;font-weight:600;text-align:center;">{sell_time_pct:.0f}% of AHT</span>'
        f'<span style="font-size:1.1rem;font-weight:800;color:#0F172A;text-align:right;">${sell_cost/1000:.0f}K/mo</span>'
        '</div>'
        '<div style="display:grid;grid-template-columns:1fr 120px 100px;align-items:baseline;padding:9px 0;border-bottom:1px solid #F1F5F9;">'
        '<span style="font-size:0.88rem;color:#0F172A;font-weight:600;">Cost to Retain <span style="color:#94A3B8;font-weight:500;">(cross-cutting)</span></span>'
        f'<span style="font-size:0.8rem;color:#64748B;font-weight:600;text-align:center;">{retain_time_pct:.0f}% of AHT</span>'
        f'<span style="font-size:1.1rem;font-weight:800;color:#0F172A;text-align:right;">${retain_cost/1000:.0f}K/mo</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:baseline;padding-top:12px;margin-top:4px;border-top:2px solid #0F172A;">'
        '<span style="font-size:0.75rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:#64748B;">Total Monthly Cost</span>'
        f'<span style="font-size:1.6rem;font-weight:800;color:#DC2626;">${base/1000:.0f}K</span>'
        '</div>'
        f'<div class="data-footnote">* Dataset avg AHT = {aht_secs}s. '
        f'Enterprise calls typically 600–1,100s — multiply $ figures by your AHT ÷ {aht_secs} '
        f'for a live deployment estimate.</div>'
        '</div>'
    )
    _right_panel = (
        '<div style="background:#FFFFFF;border-radius:14px;padding:24px 26px;'
        'box-shadow:0 1px 4px rgba(15,23,42,.08);margin-top:20px;">'
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
        f'<div class="data-footnote">* Savings % are based on call classification from the dataset. '
        f'Absolute $ scale with your actual AHT and call volume — see dataset note above.</div>'
        '</div>'
    )

    if is_demo:
        st.markdown("""<div class="callout" style="margin-top:14px;">
          <strong>Demo mode.</strong> Run <code>python run_pipeline.py</code> to replace with live results.
        </div>""", unsafe_allow_html=True)

    # ── Print / Export button ─────────────────────────────────────
    st.markdown(
        '<div style="display:flex;justify-content:flex-end;margin-top:12px;">'
        '<button onclick="window.print()" style="'
        'background:#0F172A;color:#FFFFFF;border:none;border-radius:8px;'
        'padding:8px 18px;font-size:0.75rem;font-weight:700;letter-spacing:0.06em;'
        'text-transform:uppercase;cursor:pointer;font-family:Inter,sans-serif;">'
        '&#8595; Export PDF</button></div>',
        unsafe_allow_html=True,
    )

    # ── TOP-LEVEL NARRATIVE TABS ────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["Cost to Serve", "Automation Strategy", "QA & Pipeline Health"])

    # ════════════════════════════════════════════════════════════════
    # TAB 1 — COST TO SERVE
    # ════════════════════════════════════════════════════════════════
    with tab1:
        st.markdown(_left_panel, unsafe_allow_html=True)

        # ── 1 — THE EVIDENCE ──────────────────────────────────────
        _sec("1 — The Evidence: What the Transcripts Reveal")

        col_issue, col_phase = st.columns([4, 6])

        with col_issue:
            st.markdown(
                "<div style='font-size:0.8rem;font-weight:700;color:#334155;margin-bottom:10px;'>"
                "What customers are calling about</div>",
                unsafe_allow_html=True,
            )
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
                st.plotly_chart(chart_issue_mix(ic_clean, n_calls), use_container_width=True, key="issue_mix")

        with col_phase:
            st.markdown(
                "<div style='font-size:0.8rem;font-weight:700;color:#334155;margin-bottom:10px;'>"
                "Where agent time goes inside every call</div>",
                unsafe_allow_html=True,
            )
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
                st.plotly_chart(chart_phases(phases), use_container_width=True, key="phase_time")

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

        # ── PHASE COST INTELLIGENCE ────────────────────────────────
        _sec("Phase Cost Intelligence — Call Anatomy by Type")
        _dd_pct  = 27 + 19
        _dd_cost = round(cpp * _dd_pct / 100, 2)

        phase_html = (
            f'<div style="padding:4px 0 20px;">'
            f'<div class="cts-legend">'
            f'<div class="cts-legend-item"><div class="cts-swatch" style="background:#CBD5E1"></div><span class="cts-swatch-label">Welcome &amp; Closing — Overhead</span></div>'
            f'<div class="cts-legend-item"><div class="cts-swatch" style="background:#F59E0B"></div><span class="cts-swatch-label">Discovery — Customer explains</span></div>'
            f'<div class="cts-legend-item"><div class="cts-swatch" style="background:#F97316"></div><span class="cts-swatch-label">Diagnosis — Agent investigates</span></div>'
            f'<div class="cts-legend-item"><div class="cts-swatch" style="background:#10B981"></div><span class="cts-swatch-label">Resolution — Value delivery</span></div>'
            f'<div class="cts-legend-item"><div class="cts-swatch" style="background:#EF4444"></div><span class="cts-swatch-label">Hold — Dead time</span></div>'
            f'<div class="cts-legend-item"><div class="cts-swatch" style="background:#3B82F6"></div><span class="cts-swatch-label">Upsell — Revenue</span></div>'
            f'</div>'
            f'<div class="cts-eyebrow">All Calls — Average across {n_calls:,} transcripts</div>'
            f'<div class="cts-hero-wrap"><div class="cts-hero-row">'
            f'<div class="cts-hero-label"><div class="cts-hero-name">All Calls</div><div class="cts-hero-n">n = {n_calls} · avg</div></div>'
            f'<div class="cts-hero-bar-col"><div class="cts-bar">'
            f'<div class="cts-seg" style="background:#CBD5E1;width:17.6%"><span class="sp">18%</span><span class="sn">Welcome</span></div>'
            f'<div class="cts-seg" style="background:#F59E0B;width:27.1%"><span class="sp">27%</span><span class="sn">Discovery</span></div>'
            f'<div class="cts-seg" style="background:#F97316;width:19.4%"><span class="sp">19%</span><span class="sn">Diagnosis</span></div>'
            f'<div class="cts-seg" style="background:#10B981;width:22.9%"><span class="sp">23%</span><span class="sn">Resolution</span></div>'
            f'<div class="cts-seg" style="background:#EF4444;width:0.9%" title="Hold 1%"></div>'
            f'<div class="cts-seg" style="background:#3B82F6;width:9.7%"><span class="sp">10%</span><span class="sn">Upsell</span></div>'
            f'<div class="cts-seg" style="background:#CBD5E1;opacity:0.55;width:14%"><span class="sp">14%</span><span class="sn">Closing</span></div>'
            f'</div></div>'
            f'<div class="cts-hero-meta"><div class="cts-hero-s">{aht_secs}s</div>'
            f'<div class="cts-hero-c">${cpp:.2f} / call</div>'
            f'<div class="cts-hero-m">${base/1000:.0f}K / month</div></div>'
            f'</div></div>'
            f'<div class="cts-callout"><div class="cts-callout-icon">⚡</div><div>'
            f'<div class="cts-callout-head">Discovery + Diagnosis = {_dd_pct}% of every call — ${_dd_cost:.2f} of the ${cpp:.2f} unit cost</div>'
            f'<div class="cts-callout-text">This is the highest-leverage cost reduction target in the portfolio. '
            f'<b>Proactive outreach eliminates Discovery entirely</b> for preventable contacts — the customer never calls because the issue is resolved before it forms. '
            f'<b>Agentic AI compresses Diagnosis to near-zero</b> for deterministic issues — the agent already knows the answer before the customer finishes explaining. '
            f'Together these two interventions address the majority of care cost.</div>'
            f'</div></div>'
            f'<div class="cts-eyebrow" style="margin-bottom:16px;">Breakdown by Call Type</div>'
            f'<div class="cts-grid">'

            # TECHNICAL
            f'<div class="cts-card"><div class="cts-accent" style="background:linear-gradient(90deg,#F97316,#F59E0B)"></div><div class="cts-body">'
            f'<div class="cts-card-head"><div><div class="cts-card-title">Technical</div><div class="cts-card-n">n=29 · 37% of calls · 37,180/mo</div></div>'
            f'<div style="text-align:right"><div class="cts-card-cpp" style="color:#0F172A">$5.97</div><div class="cts-card-mo">$222K / month</div></div></div>'
            f'<div class="cts-mini"><div class="cts-mseg" style="background:#CBD5E1;width:17%">17%</div><div class="cts-mseg" style="background:#F59E0B;width:28%">Disc 28%</div><div class="cts-mseg" style="background:#F97316;width:24%">Diag 24%</div><div class="cts-mseg" style="background:#10B981;width:18%">18%</div><div class="cts-mseg" style="background:#EF4444;width:1%"></div><div class="cts-mseg" style="background:#3B82F6;width:2%"></div><div class="cts-mseg" style="background:#CBD5E1;opacity:.55;width:14%">14%</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#CBD5E1"></div>Welcome</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#CBD5E1;width:17%"></div></div><div class="cts-phase-pct">17%</div><div class="cts-phase-cost">$1.03</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#F59E0B"></div>Discovery</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#F59E0B;width:28%"></div></div><div class="cts-phase-pct">28%</div><div class="cts-phase-cost">$1.66</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#F97316"></div>Diagnosis</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#F97316;width:24%"></div></div><div class="cts-phase-pct" style="color:#DC2626">24%</div><div class="cts-phase-cost" style="color:#DC2626">$1.44</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#10B981"></div>Resolution</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#10B981;width:18%"></div></div><div class="cts-phase-pct">18%</div><div class="cts-phase-cost">$1.06</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#3B82F6"></div>Upsell</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#3B82F6;width:2%"></div></div><div class="cts-phase-pct">2%</div><div class="cts-phase-cost">$0.10</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#CBD5E1;opacity:.6"></div>Closing</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#CBD5E1;width:14%"></div></div><div class="cts-phase-pct">14%</div><div class="cts-phase-cost">$0.86</div></div>'
            f'<div class="cts-badge-row"><span class="cts-badge" style="background:#FEF3C7;color:#92400E">Diagnosis overrun</span><span class="cts-badge" style="background:#F5F3FF;color:#5B21B6">28% Preventable</span></div>'
            f'</div></div>'

            # DEVICE
            f'<div class="cts-card"><div class="cts-accent" style="background:linear-gradient(90deg,#F97316,#EF4444)"></div><div class="cts-body">'
            f'<div class="cts-card-head"><div><div class="cts-card-title">Device</div><div class="cts-card-n">n=19 · 24% of calls · 24,360/mo</div></div>'
            f'<div style="text-align:right"><div class="cts-card-cpp" style="color:#DC2626">$6.31</div><div class="cts-card-mo" style="color:#DC2626">$154K / month ↑ highest</div></div></div>'
            f'<div class="cts-mini"><div class="cts-mseg" style="background:#CBD5E1;width:15%">15%</div><div class="cts-mseg" style="background:#F59E0B;width:27%">Disc 27%</div><div class="cts-mseg" style="background:#F97316;width:27%">Diag 27%</div><div class="cts-mseg" style="background:#10B981;width:20%">20%</div><div class="cts-mseg" style="background:#3B82F6;width:4%"></div><div class="cts-mseg" style="background:#CBD5E1;opacity:.55;width:13%">13%</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#CBD5E1"></div>Welcome</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#CBD5E1;width:15%"></div></div><div class="cts-phase-pct">15%</div><div class="cts-phase-cost">$0.94</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#F59E0B"></div>Discovery</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#F59E0B;width:27%"></div></div><div class="cts-phase-pct">27%</div><div class="cts-phase-cost">$1.61</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#F97316"></div>Diagnosis</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#F97316;width:27%"></div></div><div class="cts-phase-pct" style="color:#DC2626">27%</div><div class="cts-phase-cost" style="color:#DC2626">$1.64</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#10B981"></div>Resolution</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#10B981;width:20%"></div></div><div class="cts-phase-pct">20%</div><div class="cts-phase-cost">$1.22</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#3B82F6"></div>Upsell</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#3B82F6;width:4%"></div></div><div class="cts-phase-pct">4%</div><div class="cts-phase-cost">$0.23</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#CBD5E1;opacity:.6"></div>Closing</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#CBD5E1;width:13%"></div></div><div class="cts-phase-pct">13%</div><div class="cts-phase-cost">$0.78</div></div>'
            f'<div class="cts-badge-row"><span class="cts-badge" style="background:#FEF2F2;color:#991B1B">Highest cost per call</span><span class="cts-badge" style="background:#F5F3FF;color:#5B21B6">63% automatable</span></div>'
            f'</div></div>'

            # INFORMATION
            f'<div class="cts-card"><div class="cts-accent" style="background:linear-gradient(90deg,#10B981,#3B82F6)"></div><div class="cts-body">'
            f'<div class="cts-card-head"><div><div class="cts-card-title">Information</div><div class="cts-card-n">n=14 · 18% of calls · 17,950/mo</div></div>'
            f'<div style="text-align:right"><div class="cts-card-cpp" style="color:#059669">$5.60</div><div class="cts-card-mo">$101K / month</div></div></div>'
            f'<div class="cts-mini"><div class="cts-mseg" style="background:#CBD5E1;width:16%">16%</div><div class="cts-mseg" style="background:#F59E0B;width:30%">Disc 30%</div><div class="cts-mseg" style="background:#F97316;width:10%">10%</div><div class="cts-mseg" style="background:#10B981;width:36%">Res 36%</div><div class="cts-mseg" style="background:#3B82F6;width:27%">Ups 27%</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#CBD5E1"></div>Welcome</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#CBD5E1;width:16%"></div></div><div class="cts-phase-pct">16%</div><div class="cts-phase-cost">$0.98</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#F59E0B"></div>Discovery</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#F59E0B;width:30%"></div></div><div class="cts-phase-pct">30%</div><div class="cts-phase-cost">$1.77</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#F97316"></div>Diagnosis</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#F97316;width:10%"></div></div><div class="cts-phase-pct" style="color:#059669">10%</div><div class="cts-phase-cost" style="color:#059669">$0.58</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#10B981"></div>Resolution</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#10B981;width:36%"></div></div><div class="cts-phase-pct" style="color:#059669">36%</div><div class="cts-phase-cost">$2.14</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#3B82F6"></div>Upsell</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#3B82F6;width:27%"></div></div><div class="cts-phase-pct" style="color:#2563EB">27%</div><div class="cts-phase-cost" style="color:#2563EB">$1.64</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#CBD5E1;opacity:.6"></div>Closing</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#CBD5E1;width:11%"></div></div><div class="cts-phase-pct">11%</div><div class="cts-phase-cost">$0.65</div></div>'
            f'<div class="cts-badge-row"><span class="cts-badge" style="background:#ECFDF5;color:#065F46">Low diagnosis · fast resolution</span><span class="cts-badge" style="background:#EFF6FF;color:#1E40AF">Strong upsell yield</span></div>'
            f'</div></div>'

            # BILLING
            f'<div class="cts-card"><div class="cts-accent" style="background:linear-gradient(90deg,#10B981,#7C3AED)"></div><div class="cts-body">'
            f'<div class="cts-card-head"><div><div class="cts-card-title">Billing</div><div class="cts-card-n">n=5 · 6% of calls · 6,410/mo</div></div>'
            f'<div style="text-align:right"><div class="cts-card-cpp" style="color:#0F172A">$5.92</div><div class="cts-card-mo">$38K / month</div></div></div>'
            f'<div class="cts-mini"><div class="cts-mseg" style="background:#CBD5E1;width:14%">14%</div><div class="cts-mseg" style="background:#F59E0B;width:24%">24%</div><div class="cts-mseg" style="background:#F97316;width:15%">15%</div><div class="cts-mseg" style="background:#10B981;width:29%">Res 29%</div><div class="cts-mseg" style="background:#EF4444;width:2%"></div><div class="cts-mseg" style="background:#CBD5E1;opacity:.55;width:20%">20%</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#CBD5E1"></div>Welcome</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#CBD5E1;width:14%"></div></div><div class="cts-phase-pct">14%</div><div class="cts-phase-cost">$0.83</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#F59E0B"></div>Discovery</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#F59E0B;width:24%"></div></div><div class="cts-phase-pct">24%</div><div class="cts-phase-cost">$1.44</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#F97316"></div>Diagnosis</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#F97316;width:15%"></div></div><div class="cts-phase-pct">15%</div><div class="cts-phase-cost">$0.91</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#10B981"></div>Resolution</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#10B981;width:29%"></div></div><div class="cts-phase-pct" style="color:#059669">29%</div><div class="cts-phase-cost">$1.72</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#CBD5E1;opacity:.6"></div>Closing</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#CBD5E1;width:20%"></div></div><div class="cts-phase-pct">20%</div><div class="cts-phase-cost">$1.21</div></div>'
            f'<div class="cts-badge-row"><span class="cts-badge" style="background:#ECFDF5;color:#065F46">Below-avg diagnosis</span><span class="cts-badge" style="background:#F5F3FF;color:#5B21B6">Agentic AI candidate</span></div>'
            f'</div></div>'

            # PLAN
            f'<div class="cts-card"><div class="cts-accent" style="background:linear-gradient(90deg,#3B82F6,#7C3AED)"></div><div class="cts-body">'
            f'<div class="cts-card-head"><div><div class="cts-card-title">Plan</div><div class="cts-card-n">n=5 · 6% of calls · 6,410/mo</div></div>'
            f'<div style="text-align:right"><div class="cts-card-cpp" style="color:#DC2626">$7.26</div><div class="cts-card-mo" style="color:#DC2626">$47K / month ↑ longest</div></div></div>'
            f'<div class="cts-mini"><div class="cts-mseg" style="background:#CBD5E1;width:23%">23%</div><div class="cts-mseg" style="background:#F59E0B;width:17%">17%</div><div class="cts-mseg" style="background:#F97316;width:10%">10%</div><div class="cts-mseg" style="background:#10B981;width:36%">Res 36%</div><div class="cts-mseg" style="background:#3B82F6;width:29%">Ups 29%</div><div class="cts-mseg" style="background:#CBD5E1;opacity:.55;width:19%">19%</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#CBD5E1"></div>Welcome</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#CBD5E1;width:23%"></div></div><div class="cts-phase-pct">23%</div><div class="cts-phase-cost">$1.36</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#F59E0B"></div>Discovery</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#F59E0B;width:17%"></div></div><div class="cts-phase-pct">17%</div><div class="cts-phase-cost">$1.05</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#F97316"></div>Diagnosis</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#F97316;width:10%"></div></div><div class="cts-phase-pct" style="color:#059669">10%</div><div class="cts-phase-cost" style="color:#059669">$0.60</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#10B981"></div>Resolution</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#10B981;width:36%"></div></div><div class="cts-phase-pct" style="color:#059669">36%</div><div class="cts-phase-cost">$2.16</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#3B82F6"></div>Upsell</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#3B82F6;width:29%"></div></div><div class="cts-phase-pct" style="color:#2563EB">29%</div><div class="cts-phase-cost" style="color:#2563EB">$1.74</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#CBD5E1;opacity:.6"></div>Closing</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#CBD5E1;width:19%"></div></div><div class="cts-phase-pct">19%</div><div class="cts-phase-cost">$1.12</div></div>'
            f'<div class="cts-badge-row"><span class="cts-badge" style="background:#EFF6FF;color:#1E40AF">High upsell revenue phase</span><span class="cts-badge" style="background:#FEF3C7;color:#92400E">Complex resolution drives cost</span></div>'
            f'</div></div>'

            # ACCOUNT
            f'<div class="cts-card"><div class="cts-accent" style="background:linear-gradient(90deg,#94A3B8,#64748B)"></div><div class="cts-body">'
            f'<div class="cts-card-head"><div><div class="cts-card-title">Account</div><div class="cts-card-n">n=4 · 5% of calls · 5,130/mo</div></div>'
            f'<div style="text-align:right"><div class="cts-card-cpp" style="color:#059669">$4.83</div><div class="cts-card-mo" style="color:#059669">$25K / month ↓ lowest</div></div></div>'
            f'<div class="cts-mini"><div class="cts-mseg" style="background:#CBD5E1;width:40%">Welcome 40%</div><div class="cts-mseg" style="background:#F59E0B;width:24%">24%</div><div class="cts-mseg" style="background:#F97316;width:3%"></div><div class="cts-mseg" style="background:#10B981;width:11%">11%</div><div class="cts-mseg" style="background:#EF4444;width:4%"></div><div class="cts-mseg" style="background:#CBD5E1;opacity:.55;width:11%">11%</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#CBD5E1"></div>Welcome</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#CBD5E1;width:40%"></div></div><div class="cts-phase-pct" style="color:#D97706">40%</div><div class="cts-phase-cost" style="color:#D97706">$2.40</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#F59E0B"></div>Discovery</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#F59E0B;width:24%"></div></div><div class="cts-phase-pct">24%</div><div class="cts-phase-cost">$1.43</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#F97316"></div>Diagnosis</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#F97316;width:3%"></div></div><div class="cts-phase-pct" style="color:#059669">3%</div><div class="cts-phase-cost" style="color:#059669">$0.21</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#10B981"></div>Resolution</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#10B981;width:11%"></div></div><div class="cts-phase-pct">11%</div><div class="cts-phase-cost">$0.66</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#EF4444"></div>Hold</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#EF4444;width:4%"></div></div><div class="cts-phase-pct">4%</div><div class="cts-phase-cost">$0.22</div></div>'
            f'<div class="cts-phase-row"><div class="cts-phase-name"><div class="cts-phase-dot" style="background:#CBD5E1;opacity:.6"></div>Closing</div><div class="cts-micro-track"><div class="cts-micro-fill" style="background:#CBD5E1;width:11%"></div></div><div class="cts-phase-pct">11%</div><div class="cts-phase-cost">$0.66</div></div>'
            f'<div class="cts-badge-row"><span class="cts-badge" style="background:#ECFDF5;color:#065F46">Lowest cost per call</span><span class="cts-badge" style="background:#F8FAFC;color:#475569">Self-serve candidate</span></div>'
            f'</div></div>'

            f'</div>'  # /cts-grid
            f'<div class="data-footnote" style="margin-top:16px;">* Phase % are averages from {n_calls}-transcript dataset. '
            f'Call-type figures are directional given small sub-sample sizes (n=4–29). '
            f'AHT = {aht_secs}s dataset avg — see dataset note above for enterprise scale factors.</div>'
            f'</div>'
        )
        st.markdown(phase_html, unsafe_allow_html=True)

        # ── 2 — PHASE DRILL-DOWN ──────────────────────────────────────
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
            _dd_tabs = st.tabs(dd_phases)
            for _dd_tab, _dd_phase in zip(_dd_tabs, dd_phases):
                with _dd_tab:
                    rows = drilldown[_dd_phase]
                    color, _ptype = PHASE_META.get(_dd_phase, ("#94A3B8", ""))
                    top = rows[0]
                    top_intent = top["intent"].replace("_", " ").title()
                    stall_note = (
                        f", {top['stall_pct']:.0f}% flagged as agent stall"
                        if top["stall_pct"] > 0 else ""
                    )
                    st.markdown(
                        f"<div style='font-size:0.85rem;color:#475569;margin-bottom:8px;'>"
                        f"<strong style='color:{color};'>{top_intent}</strong> calls take longest in "
                        f"<strong style='color:{color};'>{_dd_phase}</strong> — averaging {top['avg_seconds']:.0f}s ({top['calls']} calls{stall_note}).</div>",
                        unsafe_allow_html=True,
                    )
                    st.plotly_chart(chart_drilldown_intents(rows, color), use_container_width=True, key=f"dd_{_dd_phase}")
        else:
            st.markdown('''<div class="callout" style="margin-top:4px;">
              Phase drill-down requires <code>phase_drilldown</code> in <code>summary.json</code> —
              run <code>python merge_outputs.py</code> to regenerate.
            </div>''', unsafe_allow_html=True)


    with tab2:
        st.markdown(_right_panel, unsafe_allow_html=True)

        # ── P/A/H RESOLUTION STRATEGY ─────────────────────────────
        _sec("Resolution Strategy — Proactive · Agentic · Human")
        _prev_cost = round(prevent_pct / 100 * base)
        _auto_cost = round(automate_pct / 100 * base)
        _hum_cost  = round(human_pct / 100 * base)
        _prev_save = cl.get("proactive_care_savings_usd", 0)
        _ss_save   = cl.get("self_serve_savings_usd", 0)
        _ag_save   = cl.get("agentic_ai_savings_usd", 0)
        _auto_save = _ss_save + _ag_save

        pah_html = (
            f'<div style="padding:4px 0 20px;">'
            f'<div style="font-size:0.87rem;color:#334155;line-height:1.7;margin-bottom:20px;">'
            f'Every care call falls into one of three resolution strategies. '
            f'Targeting the right strategy determines whether cost is <strong>eliminated</strong>, '
            f'<strong>automated</strong>, or <strong>optimised</strong>.'
            f'</div>'
            f'<div class="pah-row">'

            # PREVENT
            f'<div class="pah-card"><div class="pah-accent" style="background:linear-gradient(90deg,#10B981,#059669)"></div>'
            f'<div class="pah-body">'
            f'<div class="pah-eyebrow" style="color:#059669">Prevent</div>'
            f'<div class="pah-pct" style="color:#059669">{prevent_pct:.0f}%</div>'
            f'<div class="pah-label">Proactive Resolution</div>'
            f'<div class="pah-sub">Customer calls because we didn\'t reach them first. Eliminate the contact entirely before it forms.</div>'
            f'<div class="pah-cost-row"><span class="pah-cost-label">Addressable cost / mo</span><span class="pah-cost-value" style="color:#0F172A">${_prev_cost/1000:.0f}K</span></div>'
            f'<div class="pah-cost-row"><span class="pah-cost-label">Net saving opportunity</span><span class="pah-cost-value" style="color:#059669">${_prev_save/1000:.0f}K / mo</span></div>'
            f'<div class="pah-action"><div class="pah-action-eyebrow">Recommended Action</div>'
            f'<div class="pah-action-text">Proactive outreach — push notifications, pre-emptive SMS, bill alerts — before the customer needs to call</div></div>'
            f'</div></div>'

            # AUTOMATE
            f'<div class="pah-card"><div class="pah-accent" style="background:linear-gradient(90deg,#3B82F6,#7C3AED)"></div>'
            f'<div class="pah-body">'
            f'<div class="pah-eyebrow" style="color:#2563EB">Automate</div>'
            f'<div class="pah-pct" style="color:#2563EB">{automate_pct:.0f}%</div>'
            f'<div class="pah-label">AI Agent Resolution</div>'
            f'<div class="pah-sub">Customer calls with a deterministic issue. Deploy AI to resolve without a live human agent.</div>'
            f'<div class="pah-cost-row"><span class="pah-cost-label">Self-serve ({selfserve_pct:.0f}%) addressable</span><span class="pah-cost-value" style="color:#0F172A">${round(selfserve_pct/100*base)/1000:.0f}K / mo</span></div>'
            f'<div class="pah-cost-row"><span class="pah-cost-label">Agentic AI ({agentic_pct:.1f}%) addressable</span><span class="pah-cost-value" style="color:#0F172A">${round(agentic_pct/100*base)/1000:.0f}K / mo</span></div>'
            f'<div class="pah-cost-row"><span class="pah-cost-label">Net saving opportunity</span><span class="pah-cost-value" style="color:#2563EB">${_auto_save/1000:.0f}K / mo</span></div>'
            f'<div class="pah-action"><div class="pah-action-eyebrow">Recommended Action</div>'
            f'<div class="pah-action-text">Upgrade IVR to intent-aware AI, self-serve chatbot for top issue types, agentic routing for complex deterministic flows</div></div>'
            f'</div></div>'

            # HUMAN
            f'<div class="pah-card"><div class="pah-accent" style="background:linear-gradient(90deg,#94A3B8,#64748B)"></div>'
            f'<div class="pah-body">'
            f'<div class="pah-eyebrow" style="color:#64748B">Human Required</div>'
            f'<div class="pah-pct" style="color:#475569">{human_pct:.0f}%</div>'
            f'<div class="pah-label">Optimise for Efficiency</div>'
            f'<div class="pah-sub">Complex, empathy-critical, or compliance-governed calls. Human is the right channel.</div>'
            f'<div class="pah-cost-row"><span class="pah-cost-label">Irreducible baseline cost</span><span class="pah-cost-value" style="color:#0F172A">${_hum_cost/1000:.0f}K / mo</span></div>'
            f'<div class="pah-cost-row"><span class="pah-cost-label">Focus lever</span><span class="pah-cost-value" style="color:#475569">AHT reduction</span></div>'
            f'<div class="pah-action"><div class="pah-action-eyebrow">Recommended Action</div>'
            f'<div class="pah-action-text">Skills-based routing, real-time agent assist, Diagnosis-phase tooling, FCR improvement programmes</div></div>'
            f'</div></div>'

            f'</div>'  # /pah-row

            # Split bar
            f'<div class="cts-eyebrow">Portfolio split — {n_calls:,} calls analysed</div>'
            f'<div class="pah-split-bar">'
            f'<div class="pah-split-seg" style="background:#10B981;width:{prevent_pct:.1f}%"><span>{prevent_pct:.0f}%</span><span class="psn">Prevent</span></div>'
            f'<div class="pah-split-seg" style="background:#3B82F6;width:{selfserve_pct:.1f}%"><span>{selfserve_pct:.0f}%</span><span class="psn">Self-serve</span></div>'
            f'<div class="pah-split-seg" style="background:#7C3AED;width:{agentic_pct:.1f}%" title="Agentic {agentic_pct:.1f}%"></div>'
            f'<div class="pah-split-seg" style="background:#94A3B8;width:{human_pct:.1f}%"><span>{human_pct:.0f}%</span><span class="psn">Human</span></div>'
            f'</div>'
            f'<div class="pah-split-legend">'
            f'<div class="pah-split-legend-item"><div class="cts-swatch" style="background:#10B981"></div>Prevent {prevent_pct:.0f}% — ${_prev_save/1000:.0f}K/mo saveable</div>'
            f'<div class="pah-split-legend-item"><div class="cts-swatch" style="background:#3B82F6"></div>Self-serve {selfserve_pct:.0f}% — ${_ss_save/1000:.0f}K/mo saveable</div>'
            f'<div class="pah-split-legend-item"><div class="cts-swatch" style="background:#7C3AED"></div>Agentic {agentic_pct:.1f}% — ${_ag_save/1000:.0f}K/mo saveable</div>'
            f'<div class="pah-split-legend-item"><div class="cts-swatch" style="background:#94A3B8"></div>Human required {human_pct:.0f}% — ${_hum_cost/1000:.0f}K/mo baseline</div>'
            f'</div>'
            f'<div class="data-footnote" style="margin-top:16px;">* Segment classifications derived from call-level extraction across {n_calls} transcripts. '
            f'Dollar figures based on dataset avg AHT of {aht_secs}s — scale proportionally for enterprise deployments. '
            f'See dataset note above.</div>'
            f'</div>'
        )
        st.markdown(pah_html, unsafe_allow_html=True)

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
        st.plotly_chart(chart_segment_bar(seg_bar_data), use_container_width=True, key="segment_bar")

        st.markdown(f"""
        <div class="callout green" style="margin-top:6px;">
          <strong>Business case from {n_calls:,} calls:</strong> &nbsp;
          {total_auto:.0f}% of your contact volume — {round(vol * total_auto / 100):,} calls/month
          at scale — is addressable through autonomous AI.
          At ${cpp:.2f} per call that is
          <strong>${opp/1000:.0f}K/month · ${annual/1e6:.1f}M/year</strong>
          in recoverable cost, before any improvement in customer experience is counted.
        </div>
        <div class="data-footnote" style="margin-top:8px;">
          * Dollar figures derived from dataset avg AHT of {aht_secs}s ({aht_secs/60:.1f} min).
          Enterprise care calls typically run 600–1,100s — cost opportunity scales proportionally
          with your actual handle time. Phase classifications (Prevent / Automate / Human) are
          independent of AHT and remain valid at any call length.
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
                f"Validate against your live IVR taxonomy before build. "
                f"* Saving figures based on dataset avg AHT of {aht_secs}s — "
                f"scale by your actual AHT ÷ {aht_secs} for a live deployment estimate.</p>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="callout">Run the pipeline to populate the agent roadmap.</div>',
                        unsafe_allow_html=True)

        # ═══════════════════════════════════════════════════════════════
        # ROI CALCULATOR
        # ═══════════════════════════════════════════════════════════════
        _sec("ROI Calculator — Your Numbers")
        st.markdown(
            "<div style='font-size:0.88rem;color:#64748B;line-height:1.65;margin-bottom:18px;'>"
            "Plug in your actual contact centre volume and cost — the pipeline's classification "
            "rates apply automatically to project your saving opportunity.</div>",
            unsafe_allow_html=True,
        )
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            roi_vol = st.slider("Monthly call volume", 10_000, 2_000_000, vol, step=10_000, format="%d")
        with rc2:
            roi_cpp = st.slider("Cost per call ($)", 3.0, 20.0, float(cpp), step=0.25, format="$%.2f")
        with rc3:
            roi_defl = st.slider(
                "Deflection rate achieved (%)", 10, 90,
                int(round(min(total_auto * 0.8, 80))), step=5,
            )
        roi_base     = roi_vol * roi_cpp
        roi_deflected = roi_vol * roi_defl / 100
        roi_saving   = roi_deflected * roi_cpp
        roi_annual   = roi_saving * 12
        roi_pct      = roi_saving / roi_base * 100 if roi_base else 0
        st.markdown(
            f'<div class="roi-grid" style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-top:20px;">'
            f'<div style="background:#FFFFFF;border-radius:14px;padding:22px 20px;'
            f'box-shadow:0 1px 4px rgba(15,23,42,.08);border-top:3px solid #0F172A;">'
            f'<div style="font-size:0.62rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#94A3B8;margin-bottom:8px;">Baseline Monthly Cost</div>'
            f'<div style="font-size:2rem;font-weight:900;color:#0F172A;letter-spacing:-0.03em;">${roi_base/1000:.0f}K</div>'
            f'<div style="font-size:0.75rem;color:#94A3B8;margin-top:4px;">{roi_vol:,} calls × ${roi_cpp:.2f}</div>'
            f'</div>'
            f'<div style="background:#FFFFFF;border-radius:14px;padding:22px 20px;'
            f'box-shadow:0 1px 4px rgba(15,23,42,.08);border-top:3px solid #7C3AED;">'
            f'<div style="font-size:0.62rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#94A3B8;margin-bottom:8px;">Calls Deflected / Month</div>'
            f'<div style="font-size:2rem;font-weight:900;color:#7C3AED;letter-spacing:-0.03em;">{roi_deflected:,.0f}</div>'
            f'<div style="font-size:0.75rem;color:#94A3B8;margin-top:4px;">{roi_defl}% of {roi_vol:,}</div>'
            f'</div>'
            f'<div style="background:#FFFFFF;border-radius:14px;padding:22px 20px;'
            f'box-shadow:0 1px 4px rgba(15,23,42,.08);border-top:3px solid #059669;">'
            f'<div style="font-size:0.62rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#94A3B8;margin-bottom:8px;">Monthly Saving</div>'
            f'<div style="font-size:2rem;font-weight:900;color:#059669;letter-spacing:-0.03em;">${roi_saving/1000:.0f}K</div>'
            f'<div style="font-size:0.75rem;color:#94A3B8;margin-top:4px;">{roi_pct:.0f}% of baseline</div>'
            f'</div>'
            f'<div style="background:#FFFFFF;border-radius:14px;padding:22px 20px;'
            f'box-shadow:0 1px 4px rgba(15,23,42,.08);border-top:3px solid #CD040B;">'
            f'<div style="font-size:0.62rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#94A3B8;margin-bottom:8px;">Annual Recovery</div>'
            f'<div style="font-size:2rem;font-weight:900;color:#CD040B;letter-spacing:-0.03em;">${roi_annual/1e6:.1f}M</div>'
            f'<div style="font-size:0.75rem;color:#94A3B8;margin-top:4px;">at {roi_defl}% deflection rate</div>'
            f'</div>'
            f'</div>'
            f'<div class="data-footnote" style="margin-top:10px;">'
            f'Deflection rate = share of contacts resolved without a live human agent. '
            f'Industry benchmark: 30–50% IVR/digital; 60–70% with full agentic AI. '
            f'This dataset classification ({total_auto:.0f}% addressable) is the theoretical ceiling. '
            f'Default is set at 80% of that ceiling as a realistic first-year target.'
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
                    f'<div class="data-footnote" style="margin-top:10px;">'
                    f'* Monthly $ impact based on dataset avg AHT of {aht_secs}s. '
                    f'At enterprise AHT of 600–1,100s these figures scale 4–7×. '
                    f'Segment classifications (Prevent / Automate / Human) are AHT-independent.'
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

    # ════════════════════════════════════════════════════════════════
    # TAB 3 — QA & PIPELINE HEALTH
    # ════════════════════════════════════════════════════════════════
    with tab3:
        tu = data.get("token_usage", {})

        # ── Pipeline run summary ──────────────────────────────────
        _sec("Pipeline Run — Model & Inference")
        total_tokens  = tu.get("total_tokens", 0)
        total_cost    = tu.get("total_cost_usd", 0)
        avg_tokens    = tu.get("avg_total_tokens_per_call", 0)
        avg_cost_call = tu.get("avg_cost_per_call_usd", 0)
        calls_w_usage = tu.get("calls_with_usage", n_calls)
        prompt_tok    = tu.get("total_prompt_tokens", 0)
        completion_tok = tu.get("total_completion_tokens", 0)

        p1, p2, p3, p4 = st.columns(4)
        pipe_cards = [
            (p1, "Calls Processed",    f"{calls_w_usage:,}",         "#0F172A",  f"of {n_calls:,} total"),
            (p2, "Total Tokens Used",  f"{total_tokens/1000:.0f}K",  "#7C3AED",  f"{avg_tokens:,.0f} avg / call"),
            (p3, "Total Inference Cost", f"${total_cost:.3f}",       "#059669",  f"${avg_cost_call*100:.3f}¢ / call"),
            (p4, "Model",              meta.get("model", "—")[:22],  "#0F172A",  meta.get("inference_provider", "")),
        ]
        for col, label, val, color, note in pipe_cards:
            with col:
                st.markdown(
                    f'<div class="scard" style="border-top:3px solid {color};">'
                    f'<div class="scard-label">{label}</div>'
                    f'<div class="scard-val" style="color:{color};font-size:1.8rem;">{val}</div>'
                    f'<div class="scard-note">{note}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        if prompt_tok and completion_tok:
            tok_total = prompt_tok + completion_tok or 1
            prompt_pct  = prompt_tok  / tok_total * 100
            compl_pct   = completion_tok / tok_total * 100
            st.markdown(
                f'<div style="background:#FFFFFF;border-radius:14px;padding:22px 26px;'
                f'box-shadow:0 1px 4px rgba(15,23,42,.08);margin-top:18px;">'
                f'<div style="font-size:0.72rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#94A3B8;margin-bottom:14px;">Token Split — Prompt vs. Completion</div>'
                f'<div style="display:flex;height:36px;border-radius:8px;overflow:hidden;margin-bottom:12px;">'
                f'<div style="background:#7C3AED;width:{prompt_pct:.1f}%;display:flex;align-items:center;justify-content:center;color:#fff;font-size:0.8rem;font-weight:700;">'
                f'Prompt {prompt_pct:.0f}%</div>'
                f'<div style="background:#A78BFA;width:{compl_pct:.1f}%;display:flex;align-items:center;justify-content:center;color:#fff;font-size:0.8rem;font-weight:700;">'
                f'Completion {compl_pct:.0f}%</div>'
                f'</div>'
                f'<div style="display:flex;gap:24px;font-size:0.78rem;color:#64748B;font-weight:600;">'
                f'<span>Prompt: <strong style="color:#7C3AED;">{prompt_tok:,} tokens</strong></span>'
                f'<span>Completion: <strong style="color:#A78BFA;">{completion_tok:,} tokens</strong></span>'
                f'<span>Price input: <strong>${tu.get("price_input_per_mtok_usd", 0):.2f}/Mtok</strong></span>'
                f'<span>Price output: <strong>${tu.get("price_output_per_mtok_usd", 0):.2f}/Mtok</strong></span>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── KPI scorecard vs industry benchmark ───────────────────
        _sec("KPI Scorecard — Achieved vs. Industry Benchmark")
        st.markdown(
            "<div style='font-size:0.88rem;color:#64748B;line-height:1.65;margin-bottom:18px;'>"
            "Pipeline-extracted metrics benchmarked against telecom contact centre industry averages. "
            "Green = at or above benchmark · Amber = within 10pts · Red = below benchmark.</div>",
            unsafe_allow_html=True,
        )

        # (metric_label, achieved_val, benchmark_val, unit, higher_is_better)
        benchmarks = [
            ("First Call Resolution",      kpis.get("fcr_rate_pct", 0),              70.0,  "%",     True),
            ("All Issues Resolved",        kpis.get("all_issues_resolved_pct", 0),   70.0,  "%",     True),
            ("Escalation Rate",            kpis.get("escalation_rate_pct", 0),       15.0,  "%",     False),
            ("Sentiment Improved",         kpis.get("sentiment_improved_pct", 0),    60.0,  "%",     True),
            ("Avoidable Call Rate",        kpis.get("avoidable_call_rate_pct", 0),   35.0,  "%",     False),
            ("Upsell Conversion",          kpis.get("upsell_conversion_pct", 0),     50.0,  "%",     True),
            ("Agent Tool Struggle",        kpis.get("agent_tool_struggle_pct", 0),   10.0,  "%",     False),
            ("Agentic AI Resolvable",      kpis.get("agentic_ai_resolvable_pct", 0), 30.0,  "%",     True),
        ]

        bench_html = '<div class="bench-grid" style="display:grid;grid-template-columns:repeat(2,1fr);gap:14px;">'
        for label, achieved, benchmark, unit, higher_good in benchmarks:
            if higher_good:
                gap = achieved - benchmark
                good = gap >= 0
                near = -10 <= gap < 0
            else:
                gap = benchmark - achieved
                good = gap >= 0
                near = -10 <= gap < 0

            dot_color = "#059669" if good else ("#D97706" if near else "#DC2626")
            bar_pct   = min(achieved / max(benchmark * 1.5, 1) * 100, 100)
            bm_pct    = min(benchmark / max(benchmark * 1.5, 1) * 100, 100)
            direction = "↑ above" if gap > 0 else ("↓ below" if gap < 0 else "= at")
            gap_text  = f"{abs(gap):.0f}{unit} {direction} benchmark"
            status    = "On target" if good else ("Near target" if near else "Below target")

            bench_html += (
                f'<div style="background:#FFFFFF;border-radius:14px;padding:18px 22px;'
                f'box-shadow:0 1px 4px rgba(15,23,42,.08);border-left:4px solid {dot_color};">'
                f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px;">'
                f'<div style="font-size:0.82rem;font-weight:700;color:#0F172A;">{label}</div>'
                f'<div style="font-size:0.68rem;font-weight:700;padding:2px 9px;border-radius:12px;'
                f'background:{dot_color}22;color:{dot_color};">{status}</div>'
                f'</div>'
                f'<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:10px;">'
                f'<div style="font-size:1.6rem;font-weight:900;color:{dot_color};letter-spacing:-0.03em;">{achieved:.0f}{unit}</div>'
                f'<div style="font-size:0.75rem;color:#94A3B8;font-weight:600;">{gap_text}</div>'
                f'</div>'
                f'<div style="position:relative;height:6px;background:#F1F5F9;border-radius:3px;overflow:visible;">'
                f'<div style="height:6px;background:{dot_color};border-radius:3px;width:{bar_pct:.0f}%;opacity:0.7;"></div>'
                f'<div style="position:absolute;top:-4px;left:{bm_pct:.0f}%;width:2px;height:14px;background:#0F172A;border-radius:1px;" title="Benchmark {benchmark}{unit}"></div>'
                f'</div>'
                f'<div style="font-size:0.68rem;color:#94A3B8;margin-top:6px;">Industry benchmark: {benchmark}{unit}</div>'
                f'</div>'
            )
        bench_html += '</div>'
        st.markdown(bench_html, unsafe_allow_html=True)

        # ── Agent quality signals ─────────────────────────────────
        _sec("Agent Quality Signals")
        skill_dist = dist.get("agent_skill", {})
        disp_dist  = dist.get("agent_disproportionate_phase", {})

        aq1, aq2 = st.columns(2)
        with aq1:
            if skill_dist:
                prof  = float(skill_dist.get("proficient", 0))
                adeq  = float(skill_dist.get("adequate", 0))
                needs = float(skill_dist.get("needs_improvement", 0))
                st.markdown(
                    f'<div style="background:#FFFFFF;border-radius:14px;padding:22px 26px;'
                    f'box-shadow:0 1px 4px rgba(15,23,42,.08);">'
                    f'<div style="font-size:0.72rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#94A3B8;margin-bottom:16px;">Agent Skill Distribution</div>'
                    f'<div style="display:flex;height:40px;border-radius:8px;overflow:hidden;margin-bottom:14px;">'
                    f'<div style="background:#059669;width:{prof:.0f}%;display:flex;align-items:center;justify-content:center;color:#fff;font-size:0.8rem;font-weight:700;">Proficient {prof:.0f}%</div>'
                    f'<div style="background:#D97706;width:{adeq:.0f}%;display:flex;align-items:center;justify-content:center;color:#fff;font-size:0.8rem;font-weight:700;">Adequate {adeq:.0f}%</div>'
                    f'<div style="background:#DC2626;width:{needs:.0f}%;display:flex;align-items:center;justify-content:center;color:#fff;font-size:0.8rem;font-weight:700;">Needs improvement {needs:.0f}%</div>'
                    f'</div>'
                    f'<div style="font-size:0.8rem;color:#334155;line-height:1.6;">'
                    f'<strong style="color:#DC2626;">{needs:.0f}%</strong> of agents show knowledge or tool gaps '
                    f'— primary targets for AI-assisted agent tooling and coaching programmes.'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        with aq2:
            if disp_dist:
                phase_overruns = {k: float(v) for k, v in disp_dist.items() if k != "none" and float(v) > 0}
                none_pct = float(disp_dist.get("none", 0))
                overrun_rows = "".join(
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:8px 0;border-bottom:1px solid #F1F5F9;">'
                    f'<span style="font-size:0.84rem;font-weight:600;color:#0F172A;text-transform:capitalize;">{phase}</span>'
                    f'<div style="display:flex;align-items:center;gap:10px;">'
                    f'<div style="width:100px;height:6px;background:#F1F5F9;border-radius:3px;overflow:hidden;">'
                    f'<div style="height:6px;background:#F97316;border-radius:3px;width:{pct:.0f}%;"></div></div>'
                    f'<span style="font-size:0.88rem;font-weight:800;color:#F97316;width:36px;text-align:right;">{pct:.0f}%</span>'
                    f'</div></div>'
                    for phase, pct in sorted(phase_overruns.items(), key=lambda x: -x[1])
                )
                st.markdown(
                    f'<div style="background:#FFFFFF;border-radius:14px;padding:22px 26px;'
                    f'box-shadow:0 1px 4px rgba(15,23,42,.08);">'
                    f'<div style="font-size:0.72rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#94A3B8;margin-bottom:16px;">Phase Overrun — Calls with Disproportionate Phase Time</div>'
                    f'<div style="font-size:0.82rem;color:#64748B;margin-bottom:12px;">'
                    f'{none_pct:.0f}% of calls showed no phase overrun · {100-none_pct:.0f}% had an agent overrunning one phase</div>'
                    f'{overrun_rows}'
                    f'<div style="font-size:0.78rem;color:#94A3B8;margin-top:12px;line-height:1.55;">'
                    f'Phase overrun = call where an agent spent disproportionate time in a single phase vs. the dataset average. '
                    f'High diagnosis overrun signals knowledge gaps; high discovery overrun signals intent-capture friction.'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        if not tu:
            st.markdown(
                '<div class="callout" style="margin-top:14px;">'
                'Token usage and pipeline cost data not found in <code>summary.json</code>. '
                'Run the full pipeline to populate this tab.</div>',
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
