# Telecom Call Intelligence

> Production-grade **multi-agent LLM pipeline** that extracts 70+ structured KPIs from telecom customer care transcripts, scores extraction quality inline, generates LLM-powered strategic recommendations, and delivers an executive analytics dashboard for cost-to-serve optimisation.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2%2B-4A90D9)
![Gemini](https://img.shields.io/badge/Gemini-2.5%20Flash%20Lite-4285F4?logo=google&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.35%2B-FF4B4B?logo=streamlit&logoColor=white)
![License](https://img.shields.io/badge/License-Proprietary-DC2626)
![Status](https://img.shields.io/badge/Status-Production-22C55E)

---

## What this is

Most contact centres analyse 2–5% of calls manually. This pipeline analyses **100%** — automatically extracting structured intelligence from every transcript, validating extraction quality, and surfacing it as executive-ready KPIs with AI-generated strategic recommendations.

Built on a **6-agent LangGraph** state graph, it streams from a public HuggingFace corpus, runs each transcript through **Gemini 2.5 Flash Lite**, scores every extraction with a 100-point QA model, and uses a second LLM agent to synthesise aggregated KPIs into prioritised recommendations — all in a single pipeline invocation.

```
HuggingFace Streaming Dataset
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│           LangGraph  ·  Multi-Agent Pipeline v2.0                │
│                                                                  │
│  ┌──────────────────┐      ┌──────────────────┐                 │
│  │ DataIngestion    │─────▶│  Extraction      │                 │
│  │ Agent  (1/6)     │      │  Agent  (2/6)    │                 │
│  │ fetch + validate │      │  Gemini · 70 fields              │ │
│  └──────────────────┘      └────────┬─────────┘                 │
│                                     │                            │
│                                     ▼                            │
│  ┌──────────────────┐      ┌──────────────────┐                 │
│  │  Aggregation     │◀─────│  Quality         │                 │
│  │  Agent  (4/6)    │      │  Agent  (3/6)    │                 │
│  │  KPIs + levers   │      │  100-pt scoring  │                 │
│  └────────┬─────────┘      └──────────────────┘                 │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐      ┌──────────────────┐                 │
│  │  Insights        │─────▶│  Export          │                 │
│  │  Agent  (5/6)    │      │  Agent  (6/6)    │                 │
│  │  Gemini · recs   │      │  CSV+JSON+reports│                 │
│  └──────────────────┘      └────────┬─────────┘                 │
└────────────────────────────────────┼────────────────────────────┘
                                     │
                           outputs/summary.json ── Streamlit Dashboard
```

---

## Key features

| Feature | Description |
|---------|-------------|
| **6-agent architecture** | Specialized agents for ingestion, extraction, QA, aggregation, insights, and export — decoupled and independently replaceable |
| **Dual LLM agents** | ExtractionAgent extracts per-call JSON; InsightsAgent synthesises cross-call strategic recommendations — different prompts, roles, and temperatures |
| **Inline QA scoring** | QualityAgent scores every extraction on completeness, enum validity, consistency, and plausibility (100 pts) before aggregation |
| **70-field extraction** | Phase durations, FCR, escalation, sentiment, upsell outcome, agent skill, cost drivers per call |
| **Checkpoint / resume** | Each successful API call persisted immediately — a killed process loses nothing |
| **Batch orchestration** | `run_batches.py` runs N×M batches with process isolation, auto-merge, and post-run QA audit |
| **Token cost tracking** | Every result carries `_prompt_tokens/_completion_tokens` and cumulative USD cost |
| **Executive dashboard** | 9-panel Streamlit app with cost waterfall, phase breakdown, and deflection analysis |
| **Graceful degradation** | InsightsAgent falls back to rule-based recommendations if LLM quota is exhausted |

---

## Quick start

### Prerequisites

- Python 3.11+
- A free [Groq API key](https://console.groq.com) (30 req/min, no credit card required)

### Install

```bash
git clone https://github.com/vindon/telecom-call-intelligence.git
cd telecom-call-intelligence

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Open .env and set GROQ_API_KEY=gsk_...
```

### Run

```bash
# 3-call smoke test (confirms everything works end-to-end in ~30 seconds)
python run_pipeline.py --n 3

# Full 100-call run via 5 parallel-safe batches (recommended)
python run_batches.py --batches 5 --n 20

# Single 100-call run
python run_pipeline.py --n 100

# Launch dashboard (works immediately with demo data, or live data after a run)
streamlit run dashboard/app.py
```

---

## Project structure

```
telecom-call-intelligence/
│
├── run_pipeline.py          ← Single-batch entry point
├── run_batches.py           ← Multi-batch orchestrator (5×20 = 100 calls)
├── merge_outputs.py         ← Merge batch JSONs → combined dataset
├── qa_audit.py              ← QA scoring engine (100-point scale)
│
├── pipeline/
│   ├── hf_loader.py         ← HuggingFace streaming + offset-based batching
│   ├── analyzer.py          ← Groq API calls + token tracking + checkpoint saves
│   ├── aggregator.py        ← KPI computation + cost-lever estimates
│   ├── graph.py             ← LangGraph 5-node StateGraph
│   ├── token_tracker.py     ← Per-call token cost accounting
│   └── logger.py            ← Structured logging (INFO→stdout, DEBUG→file)
│
├── dashboard/
│   └── app.py               ← Streamlit executive dashboard (9 panels)
│
├── prompts/
│   └── system_prompt.txt    ← 70-field LLM extraction schema + rules
│
├── docs/
│   └── executive_summary_template.md   ← Presentation template for stakeholders
│
├── ARCHITECTURE.md          ← Full technical reference
├── PRD.md                   ← Product Requirements Document
│
└── outputs/                 ← Generated at runtime (gitignored except summary.json)
    ├── summary.json         ← Dashboard data (commit for live demo)
    ├── call_results_*.csv   ← Per-call CSV
    ├── full_results_*.json  ← Full JSON for audit/merge
    ├── qa_report_*.json     ← QA audit output
    └── pipeline.log         ← Structured run log
```

---

## How batching works

```
run_batches.py --batches 5 --n 20
  ├── Batch 1: offset=0,  n=20  → conversations  0–19
  ├── Batch 2: offset=20, n=20  → conversations 20–39
  ├── Batch 3: offset=40, n=20  → conversations 40–59
  ├── Batch 4: offset=60, n=20  → conversations 60–79
  └── Batch 5: offset=80, n=20  → conversations 80–99
       │
       └── merge_outputs.py → combined dataset → qa_audit.py → summary.json
```

Each batch runs as a subprocess. If batch 3 crashes, batches 1–2 results are safe on disk. Restart with the same command — checkpoints automatically skip already-analyzed calls.

---

## Checkpoint / resume

```bash
# Run killed at call 12/20
python run_pipeline.py --n 20 --offset 0 --seed 42

# Restart — loads 12 checkpointed results, analyzes only calls 13–20
python run_pipeline.py --n 20 --offset 0 --seed 42
```

Checkpoints live at `outputs/.checkpoint_{key}.jsonl`. Deleted automatically on clean completion.

---

## QA audit

```bash
python qa_audit.py                    # audit latest results
python qa_audit.py --threshold 70     # stricter pass threshold
```

Scoring dimensions:

| Dimension | Pts | Checks |
|-----------|-----|--------|
| Completeness | 30 | 19 required fields present and non-null |
| Enum validity | 25 | 18 string-enum fields match allowed values |
| Consistency | 25 | 5 cross-field logical rules |
| Plausibility | 20 | Numeric ranges, non-negative durations |

Dataset verdict: **PASS** if ≥ 90% of calls score ≥ 60.

---

## Dashboard panels

| Panel | Insight |
|-------|---------|
| Executive KPIs | AHT, FCR rate, avoidable calls, escalation rate, sentiment lift |
| Cost-to-Serve Levers | Monthly savings from self-serve, agentic AI, proactive outreach |
| Phase Breakdown | Seconds per call phase — where handle time is lost |
| Cost Waterfall | Baseline → optimised cost visualisation |
| Issue Distribution | Volume by issue category |
| Deflection Opportunity | Self-serve, agentic AI, and proactive care eligibility % |
| Agent Performance | Skill distribution, tool struggle %, repeat call risk |
| Sentiment Analysis | Customer sentiment at start vs. end of call |
| Token Usage | Inference cost per run, per-call averages, monthly projection |

---

## Cost model

**Inference (Groq free tier):**

| Metric | Value |
|--------|-------|
| Model | llama-3.3-70b-versatile |
| Input | $0.59 / 1M tokens |
| Output | $0.79 / 1M tokens |
| Cost per 100-call run | ~$0.30 USD |

**Contact centre (illustrative baseline, 100K calls/mo):**

| Lever | Assumption | Est. monthly savings |
|-------|-----------|---------------------|
| Self-serve deflection | 85% cost avoidance | Varies by FCR rate |
| Agentic AI resolution | 70% cost avoidance | Varies by AI-resolvable % |
| Proactive outreach | 60% cost avoidance | Varies by proactive % |

> Replace `COST_PER_CALL_USD = 6.00` and `MONTHLY_VOLUME = 100_000` in `aggregator.py` with your actual figures.

---

## Extending to production data

To run against real enterprise transcripts:

1. Replace `pipeline/hf_loader.py` with your own ingestion layer (S3, Snowflake, ACD export)
2. Ensure transcript format: timestamped turns with `AGENT:` / `CUSTOMER:` labels
3. Populate `agent_id`, `customer_id`, `queue_name` in the user message template (`analyzer.py`)
4. Set `COST_PER_CALL_USD` to your actual cost-to-serve figure
5. Cross-validate `fcr_indicator` against CRM callback records to calibrate the prompt

---

## Configuration

| Flag | Default | Description |
|------|---------|-------------|
| `--n` | 100 | Calls to analyze per run |
| `--seed` | 42 | Reproducible random sample |
| `--offset` | 0 | Skip N conversations (for batching) |
| `--delay` | 2.0 | Seconds between Groq API calls |
| `--batches` | 5 | Number of batches (run_batches.py) |

---

## Dataset

**`talkmap/telecom-conversation-corpus`** — MIT License

| Property | Value |
|----------|-------|
| Size | 3.73M turns · ~200K conversations |
| Schema | `conversation_id`, `speaker`, `date_time`, `text` |
| Domain | Telecom customer service (fictional carrier "Union Mobile") |
| Note | Synthetic dataset — realistic but not real recordings |

---

## Further reading

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — Data flow, LangGraph schema, prompt engineering, rate limiting, scaling
- [`PRD.md`](PRD.md) — Product requirements, goals, success metrics
- [`docs/executive_summary_template.md`](docs/executive_summary_template.md) — Stakeholder presentation template

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for how to run the project locally, submit issues, and open pull requests.

---

## License

Copyright © 2026 Vinoth N. All rights reserved. See [LICENSE](LICENSE).

Dataset: `talkmap/telecom-conversation-corpus` — MIT License (original authors).
