# Telecom Call Intelligence

> A production-grade **autonomous multi-agent AI pipeline** built on Claude's Agentic AI framework — turning raw telecom call transcripts into board-ready intelligence. Every call analysed. Every decision traceable. Every stage secured and governed.

[![CI](https://github.com/vindon/telecom-call-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/vindon/telecom-call-intelligence/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-4A90D9)
![Claude](https://img.shields.io/badge/Claude-Haiku%204.5-CC785C?logo=anthropic&logoColor=white)
![NVIDIA](https://img.shields.io/badge/NVIDIA-NIM%20LLaMA--3.3--70B-76B900?logo=nvidia&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-224%20passing-22C55E)
![License](https://img.shields.io/badge/License-Proprietary-DC2626)

---

## The problem this solves

Contact centres analyse **2–5% of calls** manually. The other 95% are invisible. Supervisors make coaching decisions, product teams make roadmap decisions, and operations leaders make cost decisions based on sampled gut-feel.

This pipeline analyses **100% of calls, autonomously.** Every transcript becomes structured data. Every run produces board-level KPIs, cost-lever estimates, and strategically grounded AI recommendations — in minutes, end to end, with a full audit trail of every decision taken.

---

## Agentic AI framework

This system is a direct implementation of Anthropic's Agentic AI framework: **agents that perceive, reason, act, observe, and adapt** in orchestrated multi-agent pipelines — with the safety, traceability, and governance that production deployment demands.

| Claude Agentic Principle | How it's implemented |
|--------------------------|---------------------|
| **Tool use** | Formal JSON-schema tool registry; each agent calls only its authorised tools via `AgentScopeGuard` |
| **Multi-agent orchestration** | 6 specialised agents + a human approval gate in a 7-node LangGraph `StateGraph`; each stateless, composable, and replaceable |
| **Reasoning loops** | ReAct (Observe→Reason→Act) per transcript; 3-pass deliberation (Analyze→Critique→Synthesize) for insights |
| **Chain-of-Thought** | `_cot_reasoning` as the mandatory first JSON field forces structured reasoning before every extraction and recommendation |
| **Long-term memory** | Flat JSON run history + Gemini-embedded semantic vector store; top-K similar historical runs injected into InsightsAgent context |
| **Decision traceability** | `DecisionLogger` captures WHY every autonomous decision was made — routing choices, exclusions, provider selections, gap-fills — all serialised to `decisions_{ts}.json` |
| **Human-in-the-loop** | Configurable approval gate before export; auto-approves in CI, interactive prompt with timeout in production |
| **Defence in depth** | `InputSanitizer`, `OutputSanitizer`, `AgentScopeGuard`, `SecretGuard`, `RateLimiter` — protecting every agent boundary |
| **Graceful degradation** | Every component has a fallback path; the pipeline always completes with a full audit trail |

---

## Live architecture

```
Local CSV (telecom_200k.csv — primary) · HuggingFace stream (fallback, 3.7M turns)
                            │
                            ▼
┌───────────────────────────────────────────────────────────────────────────┐
│              LangGraph StateGraph  ·  Multi-Agent Pipeline v4.0           │
│                                                                           │
│  ┌─────────────────────┐    ┌──────────────────────────────────────────┐  │
│  │  DataIngestion      │───▶│  Extraction Agent  (2/7)                 │  │
│  │  Agent  (1/7)       │    │  Claude Haiku 4.5 · 70 fields · CoT      │  │
│  │  stream · validate  │    │  ┌─────────── ReAct loop ──────────────┐ │  │
│  │  PII scan · audit   │    │  │ Observe : score_field_coverage()    │ │  │
│  │  decision log       │    │  │ Reason  : identify null fields      │ │  │
│  └─────────────────────┘    │  │ Act     : targeted gap-fill call    │ │  │
│                             │  └─────────────────────────────────────┘ │  │
│                             └─────────────────┬────────────────────────┘  │
│                                               │                           │
│                                               ▼                           │
│  ┌─────────────────────┐    ┌─────────────────────────┐                  │
│  │  Aggregation        │◀───│  Quality Agent  (3/7)   │                  │
│  │  Agent  (4/7)       │    │  100-pt QA model        │                  │
│  │  KPIs · cost levers │    │  dynamic routing        │                  │
│  └──────────┬──────────┘    │  exclusion logging      │                  │
│             │               └─────────────────────────┘                  │
│             ▼                                                             │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │  Insights Agent  (5/7)  · Vector memory → top-K historical runs   │   │
│  │  Provider: NVIDIA NIM (primary) · Claude (fallback) · Rule-based  │   │
│  │  ┌──────────── Deliberation loop (self-reflection) ─────────────┐ │   │
│  │  │  Pass 1  Analyze   : CoT KPI analysis → initial insights     │ │   │
│  │  │  Pass 2  Critique  : self-grade each recommendation (A/B/C)  │ │   │
│  │  │  Pass 3  Synthesize: rewrite weak/generic recommendations    │ │   │
│  │  └──────────────────────────────────────────────────────────────┘ │   │
│  └───────────────────────────────┬───────────────────────────────────┘   │
│                                  │                                        │
│                                  ▼                                        │
│  ┌─────────────────────┐    ┌─────────────────────────┐                  │
│  │  Approval Gate      │───▶│  Export Agent  (7/7)    │                  │
│  │  (6/7)              │    │  CSV · JSON · decisions │                  │
│  │  human sign-off     │    │  manifest · audit log   │                  │
│  │  auto-approve CI    │    │  decision log           │                  │
│  └─────────────────────┘    └──────────┬──────────────┘                  │
└──────────────────────────────────────── │ ─────────────────────────────  ┘
                                          │
                               outputs/ directory
                               ├── summary.json               ← Streamlit dashboard
                               ├── call_results_{ts}.csv
                               ├── full_results_{ts}.json
                               ├── qa_report_{ts}.json
                               ├── insights_{ts}.json
                               ├── decisions_{ts}.json         ← agent reasoning audit
                               ├── run_manifest_{ts}.json
                               └── audit_log_{ts}.json
```

**Normal path:** DataIngestion → Extraction → Quality → Aggregation → Insights → ApprovalGate → Export

**Quality gate failure path:** Quality → Export (bypasses aggregation and insights; always completes with audit)

---

## What makes this a complete agentic AI system

Every component exists because production autonomous systems need it.

| Capability | Implementation | Why it matters |
|------------|----------------|----------------|
| **ReAct extraction loop** | `ExtractionAgent`: Observe (field-coverage score) → Reason (identify null fields) → Act (targeted gap-fill) up to `REACT_MAX_ITERATIONS` | Industry-standard agentic control loop; recovers critical fields missed in the first extraction pass |
| **Chain-of-Thought** | `_cot_reasoning` is the mandatory first field in every LLM response — the model must reason before extracting | Forces structured reasoning at zero extra API cost; measurably reduces enum/boolean hallucination |
| **Self-reflection deliberation** | InsightsAgent: Pass 1 Analyze → Pass 2 Critique → Pass 3 Synthesize | AI critiques its own output before delivering to the user — produces data-grounded, board-ready recommendations, not platitudes |
| **Decision traceability** | `DecisionLogger` in every agent: records decision type, reasoning, evidence, alternatives considered, and confidence | Full audit trail of WHY every autonomous action occurred — retracing, challenging, and explaining agent decisions |
| **Plug-and-play model architecture** | `EXTRACTION_MODEL` in `config.py` drives everything — rate limiters, API clients, cost estimates, provider labels — one change, zero regressions | Switch from Claude to Gemini or any future model without touching agent code |
| **Semantic long-term memory** | Gemini `text-embedding-004` embeds each run's KPI summary; numpy cosine similarity retrieves top-K most similar historical runs | Agents learn from history — InsightsAgent receives relevant context, not just averages |
| **Multi-layer security** | `InputSanitizer` (injection + PII), `OutputSanitizer` (code execution + secrets), `AgentScopeGuard` (tool access), `SecretGuard`, `RateLimiter` | Prompt injection, cross-agent tool hijacking, secret exfiltration, response bombs — all blocked before they reach downstream agents |
| **Human approval gate** | Configurable checkpoint before export: interactive in production, auto-approve in CI | Autonomous systems need human oversight options; this is where operators review KPIs before outputs are written |
| **Governance layer** | `BudgetGuard` (reads `BUDGET_USD` from config), `QualityGate`, `PIIScanner`, `AuditLog` | Cost caps, quality thresholds, PII compliance, and event traceability — without manual intervention |
| **LangSmith tracing** | One env var (`LANGCHAIN_TRACING_V2=true`) enables full node-level span capture | End-to-end observability across all 7 pipeline nodes and every LLM provider |
| **Dynamic routing** | LangGraph conditional edge after QualityAgent | Catastrophic extraction failure routes to safe export; the pipeline never silently fails |
| **Checkpoint/resume** | Every API call persisted to `outputs/.checkpoint_{key}.jsonl` immediately | Kill a 100-call job at call 73 — restart and it resumes from 74 with zero duplicated API spend |
| **Process isolation** | `run_batches.py` → `Orchestrator` → N subprocesses | A crashed batch cannot corrupt other batches; full batch-level retry with health monitoring |
| **224 unit tests** | Security, governance, decision log, memory, orchestrator, tools, config, graph — all tested without API calls | CI completes in under 7 seconds; tests gate every push to main |

---

## Model architecture

| Role | Primary | Fallback 1 | Fallback 2 |
|------|---------|-----------|-----------|
| **Extraction** (70 fields/call) | Claude Haiku 4.5 | Gemini 2.0 Flash Lite | — |
| **Insights** (strategic recs) | NVIDIA NIM `llama-3.3-70b-instruct` | Claude Haiku 4.5 | Rule-based |
| **Embeddings** (vector memory) | Gemini `text-embedding-004` | TF-IDF bag-of-words (offline) | — |

**Switching models:** Change `EXTRACTION_MODEL` in `pipeline/config.py` — all API clients, rate limiters, cost estimates, provider labels, and budget guards update automatically.

---

## Results (100-call production run)

| Metric | Value |
|--------|-------|
| Calls analysed | 100 |
| Fields extracted per call | 70+ |
| QA pass rate | Typically 90–99% |
| Avg QA score | 85–99 / 100 |
| Pipeline runtime | ~8 min (5 × 20 batches, 2s inter-call delay) |
| Extraction cost (Claude Haiku) | ~$0.76 / 100 calls (~$0.0076/call) |
| Extraction cost (Gemini free tier) | ~$0.00 / 100 calls (free-tier eligible) |
| Deliberation passes | 3 per insights run |
| Decision records per run | 15–60 traceable decisions |
| Test suite | 224 tests · < 7 seconds |
| Checkpoint overhead | Zero — resume is instantaneous |

---

## Quick start

**Prerequisites:** Python 3.11+

```bash
git clone https://github.com/vindon/telecom-call-intelligence.git
cd telecom-call-intelligence

python -m venv .venv && source .venv/bin/activate
make install-dev

cp .env.example .env
```

Add your API keys to `.env`:

```bash
# Required for extraction (Claude Haiku — primary)
ANTHROPIC_API_KEY=sk-ant-...

# Required for insights embeddings (Gemini — fallback extraction + vector memory)
GEMINI_API_KEY=AIza...

# Optional: NVIDIA NIM for InsightsAgent primary (falls back to Claude if absent)
NVIDIA_API_KEY=nvapi-...

# Optional: LangSmith tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
```

```bash
make run                  # 3-call smoke test (~30 seconds)
make run-batches          # 100-call production run (5 × 20 batches)
make dashboard            # executive dashboard at localhost:8501
```

---

## Developer commands

```bash
make test          # 224 unit tests — no API calls required (< 7 seconds)
make lint          # ruff linter across all source files
make check         # lint + type-check + test (full pre-push gate)
make test-cov      # tests with HTML coverage report
make dashboard     # Streamlit dashboard on localhost:8501
make clean         # remove __pycache__, .pyc, pytest cache
```

---

## Agentic patterns implemented

| Pattern | Files | Description |
|---------|-------|-------------|
| **ReAct** | `extraction_agent.py`, `analyzer.py` | Per-transcript Observe → Reason → Act control loop with targeted gap-fill retries |
| **Chain-of-Thought** | `analyzer.py`, `insights_agent.py` | `_cot_reasoning` as mandatory first JSON field across all LLM responses |
| **Self-reflection / deliberation** | `insights_agent.py` | 3-pass Analyze → Critique → Synthesize loop with A/B/C recommendation grading |
| **Decision traceability** | `decision_log.py`, all agents | Structured WHY records for every autonomous decision, with evidence and alternatives |
| **Semantic long-term memory** | `vector_memory.py` | Gemini-embedded KPI histories with cosine similarity retrieval |
| **Tool access control** | `security.py` | `AgentScopeGuard` enforces per-agent authorised tool sets |
| **Human-in-the-loop** | `graph.py` | Configurable approval gate before any outputs are written to disk |
| **Distributed tracing** | `graph.py` | LangSmith integration via `LANGCHAIN_TRACING_V2` — full span capture |
| **Plug-and-play providers** | `config.py`, `analyzer.py`, `token_tracker.py` | Single `EXTRACTION_MODEL` config value drives all downstream provider logic |

---

## KPIs extracted per call

| Category | Fields |
|----------|--------|
| **Resolution** | `fcr_indicator`, `all_issues_resolved`, `primary_issue_resolved`, `escalation_required` |
| **Effort** | `total_duration_seconds`, `total_issues_count`, `hold_count`, `phase_hold_total_seconds` |
| **Intent** | `issue_1..5_category`, `avoidable_call`, `agentic_ai_resolvable`, `could_be_self_served` |
| **Sentiment** | `customer_sentiment_start`, `customer_sentiment_end`, `customer_sentiment_improved` |
| **Risk** | `repeat_call_risk`, `customer_expressed_dissatisfaction` |
| **Commercial** | `upsell_attempted`, `upsell_outcome`, `plans_discussed` |
| **Operations** | `primary_cost_driver`, `agent_skill_rating`, `agent_tool_struggle_detected`, `handle_time_efficiency` |
| **Phase durations** | `phase_welcome/discovery/diagnosis/resolution/upsell/closing_duration_seconds` |
| **Reasoning** | `_cot_reasoning` (LLM step-by-step analysis before field extraction) |

---

## Dashboard

The executive dashboard (`dashboard/app.py`) is a professional light-theme Streamlit application with 8 sections, reading live from `outputs/summary.json`. Falls back to built-in demo data when no pipeline output is present.

```bash
streamlit run dashboard/app.py   # http://localhost:8501
```

| Section | Content |
|---------|---------|
| **Hero** | "X out of every 100 contacts don't need a human agent" — from live analysis |
| **Cost Panels** | *Insights from N Calls Analysed* (Cost to Serve/Sell/Retain forecast) · *AI Recovery Opportunity* (monthly saving vs baseline) |
| **Evidence** | Issue category bar chart · phase-time waterfall |
| **Resolution Opportunity** | PREVENT · AUTOMATE · HUMAN REQUIRED — with cost impact per segment |
| **AI Agents to Build** | Ranked roadmap: intent · calls/month · saving/month · build effort |
| **Actual Performance** | FCR · AHT · escalation rate · sentiment improved · avoidable rate |
| **Prioritised Action Plan** | Traffic-signal table: CRITICAL / HIGH / QUICK WIN with initiative, scope, impact, next step |
| **Performance Trends** | FCR/AHT/QA trend charts (visible after 2+ pipeline runs) |

---

## Project structure

```
telecom-call-intelligence/
│
├── pipeline/
│   ├── config.py               ← Single source of truth for all constants
│   ├── security.py             ← InputSanitizer, OutputSanitizer, AgentScopeGuard,
│   │                               SecretGuard, RateLimiter — full security layer
│   ├── decision_log.py         ← DecisionRecord, DecisionLogger, summarize_decisions
│   │                               — agent reasoning audit trail
│   ├── vector_memory.py        ← Semantic KPI memory (Gemini embeddings + cosine sim)
│   ├── agents/
│   │   ├── data_agent.py           ← Agent 1: DataIngestionAgent
│   │   ├── extraction_agent.py     ← Agent 2: ExtractionAgent (Claude Haiku + ReAct)
│   │   ├── quality_agent.py        ← Agent 3: QualityAgent (100-pt QA scoring)
│   │   ├── aggregation_agent.py    ← Agent 4: AggregationAgent (KPIs + cost levers)
│   │   ├── insights_agent.py       ← Agent 5: InsightsAgent (NVIDIA NIM deliberation)
│   │   └── export_agent.py         ← Agent 6: ExportAgent (CSV/JSON/decisions/audit)
│   ├── graph.py                ← LangGraph StateGraph (7 nodes, conditional routing,
│   │                               approval gate, LangSmith tracing)
│   ├── orchestrator.py         ← WorkPlanner, AgentHealthMonitor, adaptive retry
│   ├── governance.py           ← BudgetGuard, QualityGate, PIIScanner, AuditLog
│   ├── memory.py               ← Persistent cross-run flat JSON agent memory
│   ├── tools.py                ← Formal tool registry with JSON schemas
│   ├── analyzer.py             ← LLM client (Claude/Gemini, CoT, ReAct, checkpoint)
│   ├── aggregator.py           ← KPI computation + cost-lever estimates
│   ├── hf_loader.py            ← CSV/HuggingFace streaming + offset batching
│   ├── token_tracker.py        ← Model-aware token cost accounting
│   └── logger.py               ← Structured logging (INFO→stdout, DEBUG→file)
│
├── tests/                      ← 224 unit tests (zero API calls, < 7 seconds)
│   ├── test_config.py
│   ├── test_decision_log.py    ← 24 decision traceability tests
│   ├── test_governance.py
│   ├── test_memory.py
│   ├── test_orchestrator.py
│   ├── test_tools.py
│   ├── test_graph.py
│   └── test_security.py        ← 51 security tests
│
├── dashboard/app.py            ← Streamlit executive dashboard (8 sections)
├── api/main.py                 ← FastAPI wrapper (/health, /summary, /analyze)
├── prompts/system_prompt.txt   ← 70-field extraction schema + CoT instructions
│
├── run_pipeline.py             ← Single-batch entry point (model-aware key validation)
├── run_batches.py              ← Multi-batch orchestrator (5 × 20 default)
├── merge_outputs.py            ← Merge batch JSONs into combined dataset
├── qa_audit.py                 ← Standalone QA scoring tool
│
├── pyproject.toml              ← ruff, mypy, pytest configuration
├── Makefile                    ← Developer shortcuts
├── CLAUDE.md                   ← AI assistant guide
├── ARCHITECTURE.md             ← Full technical reference
├── SECURITY.md                 ← Threat model, PII policy, disclosure process
└── CHANGELOG.md                ← Versioned history (v0.1 → v4.0)
```

---

## Extending to enterprise data

```python
# 1. Replace the data loader with your source
# pipeline/agents/data_agent.py — swap load_telecom_transcripts()
# with your Genesys, S3, Snowflake, SFTP, or Twilio connector.
# Transcripts need: call_id, transcript_text, call_date

# 2. Switch models in one line
# pipeline/config.py → EXTRACTION_MODEL = "claude-opus-4-7"
# All downstream pricing, clients, rate limiters update automatically.

# 3. Calibrate cost model to your actuals
# pipeline/aggregator.py → COST_PER_CALL_USD = <your figure>

# 4. Add domain-specific enums to the extraction schema
# prompts/system_prompt.txt → intent categories, cost_driver taxonomy, etc.
```

The 7-node architecture is designed for this. Only `data_agent.py` changes when you swap data sources. QA, aggregation, insights, security, and export are data-source agnostic.

---

## Dataset

**[`talkmap/telecom-conversation-corpus`](https://huggingface.co/datasets/talkmap/telecom-conversation-corpus)** — MIT License

3.73M turns · ~200K conversations · synthetic telecom customer care (realistic, not real recordings). Pre-downloaded to `telecom_200k.csv` for zero-latency local runs; HuggingFace streaming activates automatically when the local file is absent.

---

## Further reading

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — Multi-agent design, agentic control loops, decision traceability, security layer, state schema
- [`SECURITY.md`](SECURITY.md) — Threat model, PII handling, API key security, vulnerability disclosure
- [`CHANGELOG.md`](CHANGELOG.md) — Version history from v0.1 to v4.1

---

## Built by

**Vinoth N** — AI systems engineer with hands-on experience designing and shipping production-grade autonomous agentic AI systems.

This project demonstrates complete ownership of a v4.0 agentic AI system aligned with Anthropic's agentic AI framework: ReAct control loops, Chain-of-Thought prompting, self-reflective deliberation, decision traceability, semantic vector memory, multi-layer security, plug-and-play model architecture, LangGraph orchestration, LLM prompt engineering, quality assurance, governance, observability, and developer tooling — built at the standard a production agentic AI company would actually ship.

**Open to partnerships in building the agentic AI future:**

| Mode | What that looks like |
|------|---------------------|
| **Employee** | AI/ML Engineer · LLM Platform Engineer · Agentic Systems Engineer at an AI-first company |
| **Co-founder** | Technical co-founder for an agentic AI or enterprise SaaS venture |
| **Consultant** | Agentic AI system design · LLM pipeline architecture · multi-agent frameworks (LangGraph, Claude, NVIDIA NIM) |
| **Contract** | Fixed-scope delivery: pipeline builds, LLM integrations, autonomous agent systems |

📧 **vinoth.n@outlook.com**

---

## License

Copyright © 2026 Vinoth N. All rights reserved. Proprietary — not open source.

Dataset: `talkmap/telecom-conversation-corpus` — MIT License (original authors).
