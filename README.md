# Telecom Call Intelligence

> A production-grade **autonomous multi-agent AI pipeline** that turns raw telecom call transcripts into executive-ready intelligence — extracting 70+ structured fields per call using ReAct control loops, scoring quality inline, running a self-reflective deliberation cycle for strategic recommendations, and securing every stage against prompt injection and data leakage — fully automated, end to end.

[![CI](https://github.com/vindon/telecom-call-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/vindon/telecom-call-intelligence/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-4A90D9)
![Gemini](https://img.shields.io/badge/Gemini-2.5%20Flash%20Lite-4285F4?logo=google&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-198%20passing-22C55E)
![License](https://img.shields.io/badge/License-Proprietary-DC2626)

---

## The problem this solves

Contact centres analyse **2–5% of calls** manually. The rest — the other 95% — are invisible. Supervisors make coaching decisions, product teams make roadmap decisions, and operations leaders make cost decisions based on sampled gut feel.

This pipeline analyses **100% of calls, automatically.** Every transcript becomes structured data. Every run produces board-level KPIs, cost-lever estimates, and AI-generated strategic recommendations in minutes.

---

## Live architecture

```
Local CSV (telecom_200k.csv — primary) · HuggingFace fallback (3.7M turns)
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│            LangGraph StateGraph  ·  Multi-Agent Pipeline v3.0        │
│                                                                      │
│  ┌───────────────────┐      ┌────────────────────────────────────┐   │
│  │ DataIngestion     │─────▶│  Extraction Agent  (2/7)           │   │
│  │ Agent  (1/7)      │      │  Gemini · 70 fields · CoT prompt   │   │
│  │ stream · validate │      │  ┌─────── ReAct loop ────────────┐ │   │
│  │ PII scan · audit  │      │  │ Observe: field coverage score │ │   │
│  └───────────────────┘      │  │ Reason: identify null fields  │ │   │
│                             │  │ Act:    targeted gap-fill call│ │   │
│                             │  └───────────────────────────────┘ │   │
│                             └──────────────┬───────────────────── ┘  │
│                                            │                         │
│                                            ▼                         │
│  ┌───────────────────┐      ┌───────────────────┐                   │
│  │  Aggregation      │◀─────│  Quality          │                   │
│  │  Agent  (4/7)     │      │  Agent  (3/7)     │                   │
│  │  KPIs · cost levers│     │  100-pt QA model  │                   │
│  └────────┬──────────┘      │  dynamic routing  │                   │
│           │                 └───────────────────┘                   │
│           ▼                                                          │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Insights Agent  (5/7)  · Vector memory retrieval             │  │
│  │  ┌───────── Deliberation loop (self-reflection) ────────────┐ │  │
│  │  │  Pass 1  Analyze   : CoT KPI analysis → initial insights │ │  │
│  │  │  Pass 2  Critique  : self-grade each recommendation       │ │  │
│  │  │  Pass 3  Synthesize: rewrite weak recommendations         │ │  │
│  │  └──────────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │                                       │
│                              ▼                                       │
│  ┌───────────────────┐      ┌───────────────────┐                   │
│  │  Approval Gate    │─────▶│  Export           │                   │
│  │  (6/7)            │      │  Agent  (7/7)     │                   │
│  │  human sign-off   │      │  CSV · JSON       │                   │
│  │  auto-approve CI  │      │  manifest · audit │                   │
│  └───────────────────┘      └────────┬──────────┘                   │
└───────────────────────────────────── │ ─────────────────────────────┘
                                       │
                            outputs/summary.json
                                       │
                            Streamlit Executive Dashboard
```

**Normal path:** all 7 nodes run in sequence, including the self-reflection deliberation loop.
**Quality gate failure path:** QualityAgent routes directly to ExportAgent — the pipeline always completes with an audit trail.

---

## What makes this production-grade

This is not a tutorial pipeline. Every component reflects how autonomous agentic AI systems are built in enterprise environments.

| Component | What it does | Why it matters |
|-----------|-------------|----------------|
| **ReAct extraction loop** | Observe (field-coverage score) → Reason (identify null critical fields) → Act (targeted gap-fill call) — up to `REACT_MAX_ITERATIONS` per transcript | Industry-standard agentic control loop; demonstrably improves extraction quality on ambiguous transcripts |
| **Chain-of-Thought prompts** | `_cot_reasoning` as the first JSON field forces the LLM to articulate its reasoning before committing to field values | Measurably reduces hallucination on enum and boolean fields without extra API calls |
| **Deliberation loop** | InsightsAgent runs 3 passes (NVIDIA NIM primary · Gemini fallback · Claude fallback): Analyze (CoT) → Critique (self-reflection) → Synthesize (rewrite weak recommendations) | Self-reflective pattern ensures board-ready, data-grounded recommendations rather than generic platitudes |
| **Vector memory** | Gemini `text-embedding-004` embeds each run's KPI summary; numpy cosine similarity retrieves the top-K most similar historical runs | Semantic long-term memory — InsightsAgent receives relevant historical context, not just averages |
| **Security layer** | `InputSanitizer` (injection, encoding, secrets), `OutputSanitizer` (code execution, response bombs), `AgentScopeGuard` (per-agent tool access control), `SecretGuard` (key leakage), `RateLimiter` (API consumption cap) | Production systems face real attacks; this handles prompt injection, jailbreak attempts, cross-agent tool hijacking, and secret exfiltration |
| **Human approval gate** | Configurable `approval_gate_node` before export; auto-approves in CI, interactive prompt with timeout in production | Prevents fully-autonomous export without human review in regulated or high-stakes deployments |
| **LangSmith tracing** | One-env-var activation (`LANGCHAIN_TRACING_V2=true`); LangGraph auto-traces every node | Full observability across all 7 nodes and both LLM agents |
| **Governance layer** | `BudgetGuard` (hard cost cap), `QualityGate` (extraction quality threshold), `PIIScanner` (6 PII types, auto-redact), `AuditLog` (append-only event trace) | Compliance, safety, and cost control without manual intervention |
| **Agent memory** | Flat JSON cross-run store + semantic vector store — FCR trends, failure patterns, quota events, model performance | Each run learns from previous ones; context injected into InsightsAgent prompt |
| **Tool registry** | Formal JSON-schema definitions for all 5 agent operations; uniform audit trail; LLM-discoverable | Enables future LLM-driven tool selection; swappable implementations for testing |
| **Orchestrator** | `WorkPlanner`, `AgentHealthMonitor`, adaptive retry, process isolation | A crashed batch cannot corrupt others; health degradation triggers alerts |
| **Dynamic routing** | LangGraph `add_conditional_edges` — quality gate failure bypasses aggregation, insights, and approval | Pipeline always completes, even under catastrophic extraction failure |
| **Checkpoint/resume** | Each API call persisted immediately to `outputs/.checkpoint_{key}.jsonl` | Kill a 100-call job at call 73 — restart and it picks up from 74 |
| **198 unit tests** | Security, governance, memory, orchestrator, tools, config, graph — all tested without API calls | CI runs in under 6 seconds; tests gate every push |
| **Quota circuit breaker** | `_react_quota_exhausted` flag in `analyzer.py` trips on first 429 in gap-fill; disables all subsequent gap-fill retries for the remainder of the run | Free-tier 20 RPD is preserved for primary extraction across all batches |

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
| Test suite | 198 tests, < 6 seconds |

---

## Quick start

**Prerequisites:** Python 3.11+ · Free [Google AI Studio key](https://aistudio.google.com) (no credit card)

```bash
git clone https://github.com/vindon/telecom-call-intelligence.git
cd telecom-call-intelligence

python -m venv .venv && source .venv/bin/activate
make install-dev          # installs prod + dev deps + pre-commit hooks

cp .env.example .env
# Required: GEMINI_API_KEY
# Optional: LANGCHAIN_TRACING_V2=true + LANGCHAIN_API_KEY  (LangSmith tracing)

make run                  # 3-call smoke test (~30 seconds)
make run-batches          # 100-call production run (5 × 20 batches)
streamlit run dashboard/app.py   # executive dashboard
```

---

## Developer commands

```bash
make test          # 198 unit tests — no API calls required
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
│   ├── security.py          ← InputSanitizer, OutputSanitizer, AgentScopeGuard,
│   │                            SecretGuard, RateLimiter — full security layer
│   ├── vector_memory.py     ← Semantic KPI memory (Gemini embeddings + cosine similarity)
│   ├── agents/
│   │   ├── data_agent.py        ← Agent 1: DataIngestionAgent
│   │   ├── extraction_agent.py  ← Agent 2: ExtractionAgent (Gemini + ReAct loop)
│   │   ├── quality_agent.py     ← Agent 3: QualityAgent (100-pt QA)
│   │   ├── aggregation_agent.py ← Agent 4: AggregationAgent (KPIs)
│   │   ├── insights_agent.py    ← Agent 5: InsightsAgent (deliberation loop)
│   │   └── export_agent.py      ← Agent 6: ExportAgent (CSV/JSON/audit)
│   ├── graph.py             ← LangGraph StateGraph (7 nodes, conditional routing,
│   │                            approval gate, LangSmith tracing)
│   ├── orchestrator.py      ← WorkPlanner, AgentHealthMonitor, retry logic
│   ├── governance.py        ← BudgetGuard, QualityGate, PIIScanner, AuditLog
│   ├── memory.py            ← Persistent cross-run agent memory (flat JSON)
│   ├── tools.py             ← Formal tool registry with JSON schemas
│   ├── analyzer.py          ← Gemini API client (CoT, ReAct, checkpoint, backoff)
│   ├── aggregator.py        ← KPI computation + cost-lever estimates
│   ├── hf_loader.py         ← HuggingFace streaming + offset batching
│   ├── token_tracker.py     ← Per-call token cost accounting
│   └── logger.py            ← Structured logging (INFO→stdout, DEBUG→file)
│
├── tests/                   ← 198 unit tests (no API calls)
│   ├── test_config.py
│   ├── test_governance.py
│   ├── test_memory.py
│   ├── test_orchestrator.py
│   ├── test_tools.py
│   ├── test_graph.py
│   └── test_security.py     ← 49 security tests
│
├── dashboard/app.py         ← Streamlit executive dashboard (7 sections, traffic-signal action plan)
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
└── CHANGELOG.md             ← Versioned history (v0.1 → v1.0 → v2.0 → v3.0)
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

## Agentic patterns implemented

| Pattern | File | Description |
|---------|------|-------------|
| **ReAct** | `extraction_agent.py`, `analyzer.py` | Reason→Act→Observe loop with targeted gap-fill retries |
| **Chain-of-Thought** | `analyzer.py`, `insights_agent.py` | `_cot_reasoning` field in all LLM prompts |
| **Self-reflection / deliberation** | `insights_agent.py` | Analyze → Critique → Synthesize (3 Gemini passes) |
| **Semantic long-term memory** | `vector_memory.py` | Cosine similarity over Gemini-embedded KPI histories |
| **Tool access control** | `security.py` | `AgentScopeGuard` with per-agent authorized tool sets |
| **Human-in-the-loop** | `graph.py` | Configurable approval gate before autonomous export |
| **Distributed tracing** | `graph.py` | LangSmith integration via `LANGCHAIN_TRACING_V2` |

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

The 7-node architecture is designed for this. Only `data_agent.py` changes when you swap data sources. Everything downstream — QA, aggregation, insights, export — is data-source agnostic.

---

## Dashboard — Telecom Call Intelligence

The executive dashboard (`dashboard/app.py`) is a full professional light-theme Streamlit app with 7 sections. It reads `outputs/summary.json` on every load and falls back to built-in demo data when no pipeline output is present.

```
streamlit run dashboard/app.py   # http://localhost:8501
```

| Section | What it shows |
|---------|--------------|
| **Hero** | Bold headline: "X out of every 100 customer contacts don't need a human agent" — based on live transcript analysis |
| **Cost Panels** | Two side-by-side cards: *Insights from N Calls Analysed* (Cost to Serve / Sell / Retain breakdown, forecast at 100K volume) and *AI Recovery Opportunity* (autonomous resolution %, monthly saving vs baseline, annual recovery) |
| **1 — The Evidence** | Issue category bar chart (what customers call about) + vertical phase-time chart (where agent time goes inside every call) |
| **2 — Resolution Opportunity** | Three resolution segments — PREVENT (proactive outreach) · AUTOMATE (agentic AI / self-serve) · HUMAN REQUIRED — each with call count, monthly cost impact, and description |
| **3 — Which AI Agents to Build** | Ranked roadmap table: call intent · calls/month estimate · resolution type · saving/month · build effort |
| **4 — Actual Performance** | 6 metric cards: FCR, AHT, escalation rate, issues resolved, sentiment improved, avoidable call rate |
| **5 — Prioritised Action Plan** | Traffic-signal action table — CRITICAL / HIGH / QUICK WIN — each row has initiative, scope, estimated monthly impact, and next step |
| **6 — Performance Trends** | Multi-run trend charts (FCR, AHT, QA score) — visible when ≥ 2 pipeline runs exist |

---

## Dataset

**[`talkmap/telecom-conversation-corpus`](https://huggingface.co/datasets/talkmap/telecom-conversation-corpus)** — MIT License

3.73M turns · ~200K conversations · synthetic telecom customer care (realistic, not real recordings)

---

## Further reading

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — Multi-agent design, agentic control loops, security layer, state schema
- [`SECURITY.md`](SECURITY.md) — Threat model, PII handling, vulnerability disclosure
- [`CHANGELOG.md`](CHANGELOG.md) — Version history from v0.1.0 through v3.0.0

---

## Built by

**Vinoth N** — AI systems engineer with hands-on experience designing and shipping production-grade autonomous agentic pipelines.

This project demonstrates end-to-end ownership of a v3.0 autonomous multi-agent system: ReAct control loops, Chain-of-Thought prompting, self-reflective deliberation, semantic vector memory, multi-layer security hardening, LangGraph orchestration, LLM prompt engineering, quality assurance, observability, and developer tooling — built to the standards a Series A company would actually ship.

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
