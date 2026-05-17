# Telecom Call Intelligence — Technical Architecture

## System Overview

An end-to-end **multi-agent pipeline** that ingests raw telecom call transcripts from a public
HuggingFace corpus, extracts 70+ structured metadata fields per call using an LLM, scores
extraction quality inline, synthesises KPIs and LLM-generated recommendations, and serves
an executive analytics dashboard.

```
HuggingFace Streaming Dataset
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│           LangGraph StateGraph  ·  Multi-Agent Pipeline v2.0     │
│                                                                  │
│  ┌─────────────────┐     ┌─────────────────┐                    │
│  │ DataIngestion   │────▶│  Extraction     │                    │
│  │ Agent  (1/6)    │     │  Agent  (2/6)   │                    │
│  │                 │     │  Gemini 2.5     │                    │
│  │ fetch + validate│     │  Flash Lite     │                    │
│  └─────────────────┘     └────────┬────────┘                    │
│                                   │                              │
│                                   ▼                              │
│  ┌─────────────────┐     ┌─────────────────┐                    │
│  │  Aggregation    │◀────│  Quality        │                    │
│  │  Agent  (4/6)   │     │  Agent  (3/6)   │                    │
│  │                 │     │                 │                    │
│  │  KPIs + cost    │     │  100-pt scoring │                    │
│  └────────┬────────┘     └─────────────────┘                    │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐     ┌─────────────────┐                    │
│  │  Insights       │────▶│  Export         │                    │
│  │  Agent  (5/6)   │     │  Agent  (6/6)   │                    │
│  │                 │     │                 │                    │
│  │  Gemini LLM     │     │  CSV + JSON +   │                    │
│  │  recommendations│     │  manifest       │                    │
│  └─────────────────┘     └────────┬────────┘                    │
└──────────────────────────────────┼─────────────────────────────┘
                                   │
                          outputs/ directory
                          summary.json          ← Streamlit dashboard
                          call_results_{ts}.csv
                          full_results_{ts}.json
                          qa_report_{ts}.json
                          insights_{ts}.json
                          run_manifest_{ts}.json
                                   │
                                   ▼
                         Streamlit Dashboard
```

---

## Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Orchestration** | LangGraph `StateGraph` | Explicit state schema; each agent is a pure function; compiled graph is inspectable; trivial to parallelise with `Send` API |
| **LLM (Extraction)** | Google Gemini 2.5 Flash Lite | Native `response_mime_type="application/json"` — no fence-stripping; `thinking_budget=0` maximises output tokens for the 70-field JSON; 15 RPM free tier |
| **LLM (Insights)** | Google Gemini 2.5 Flash Lite | Second agent-role: synthesises KPIs into strategic recommendations — different prompt, different temperature (0.3), same model |
| **Dataset** | HuggingFace `talkmap/telecom-conversation-corpus` | 3.73M turns, 200K conversations, MIT-licensed, real telecom call data |
| **Streaming** | `datasets` streaming mode | Never loads the full corpus into memory; bounded RAM regardless of size |
| **QA Scoring** | Custom 100-pt model | Completeness(30) + Enum validity(25) + Consistency(25) + Plausibility(20); runs inline after extraction |
| **Dashboard** | Streamlit + Plotly | Python-native; executive KPI displays; reads `summary.json` |
| **Logging** | Python `logging` | INFO→stdout, DEBUG→`outputs/pipeline.log`; no external dependencies |

---

## Agent Design

Each agent is a **stateless class** with a single `run(state: dict) -> dict` method.
Agents are decoupled from the graph — swapping, replacing, or parallelising them
requires only changes to `pipeline/graph.py`.

### Agent 1 — DataIngestionAgent (`pipeline/agents/data_agent.py`)

**Responsibilities:** Streaming acquisition + quality gating before inference.

**Streaming strategy** — avoids loading all 3.73M rows:
1. Stream rows until `(offset + n) × 6` unique `conversation_id` values are seen.
2. Sort IDs lexicographically → stable global ordering.
3. Slice `[offset : offset + n×6]` to skip previously-processed conversations.
4. `random.sample(slice, n, seed)` → final selection.

**Quality gates (rejections logged to `validation_errors`):**
- `transcript_text` must be non-empty
- Minimum 150 characters
- Minimum 4 dialogue turns

**Outputs:** `raw_transcripts`, `validated_transcripts`, `validation_errors`

---

### Agent 2 — ExtractionAgent (`pipeline/agents/extraction_agent.py`)

**Responsibilities:** Drive Gemini API calls for all validated transcripts.

**Key design decisions:**
- `response_mime_type="application/json"` — native JSON mode guarantees valid JSON, eliminating fence-stripping and format retries
- `thinking_budget=0` — disables Gemini 2.5's thinking step so the full `max_output_tokens=8192` budget is available for the 70-field JSON output
- `temperature=0.1` — near-deterministic; reduces hallucination on enum fields

**Rate-limit handling:**
- Exponential backoff on 429: `30s → 60s → 120s`
- Linear backoff on 5xx server errors
- After `max_retries=3` permanent failures, call ID recorded in `failed_call_ids`

**Checkpoint/resume:**
- Each successful result immediately appended to `outputs/.checkpoint_{key}.jsonl`
- On restart with same flags, already-analysed calls are loaded and skipped
- Checkpoint deleted automatically on clean (zero-failure) completion

**Token injection per result:**
```python
result["_prompt_tokens"]     = response.usage_metadata.prompt_token_count
result["_completion_tokens"] = response.usage_metadata.candidates_token_count
result["_total_tokens"]      = response.usage_metadata.total_token_count
```

**Outputs:** `analysis_results`, `failed_call_ids`

---

### Agent 3 — QualityAgent (`pipeline/agents/quality_agent.py`)

**Responsibilities:** Inline 100-point QA scoring before aggregation.

**Scoring model:**

| Dimension | Points | What is checked |
|-----------|--------|-----------------|
| Completeness | 30 | 19 required fields are non-null / non-empty |
| Enum validity | 25 | String fields match their allowed value sets |
| Consistency | 25 | Cross-field rules (FCR ≠ escalation, upsell intent vs outcome, etc.) |
| Plausibility | 20 | Duration [30–7200s], non-negative counts, issue count in [0,5] |

**Grade bands:**
- `HIGH` ≥ 85 → production-grade
- `MEDIUM` 60–84 → usable with minor gaps
- `LOW` < 60 → excluded from aggregation

**Dataset verdict:** PASS if ≥90% of calls score ≥60.

**QA enrichment:** Every result dict receives `_qa_score`, `_qa_grade`, `_qa_n_issues`,
`_qa_dimensions` before being passed downstream.

**Outputs:** `analysis_results` (QA-enriched), `qa_report`, `qa_passed_results`

---

### Agent 4 — AggregationAgent (`pipeline/agents/aggregation_agent.py`)

**Responsibilities:** Executive KPI computation from QA-passed results.

Operates on `qa_passed_results` (LOW-grade records excluded). Falls back to the
full `analysis_results` set if QA was skipped.

**KPIs computed:**
- First Call Resolution (FCR) rate
- Average Handle Time (AHT)
- Escalation rate
- Avoidable call rate
- Agentic AI resolvability rate
- Repeat call risk distribution
- Customer sentiment improvement rate
- Phase-level duration breakdown
- Cost-lever savings opportunity (at $6.00/call industry benchmark)

**Outputs:** `aggregated_metrics`, `token_usage`

---

### Agent 5 — InsightsAgent (`pipeline/agents/insights_agent.py`)

**Responsibilities:** The second LLM agent — synthesises KPIs into strategic recommendations.

Unlike ExtractionAgent (which reads individual transcripts one-by-one), InsightsAgent
operates on the **aggregated view** of all calls and reasons cross-functionally about
cost reduction, CX improvement, and automation opportunities.

**LLM call parameters:**
- Model: `gemini-2.5-flash-lite`
- Temperature: `0.3` (more creative than extraction)
- Structured JSON output: `executive_summary`, `top_recommendations` (5), `quick_wins` (3), `risk_flags` (2)

**Graceful degradation:** If Gemini quota is exhausted, a rule-based fallback derives
insights directly from KPI thresholds — the pipeline always completes.

**Outputs:** `agent_insights`

---

### Agent 6 — ExportAgent (`pipeline/agents/export_agent.py`)

**Responsibilities:** Persist all outputs and write the immutable audit trail.

| File | Purpose |
|------|---------|
| `call_results_{ts}.csv` | Per-call flat CSV for BI tools / analysts |
| `summary.json` | Streamlit dashboard source of truth (overwritten each run) |
| `full_results_{ts}.json` | Complete per-call JSON with QA scores embedded |
| `qa_report_{ts}.json` | Standalone QA audit report |
| `insights_{ts}.json` | InsightsAgent recommendations |
| `run_manifest_{ts}.json` | Immutable audit record: all counts, agent list, file paths |

**Outputs:** `export_paths`

---

## State Schema

```python
class PipelineState(TypedDict):
    # Run configuration
    n_calls:               int
    seed:                  int
    offset:                int
    inter_call_delay:      float
    checkpoint_key:        str

    # Agent outputs (in execution order)
    raw_transcripts:       list   # DataIngestionAgent
    validated_transcripts: list   # DataIngestionAgent
    analysis_results:      list   # ExtractionAgent → enriched by QualityAgent
    qa_report:             dict   # QualityAgent
    qa_passed_results:     list   # QualityAgent
    aggregated_metrics:    dict   # AggregationAgent
    agent_insights:        dict   # InsightsAgent
    export_paths:          dict   # ExportAgent

    # Telemetry
    validation_errors:     list
    failed_call_ids:       list
    token_usage:           dict
```

---

## Batch Orchestration

```
run_batches.py
  │
  ├── Batch 1: python run_pipeline.py --offset 0  --n 20  → checkpoint_offset0_n20_seed42
  ├── Batch 2: python run_pipeline.py --offset 20 --n 20  → checkpoint_offset20_n20_seed42
  ├── Batch 3: python run_pipeline.py --offset 40 --n 20  → checkpoint_offset40_n20_seed42
  ├── Batch 4: python run_pipeline.py --offset 60 --n 20  → checkpoint_offset60_n20_seed42
  └── Batch 5: python run_pipeline.py --offset 80 --n 20  → checkpoint_offset80_n20_seed42
          │
          └── merge_outputs.py   → full_results_combined_{ts}.json
                  │
                  └── qa_audit.py  → qa_report_{ts}.json
```

Each batch runs sequentially in a subprocess, respects the free-tier rate limit
(15 RPM with 2s inter-call delay), and produces independent checkpoint files.
Interrupted batches resume automatically with no duplicate API calls.

---

## File Structure

```
telecom-call-intelligence/
├── pipeline/
│   ├── agents/                   ← Multi-agent layer
│   │   ├── __init__.py
│   │   ├── data_agent.py         ← Agent 1: DataIngestionAgent
│   │   ├── extraction_agent.py   ← Agent 2: ExtractionAgent
│   │   ├── quality_agent.py      ← Agent 3: QualityAgent
│   │   ├── aggregation_agent.py  ← Agent 4: AggregationAgent
│   │   ├── insights_agent.py     ← Agent 5: InsightsAgent
│   │   └── export_agent.py       ← Agent 6: ExportAgent
│   ├── graph.py                  ← LangGraph orchestrator
│   ├── analyzer.py               ← Gemini API client (used by ExtractionAgent)
│   ├── aggregator.py             ← KPI computation (used by AggregationAgent)
│   ├── hf_loader.py              ← HuggingFace streaming (used by DataIngestionAgent)
│   ├── token_tracker.py          ← Token accounting
│   └── logger.py                 ← Structured logging
├── prompts/
│   └── system_prompt.txt         ← 70-field extraction prompt
├── dashboard/
│   └── app.py                    ← Streamlit dashboard
├── run_pipeline.py               ← Single-batch entry point
├── run_batches.py                ← Multi-batch orchestrator
├── merge_outputs.py              ← Batch merge utility
├── qa_audit.py                   ← Standalone QA audit tool
└── outputs/                      ← All pipeline outputs (gitignored)
```

---

## Design Principles

1. **Stateless agents** — each agent receives state, produces updated state, holds no instance data. Safe to instantiate once and reuse.

2. **Immutable state handoff** — every agent returns `{**state, new_key: new_value}`. No mutation; any agent can be replayed in isolation.

3. **Graceful degradation** — InsightsAgent falls back to rule-based insights when the LLM is unavailable. QualityAgent skips with a warning on empty input. The pipeline always completes.

4. **Observable** — every agent logs at INFO level with its name prefix `[AgentName]`. DEBUG level captures full token counts per call.

5. **Composable** — to parallelise ExtractionAgent, replace `extract_node` with a LangGraph `Send`-based fan-out. No other files change.

6. **Audit trail** — the run manifest records every agent executed, all file paths, counts, QA verdict, and token cost. Reproducible with the same `(offset, n, seed)` triple.
