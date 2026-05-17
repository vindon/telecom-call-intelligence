# Telecom Call Intelligence

> A production-grade **multi-agent AI pipeline** that turns raw telecom call transcripts into executive-ready intelligence — extracting 70+ structured fields per call, scoring extraction quality inline, aggregating KPIs, and generating LLM-powered strategic recommendations — fully automated, end to end.

[![CI](https://github.com/vindon/telecom-call-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/vindon/telecom-call-intelligence/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-4A90D9)
![Gemini](https://img.shields.io/badge/Gemini-2.5%20Flash%20Lite-4285F4?logo=google&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-149%20passing-22C55E)
![License](https://img.shields.io/badge/License-Proprietary-DC2626)

---

## The problem this solves

Contact centres analyse **2–5% of calls** manually. The rest — the other 95% — are invisible. Supervisors make coaching decisions, product teams make roadmap decisions, and operations leaders make cost decisions based on sampled gut feel.

This pipeline analyses **100% of calls, automatically.** Every transcript becomes structured data. Every run produces board-level KPIs, cost-lever estimates, and AI-generated strategic recommendations in minutes.

---

## Live architecture

```
HuggingFace Corpus (3.7M turns · 200K conversations)
           │
           ▼
┌──────────────────────────────────────────────────────────────────────┐
│              LangGraph StateGraph  ·  Multi-Agent Pipeline v2.0      │
│                                                                      │
│  ┌───────────────────┐      ┌───────────────────┐                   │
│  │ DataIngestion     │─────▶│  Extraction       │                   │
│  │ Agent  (1 of 6)   │      │  Agent  (2 of 6)  │                   │
│  │ stream · validate │      │  Gemini · 70 fields│                  │
│  │ PII scan · audit  │      │  checkpoint/resume │                   │
│  └───────────────────┘      └────────┬──────────┘                   │
│                                      │                               │
│                                      ▼                               │
│  ┌───────────────────┐      ┌───────────────────┐                   │
│  │  Aggregation      │◀─────│  Quality          │                   │
│  │  Agent  (4 of 6)  │      │  Agent  (3 of 6)  │                   │
│  │  KPIs · cost levers│     │  100-pt QA model  │                   │
│  └────────┬──────────┘      │  dynamic routing  │                   │
│           │                 └───────────────────┘                   │
│           ▼                                                          │
│  ┌───────────────────┐      ┌───────────────────┐                   │
│  │  Insights         │─────▶│  Export           │                   │
│  │  Agent  (5 of 6)  │      │  Agent  (6 of 6)  │                   │
│  │  Gemini · strategy│      │  CSV · JSON       │                   │
│  │  LLM + fallback   │      │  manifest · audit │                   │
│  └───────────────────┘      └────────┬──────────┘                   │
└───────────────────────────────────── │ ─────────────────────────────┘
                                       │
                            outputs/summary.json
                                       │
                            Streamlit Executive Dashboard
```

**Normal path:** all 6 agents run in sequence.
**Quality gate failure path:** QualityAgent routes directly to ExportAgent, skipping aggregation and insights — the pipeline always completes with an audit trail.

---

## What makes this production-grade

This is not a tutorial pipeline. Every component reflects how agentic AI systems are built in enterprise environments.

| Component | What it does | Why it matters |
|-----------|-------------|----------------|
| **Governance layer** | `BudgetGuard` (hard cost cap), `QualityGate` (extraction quality threshold), `PIIScanner` (6 PII pattern types, auto-redact), `AuditLog` (append-only event trace) | Compliance, safety, and cost control without manual intervention |
| **Agent memory** | Persistent cross-run JSON store — FCR trends, failure patterns, quota events, model performance | Each run learns from previous ones; InsightsAgent injects historical context into its LLM prompt |
| **Tool registry** | Formal JSON-schema definitions for all 5 agent operations; uniform audit trail; LLM-discoverable via `REGISTRY.manifest()` | Enables future LLM-driven tool selection; swappable implementations for testing |
| **Orchestrator** | `WorkPlanner` (batch planning), `AgentHealthMonitor` (per-agent success tracking), adaptive retry, process isolation | A crashed batch cannot corrupt others; health degradation triggers alerts |
| **Dynamic routing** | LangGraph `add_conditional_edges` — quality gate failure bypasses aggregation and insights | Pipeline completes even under catastrophic extraction failure |
| **Checkpoint/resume** | Each API call persisted immediately to `outputs/.checkpoint_{key}.jsonl` | Kill a 100-call job at call 73 — restart and it picks up from 74 |
| **Dual LLM agents** | ExtractionAgent (per-call JSON, temp=0.1) and InsightsAgent (cross-call strategy, temp=0.3) | Different roles, different temperatures, different prompts — not one model doing everything |
| **149 unit tests** | Governance, memory, orchestrator, tools, config, graph — all tested without API calls | CI runs in under 1 second; tests gate every push |
| **thinking_budget=0** | Disables Gemini 2.5 thinking step | Prevents thinking tokens consuming the output budget; required for 70-field JSON to fit in one response |

---

## Results (100-call run)

| Metric | Value |
|--------|-------|
| Calls analyzed | 100 |
| Fields extracted per call | 70+ |
| Extraction cost | < $0.01 USD (Gemini free tier) |
| QA pass rate | Typically 90–95% |
| Avg QA score | 85–92 / 100 |
| Pipeline runtime | ~8 min (5 × 20 batches, 2s inter-call delay) |
| Checkpoint overhead | Zero — resume is instantaneous |
| Test suite | 149 tests, < 1 second |

---

## Quick start

**Prerequisites:** Python 3.11+ · Free [Google AI Studio key](https://aistudio.google.com) (no credit card)

```bash
git clone https://github.com/vindon/telecom-call-intelligence.git
cd telecom-call-intelligence

python -m venv .venv && source .venv/bin/activate
make install-dev          # installs prod + dev deps + pre-commit hooks

cp .env.example .env
# Set GEMINI_API_KEY in .env

make run                  # 3-call smoke test (~30 seconds)
make run-batches          # 100-call production run (5 × 20 batches)
streamlit run dashboard/app.py   # executive dashboard
```

---

## Developer commands

```bash
make test          # 149 unit tests — no API calls required
make lint          # ruff linter across all source files
make check         # lint + type-check + test (full pre-push gate)
make test-cov      # tests with HTML coverage report
make dashboard     # Streamlit dashboard on localhost:8501
make clean         # remove __pycache__, .pyc, pytest cache
```

---

## Project structure

```
telecom-call-intelligence/
│
├── pipeline/
│   ├── config.py            ← Single source of truth for all constants
│   ├── agents/
│   │   ├── data_agent.py    ← Agent 1: DataIngestionAgent
│   │   ├── extraction_agent.py  ← Agent 2: ExtractionAgent (Gemini)
│   │   ├── quality_agent.py     ← Agent 3: QualityAgent (100-pt QA)
│   │   ├── aggregation_agent.py ← Agent 4: AggregationAgent (KPIs)
│   │   ├── insights_agent.py    ← Agent 5: InsightsAgent (Gemini + fallback)
│   │   └── export_agent.py      ← Agent 6: ExportAgent (CSV/JSON/audit)
│   ├── graph.py             ← LangGraph StateGraph (6 nodes, conditional routing)
│   ├── orchestrator.py      ← WorkPlanner, AgentHealthMonitor, retry logic
│   ├── governance.py        ← BudgetGuard, QualityGate, PIIScanner, AuditLog
│   ├── memory.py            ← Persistent cross-run agent memory
│   ├── tools.py             ← Formal tool registry with JSON schemas
│   ├── analyzer.py          ← Gemini API client (checkpoint, backoff, tokens)
│   ├── aggregator.py        ← KPI computation + cost-lever estimates
│   ├── hf_loader.py         ← HuggingFace streaming + offset batching
│   ├── token_tracker.py     ← Per-call token cost accounting
│   └── logger.py            ← Structured logging (INFO→stdout, DEBUG→file)
│
├── tests/                   ← 149 unit tests (no API calls)
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_governance.py
│   ├── test_memory.py
│   ├── test_orchestrator.py
│   ├── test_tools.py
│   └── test_graph.py
│
├── dashboard/app.py         ← Streamlit executive dashboard (9 panels)
├── prompts/system_prompt.txt ← 70-field extraction schema
│
├── run_pipeline.py          ← Single-batch entry point
├── run_batches.py           ← Multi-batch orchestrator (delegates to Orchestrator)
├── merge_outputs.py         ← Merge batch JSONs → combined dataset
├── qa_audit.py              ← Standalone QA scoring tool
│
├── pyproject.toml           ← ruff, mypy, pytest config
├── Makefile                 ← Developer shortcuts
├── CLAUDE.md                ← AI assistant guide for this repo
├── ARCHITECTURE.md          ← Full technical reference
├── SECURITY.md              ← Threat model, PII policy, disclosure process
└── CHANGELOG.md             ← Versioned history (v0.1 → v1.0 → v2.0)
```

---

## KPIs extracted per call

| Category | Fields |
|----------|--------|
| **Resolution** | `first_call_resolution`, `resolution_status`, `escalated` |
| **Effort** | `handle_time_seconds`, `issue_count`, `hold_time_seconds` |
| **Intent** | `intent` (24 categories), `avoidable_call`, `agentic_ai_resolvable` |
| **Sentiment** | `sentiment_start`, `sentiment_end`, `sentiment_trajectory` |
| **Risk** | `repeat_call_risk`, `churn_risk_signal` |
| **Commercial** | `upsell_attempted`, `upsell_success`, `cross_sell_opportunity` |
| **Operations** | `cost_driver`, `agent_professionalism`, `tool_struggle_detected` |
| **Phase durations** | `greeting_s`, `issue_s`, `resolution_s`, `wrap_up_s` |

---

## Extending to real enterprise data

```python
# 1. Replace the HuggingFace loader with your data source
# pipeline/agents/data_agent.py — swap load_telecom_transcripts()
# with your S3, Snowflake, Genesys, or SFTP connector

# 2. Transcripts need: call_id, transcript_text, call_date
# Turns format: "Agent: ... \nCustomer: ..."

# 3. Calibrate cost model to your actuals
# pipeline/aggregator.py → COST_PER_CALL_USD = <your figure>

# 4. Add your enums to the extraction prompt
# prompts/system_prompt.txt → intent, cost_driver, etc.
```

The 6-agent architecture is designed for this. Only `data_agent.py` changes when you swap data sources. Everything downstream — QA, aggregation, insights, export — is data-source agnostic.

---

## Dashboard panels

| Panel | What it shows |
|-------|--------------|
| Executive KPIs | AHT, FCR, avoidable call rate, escalation rate, sentiment lift |
| Cost-to-Serve Levers | Monthly savings from self-serve, agentic AI, proactive outreach |
| AI Resolvability | % of calls fully handleable by an AI agent |
| Phase Breakdown | Where handle time is spent — greeting, issue, resolution, wrap-up |
| Cost Waterfall | Baseline → optimised cost with each lever applied |
| Deflection Opportunity | Self-serve + agentic AI + proactive care eligibility |
| Agent Performance | Skill distribution, tool struggle, repeat call risk |
| Sentiment Analysis | Customer sentiment at call start vs. end |
| Token Usage | Inference cost per run, per-call average, monthly projection |

---

## Dataset

**[`talkmap/telecom-conversation-corpus`](https://huggingface.co/datasets/talkmap/telecom-conversation-corpus)** — MIT License

3.73M turns · ~200K conversations · synthetic telecom customer care (realistic, not real recordings)

---

## Further reading

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — Multi-agent design, LangGraph state schema, orchestrator, governance layer
- [`SECURITY.md`](SECURITY.md) — Threat model, PII handling, vulnerability disclosure
- [`CHANGELOG.md`](CHANGELOG.md) — Version history from v0.1.0 through v2.0.0

---

## Built by

**Vinoth N** — AI systems builder with hands-on experience designing and shipping production-grade agentic AI pipelines.

This project demonstrates end-to-end ownership of an agentic AI system: architecture design, multi-agent orchestration, governance and safety layers, LLM prompt engineering, quality assurance, observability, and developer tooling — built to the standards a Series A company would actually ship.

**Open to partnerships:**

| Mode | What that looks like |
|------|---------------------|
| **Employee** | AI/ML Engineer · LLM Platform Engineer · Senior Backend Engineer at an AI-first company |
| **Co-founder** | Technical co-founder for an AI or enterprise SaaS venture — I bring the architecture, you bring the market |
| **Consultant** | Agentic AI system design · LLM pipeline architecture · multi-agent frameworks (LangGraph, Gemini, Claude) |
| **Contract** | Fixed-scope delivery: pipeline builds, LLM integrations, data intelligence products |

📧 **vinoth.n@outlook.com**

---

## License

Copyright © 2026 Vinoth N. All rights reserved. Proprietary — not open source.

Dataset: `talkmap/telecom-conversation-corpus` — MIT License (original authors).
