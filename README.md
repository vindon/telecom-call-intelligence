# Telecom Call Intelligence

> A production-grade **autonomous multi-agent AI pipeline** built on Claude's Agentic AI framework — turning raw telecom call transcripts into board-ready intelligence. Every call analysed. Every decision traceable. Every stage secured and governed.

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Streamlit-CD040B?logo=streamlit&logoColor=white)](https://telecom-call-intelligence.streamlit.app/)
[![CI](https://github.com/vindon/telecom-call-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/vindon/telecom-call-intelligence/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-4A90D9)
![Claude](https://img.shields.io/badge/Claude-Haiku%204.5-CC785C?logo=anthropic&logoColor=white)
![NVIDIA](https://img.shields.io/badge/NVIDIA-NIM%20LLaMA--3.3--70B-76B900?logo=nvidia&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-399%20passing-22C55E)
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
│              LangGraph StateGraph  ·  Multi-Agent Pipeline v4.5           │
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
| **Process isolation** | `run_batches.py` → `Orchestrator` → N subprocesses | A crashed batch cannot corrupt other batches; the first failure halts the entire run and requires explicit human review (`--acknowledge-halt`) — no silent auto-retry |
| **399 unit tests** | Security, governance, decision log, memory, orchestrator, LLM clients, circuit breaker, config, graph — all tested without API calls | CI completes in under 7 seconds; tests gate every push to main |

---

## Model architecture

| Role | Primary | Fallback 1 | Fallback 2 |
|------|---------|-----------|-----------|
| **Extraction** (70 fields/call) | Claude Haiku 4.5 | Gemini 2.0 Flash Lite | — |
| **Insights** (strategic recs) | NVIDIA NIM `llama-3.3-70b-instruct` | Claude Haiku 4.5 | Rule-based |
| **Embeddings** (vector memory) | Gemini `text-embedding-004` | TF-IDF bag-of-words (offline) | — |

**Switching models:** Change `EXTRACTION_MODEL` in `pipeline/config.py` — all API clients, rate limiters, cost estimates, provider labels, and budget guards update automatically.

---

## Results (representative single-batch run)

Pipeline mechanics for a typical single run — cost, runtime, extraction reliability. For the cumulative, honest **pass/fail picture across every call this pipeline has ever processed** (the number that actually gates cost-lever accuracy), see "Proven at scale" below — the two are answering different questions and are not the same metric.

| Metric | Value |
|--------|-------|
| Calls analysed | 100 |
| Fields extracted per call | 70+ |
| **QA Score** pass rate (HIGH+MEDIUM — extraction was well-formed; *not* the Data Quality Gate, see below) | Typically 90–99% |
| Avg QA Score | 85–99 / 100 |
| Pipeline runtime | ~8 min (5 × 20 batches, 2s inter-call delay) |
| Extraction cost (Claude Haiku) | ~$0.76 / 100 calls (~$0.0076/call) |
| Extraction cost (Gemini free tier) | ~$0.00 / 100 calls (free-tier eligible) |
| Deliberation passes | 3 per insights run |
| Decision records per run | 15–60 traceable decisions |
| Test suite | 399 tests · < 7 seconds |
| Checkpoint overhead | Zero — resume is instantaneous |

---

## Proven at scale — the data-quality story, told honestly

**Two separate checks decide whether a call counts, and they answer different questions:**

| | QA Score | Data Quality Gate |
|---|---|---|
| **Question it answers** | Did the LLM extract this call's 70+ fields correctly? | Can this call's *time data* be trusted for AHT and cost-lever attribution? |
| **Scale** | 0–100, weighted rubric | Pass / fail, 3 deterministic checks |
| **What it checks** | Field completeness, enum validity, cross-field consistency, plausibility | Phase-time reconciliation, timestamp ground-truth vs. the source recording, transcript completeness |
| **Can it be gamed by a well-formed extraction?** | — | No — a call can score 100/100 on the left and still fail here |

They're kept separate on purpose. A 100-pt QA score only tells you the extraction was *structurally* well-formed — every field populated, every enum valid. It doesn't tell you whether the model's own phase-by-phase time math actually adds up, whether the input transcript was complete, or whether the stated call length matches the source recording. Most AI call-analytics tools never check that second thing. This one does, on every call, with three deterministic (non-LLM) checks — see [`qa_audit.check_data_quality()`](qa_audit.py).

**Why the Data Quality Gate exists — it protects the product's core value proposition.** Every cost-lever dollar figure this product produces (Cost to Serve / Cost to Sell / Cost to Retain, and the enterprise cost-to-serve projection) is computed by [`aggregator.py::_phase_pnl()`](pipeline/aggregator.py) as a direct proportion of each call's phase-duration fields. If a call's phase times don't reconcile and it isn't excluded, its minutes get misattributed across those buckets and every downstream dollar figure is wrong by the same proportion — silently, since a well-formed (high-QA-Score) extraction wouldn't flag it. The product's success is defined as *near-accurate representation of AHT segmented by cost lever* — this gate is the mechanism that makes that claim defensible instead of asserted.

**This is the project's success criterion, stated plainly:** of every call this pipeline has processed, **172 pass every QA and data-integrity check — that's the number the product stands behind.** The other 45 don't get silently averaged in; each is excluded with one of three specific, logged reasons. That's not a defect to explain away — it's what strict validation looks like when it's actually enforced in code instead of asserted in a slide. The failure modes below are exactly the constraints any team will hit processing real, messy transcripts at volume; naming them here is what lets an enterprise buyer plan mitigations *before* they show up in a production AHT number, not after.

**Real numbers, across every batch run to date** (live from `outputs/summary.json`, not a cherry-picked example):

| | |
|---|---|
| Calls processed | **217** |
| Extraction success rate | **100%** — zero technical/LLM failures |
| **Fully trusted — meets the product's success criteria** (QA score + all 3 data-integrity checks) | **172 (79.3%)** |
| Excluded, each with a specific logged reason | 45 |

**Why calls get excluded** — three specific, auditable constraints, not a vague error rate. Each recurs at enterprise scale and each has a known mitigation:

| Reason | Count | What it actually means | Mitigation at scale |
|---|---|---|---|
| Phase-time reconciliation | 33 | The model's own phase breakdown didn't sum to its stated total call length — a reasoning imperfection | Route to human QA review before it feeds AHT/cost aggregates; track as a model-quality metric over time |
| Transcript truncation | 15 | The model flagged the input itself as cut off — a data-pipeline issue, not an extraction failure | Fix upstream capture/storage completeness; truncated calls should never reach the model in the first place |
| Timestamp ground-truth mismatch | 1 | Stated call length didn't match the source recording's real timestamps — rarest, most serious | Cross-check against telephony system timestamps as a hard gate before any staffing/cost decision |

**At enterprise scale (100K calls/month):** ~79,300 calls/month get fully automated, board-ready analytics with zero human review. ~20,700/month are correctly routed to review instead of silently corrupting the aggregate AHT numbers — that gating, enforced in code at the aggregation layer (not a caveat in a doc), is the actual product. A pipeline that skipped these checks wouldn't have fewer problems at scale; it would just report a false 100% while quietly baking bad phase math into every downstream cost model.

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
make test          # 399 unit tests — no API calls required (< 7 seconds)
make lint          # ruff linter across all source files
make check         # lint + type-check + test (full pre-push gate)
make test-cov      # tests with HTML coverage report
make dashboard     # Streamlit dashboard on localhost:8501
make demo          # standalone live demo app on localhost:8001
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

The executive dashboard (`dashboard/app.py`) is a professional light-theme Streamlit application with 6 sections, reading live from `outputs/summary.json`. Falls back to built-in demo data when no pipeline output is present.

```bash
streamlit run dashboard/app.py   # http://localhost:8501
```

| Section | Content |
|---------|---------|
| **Hero** | "Telecom Cost Intelligence for Care Calls" — eyebrow, headline, and subline sourced from live analysis |
| **Cost Panels** | *Insights from N Calls Analysed* (Cost to Serve P1–P4 / Cost to Sell P5 / Cost to Retain — allocated by phase-time share of AHT) · *AI Recovery Opportunity* (monthly saving vs baseline) |
| **1 — The Evidence** | Issue category bar chart · phase-time waterfall |
| **2 — Phase Drill-Down** | Per-phase tabs (Discovery/Diagnosis/Resolution/Upsell) — top-5 intents by avg phase duration, with agent stall rate |
| **3 — Resolution Opportunity** | PREVENT · AUTOMATE · HUMAN REQUIRED — with cost impact per segment |
| **4 — AI Agents to Build** | Ranked roadmap: intent · calls/month · saving/month · build effort |
| **5 — Actual Performance** | FCR · AHT · escalation rate · sentiment improved · avoidable rate |
| **6 — Issue Tree** | Per-call-type breakdown: what the agent did (`issue_1_resolution_method`) → Prevent / Automate / Human segment attribution → ranked build queue (top-4 opportunities by monthly $ impact) + full-picture overview bar |

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
│   ├── orchestrator.py         ← WorkPlanner, AgentHealthMonitor, strict halt-on-failure policy
│   ├── governance.py           ← BudgetGuard, QualityGate, PIIScanner, AuditLog
│   ├── memory.py               ← Persistent cross-run flat JSON agent memory
│   ├── vector_memory.py        ← Semantic KPI-similarity memory (embeds each run)
│   ├── llm_clients.py          ← Single seam for Anthropic/Gemini/NVIDIA client construction
│   ├── circuit_breaker.py      ← Shared provider-unavailability breaker
│   ├── analyzer.py             ← LLM client (Claude/Gemini, CoT, ReAct, checkpoint)
│   ├── aggregator.py           ← KPI computation + cost-lever estimates
│   ├── hf_loader.py            ← CSV/HuggingFace streaming + offset batching
│   ├── token_tracker.py        ← Model-aware token cost accounting
│   └── logger.py               ← Structured logging (INFO→stdout, DEBUG→file)
│
├── tests/                      ← 399 unit tests (zero API calls, < 7 seconds)
│   ├── test_agents/             ← per-agent unit tests (data, extraction, quality, aggregation, insights, export)
│   ├── test_config.py
│   ├── test_decision_log.py    ← decision traceability tests
│   ├── test_governance.py
│   ├── test_hf_loader.py       ← offset-disjointness / sampling regression tests
│   ├── test_memory.py
│   ├── test_orchestrator.py    ← strict halt-on-failure policy tests
│   ├── test_qa_audit_phase_reconciliation.py  ← sequential vs. overlay phase reconciliation tests
│   ├── test_llm_clients.py
│   ├── test_circuit_breaker.py
│   ├── test_graph.py
│   └── test_security.py        ← security module tests
│
├── dashboard/app.py            ← Streamlit executive dashboard (4 tabs: Cost to Serve, Automation Strategy, QA & Pipeline Health, Live Pipeline Demo)
├── demo/
│   ├── app.py                  ← Standalone live demo (FastAPI) — transcript input → 6-agent pipeline → dashboard
│   └── index.html              ← Self-contained demo UI (no build step)
├── docs/
│   └── executive_deck.html     ← BCG-style 13-slide cost intelligence deck — the single source of truth for economics/success-metrics narrative
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
└── CHANGELOG.md                ← Versioned history (v0.1 → v4.5)
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
- [`CHANGELOG.md`](CHANGELOG.md) — Version history from v0.1 to v4.5

---

## Built by

**Vinoth N** — AI systems engineer with hands-on experience designing and shipping production-grade autonomous agentic AI systems.

This project demonstrates complete ownership of a v4.5 agentic AI system aligned with Anthropic's agentic AI framework: ReAct control loops, Chain-of-Thought prompting, self-reflective deliberation, decision traceability, semantic vector memory, multi-layer security, plug-and-play model architecture, LangGraph orchestration, LLM prompt engineering, quality assurance, governance, observability, and developer tooling — built at the standard a production agentic AI company would actually ship.

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
