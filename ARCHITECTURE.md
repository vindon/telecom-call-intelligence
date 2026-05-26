# Telecom Call Intelligence — Technical Architecture v3.0

## System Overview

An end-to-end **autonomous multi-agent pipeline** that ingests raw telecom call transcripts,
extracts 70+ structured metadata fields per call using ReAct control loops, scores extraction
quality inline, synthesises KPIs, runs a self-reflective deliberation cycle for strategic
recommendations, and secures every stage against prompt injection and data leakage.

```
HuggingFace Streaming Dataset
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│            LangGraph StateGraph  ·  Multi-Agent Pipeline v3.0       │
│                                                                     │
│  ┌─────────────────┐     ┌──────────────────────────────────────┐  │
│  │ DataIngestion   │────▶│  Extraction Agent  (2/7)             │  │
│  │ Agent  (1/7)    │     │  Gemini · 70 fields · CoT prompt     │  │
│  │ fetch + validate│     │  ┌──────── ReAct loop ─────────────┐ │  │
│  │ PII scan + audit│     │  │ Observe: score_field_coverage   │ │  │
│  └─────────────────┘     │  │ Reason: identify null fields    │ │  │
│                          │  │ Act:    gap-fill targeted call  │ │  │
│                          │  └─────────────────────────────────┘ │  │
│                          └─────────────────┬────────────────────┘  │
│                                            │                        │
│                                            ▼                        │
│  ┌─────────────────┐     ┌─────────────────┐                       │
│  │  Aggregation    │◀────│  Quality        │                       │
│  │  Agent  (4/7)   │     │  Agent  (3/7)   │                       │
│  │  KPIs + cost    │     │  100-pt scoring │                       │
│  └────────┬────────┘     │  dynamic route  │                       │
│           │              └─────────────────┘                       │
│           ▼                                                         │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Insights Agent  (5/7)                                       │  │
│  │  Vector memory retrieval → top-K similar historical runs     │  │
│  │  ┌────────── Deliberation loop ────────────────────────────┐ │  │
│  │  │  Pass 1  Analyze  : CoT KPI analysis → initial insights │ │  │
│  │  │  Pass 2  Critique : self-grade each recommendation      │ │  │
│  │  │  Pass 3  Synthesize: rewrite weak recommendations       │ │  │
│  │  └─────────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────┬──────────────────────────────────┘  │
│                              │                                      │
│                              ▼                                      │
│  ┌─────────────────┐     ┌─────────────────┐                       │
│  │  Approval Gate  │────▶│  Export         │                       │
│  │  (6/7)          │     │  Agent  (7/7)   │                       │
│  │  human sign-off │     │  CSV + JSON +   │                       │
│  │  auto-approve CI│     │  manifest       │                       │
│  └─────────────────┘     └────────┬────────┘                       │
└─────────────────────────────────-─┼────────────────────────────────┘
                                    │
                           outputs/ directory
                           summary.json          ← Streamlit dashboard
                           call_results_{ts}.csv
                           full_results_{ts}.json
                           qa_report_{ts}.json
                           insights_{ts}.json
                           run_manifest_{ts}.json
                           audit_log_{ts}.json
                           vector_memory/        ← semantic KPI store
```

---

## Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Orchestration** | LangGraph `StateGraph` | Explicit state schema; each agent is a pure function; compiled graph is inspectable; `Send` API available for fan-out parallelism |
| **LLM (Extraction)** | Gemini 2.5 Flash Lite | Native JSON mode; `thinking_budget=0` maximises output token budget for 70-field JSON; 15 RPM free tier |
| **LLM (Insights)** | Gemini 2.5 Flash Lite | Three deliberation passes at different temperatures; `response_mime_type="application/json"` throughout |
| **LLM (Embeddings)** | Gemini `text-embedding-004` | 768-dim embeddings for vector memory; same API key, no extra library |
| **Dataset** | HuggingFace `talkmap/telecom-conversation-corpus` | 3.73M turns, 200K conversations, MIT-licensed |
| **Streaming** | `datasets` streaming mode | Never loads the full corpus into memory; bounded RAM regardless of corpus size |
| **QA Scoring** | Custom 100-pt model | Completeness(30) + Enum validity(25) + Consistency(25) + Plausibility(20) |
| **Vector memory** | numpy cosine similarity | Zero extra dependencies; interface-compatible with ChromaDB/Pinecone swap |
| **Tracing** | LangSmith (optional) | `LANGCHAIN_TRACING_V2=true` activates full node-level trace capture |
| **Dashboard** | Streamlit + Plotly | Python-native; reads `summary.json` |

---

## Agentic Control Loops

### ReAct — ExtractionAgent

The standard Reason → Act → Observe loop, applied per-transcript:

```
┌─────────────────────────────────────────────────────────────────┐
│  Initial Act: analyze_transcript() → first_pass result          │
│                       │                                         │
│               Observe: score_field_coverage()                   │
│               (% of critical fields non-null)                   │
│                       │                                         │
│          coverage < REACT_QUALITY_THRESHOLD?                    │
│              │                      │                           │
│             YES                     NO → done                   │
│              │                                                  │
│       Reason: identify null critical fields                     │
│       (_CRITICAL_FIELDS: fcr, resolution_status, sentiments…)  │
│              │                                                  │
│        Act: gap_fill_transcript()                               │
│        (targeted call for missing fields only)                  │
│              │                                                  │
│       Observe: merge + re-score                                 │
│       (repeat up to REACT_MAX_ITERATIONS)                       │
└─────────────────────────────────────────────────────────────────┘
```

Key functions in `pipeline/analyzer.py`:
- `score_field_coverage(result)` — returns 0–100 field coverage score
- `gap_fill_transcript(client, system_prompt, transcript, first_pass)` — targeted retry, merges only null fields
- `_build_gap_fill_message(transcript, missing_fields)` — focused prompt for missing fields only

### Chain-of-Thought — Both LLM Agents

`_cot_reasoning` is the **first field** in every JSON response. Because the LLM must populate this field before the 70 structured fields, it is forced to reason explicitly about the call before committing to values. This is standard CoT embedded in JSON mode — no extra API calls.

```json
{
  "_cot_reasoning": "The customer called about a billing discrepancy on their account.
    The agent investigated and found a duplicate charge, which was successfully
    refunded. Sentiment moved from frustrated to satisfied.",
  "fcr": true,
  "resolution_status": "resolved",
  ...
}
```

The InsightsAgent's `ANALYZE_PROMPT` includes explicit step-by-step reasoning instructions before the recommendations:

```
STEP-BY-STEP REASONING (Chain-of-Thought):
1. Which KPIs are significantly above or below industry benchmarks?
2. What root causes are most likely given the pattern of KPIs together?
3. Which interventions would have the highest ROI given this specific data?
4. What risks are NOT visible in this data but are implied by the patterns?
```

### Self-Reflection Deliberation — InsightsAgent

Three Gemini passes, each with a distinct role:

```
Pass 1 — Analyze (CoT)
  Input : KPI summary + historical context
  Prompt: ANALYZE_PROMPT (CoT instructions embedded)
  Output: initial insights JSON with _cot_reasoning
  Temp  : 0.3

Pass 2 — Critique (self-reflection)
  Input : Pass 1 output + raw KPIs
  Prompt: CRITIQUE_PROMPT
  Task  : Grade each recommendation A/B/C on:
          data-grounded, specific, non-duplicated
  Output: overall_quality + per-recommendation grades
  Temp  : 0.1 (consistent grading)

Pass 3 — Synthesize
  Input : Pass 1 output + Pass 2 critique
  Prompt: SYNTHESIZE_PROMPT
  Task  : Rewrite weak/generic recommendations;
          ensure every recommendation cites a specific KPI
  Output: final improved insights JSON
  Temp  : 0.3
```

Graceful degradation at each pass: if Pass 2 fails, Pass 1 result is returned. If Pass 3 fails, Pass 2 result is returned. If all three fail, rule-based fallback fires. The pipeline always completes.

---

## Security Layer (`pipeline/security.py`)

Every agent boundary is protected by the security layer. No LLM call proceeds without input sanitization; no LLM output reaches downstream agents without output sanitization.

### Threat model

| Threat | Component | Defence |
|--------|-----------|---------|
| Prompt injection in transcript text | `InputSanitizer` | 10 regex patterns; neutralize with `[FILTERED]`, not reject (avoids DoS from single bad record) |
| Token bomb (oversized input) | `InputSanitizer` | Hard cap at `MAX_TRANSCRIPT_CHARS` (50K chars ≈ 12.5K tokens); truncate with marker |
| Encoding attacks (null bytes, replacement chars) | `InputSanitizer` | Strip `\x00` and `�` before LLM |
| Secret leakage in input data | `InputSanitizer` | Google/OpenAI key patterns, JWTs, Bearer tokens → `[SECRET_REDACTED]` |
| Code execution in LLM output | `OutputSanitizer` | `__import__`, `eval`, `exec`, `subprocess`, XSS → `[CONTENT_FILTERED]` |
| Response bomb (oversized LLM output) | `OutputSanitizer` | Hard cap at `MAX_RESPONSE_BYTES` (32 KB); raises `SecurityViolation` before JSON parse |
| Secret leakage in LLM output | `SecretGuard` | Pattern scan before downstream agents receive any LLM text |
| Cross-agent tool hijacking | `AgentScopeGuard` | Per-agent authorized tool set; violation raises `SecurityViolation` before invocation |
| State tampering | `InputSanitizer.validate_state_schema()` | Required keys checked at each agent boundary |
| Runaway API consumption | `RateLimiter` | Sliding-window 15 req/60s acquired before every Gemini call |

### Security call flow

```python
# Every Gemini call in analyzer.py:
transcript = INPUT_SANITIZER.sanitize_transcript(transcript)   # before call
GEMINI_RATE_LIMITER.acquire()                                   # rate check
response = client.models.generate_content(...)
SECRET_GUARD.assert_no_secrets_in_output(response.text)        # after call
OUTPUT_SANITIZER.check_response_size(response.text)            # size check
result = json.loads(response.text)
result = OUTPUT_SANITIZER.sanitize_extraction_result(result)   # field sanitize
```

---

## Vector Memory (`pipeline/vector_memory.py`)

Semantic long-term memory that retrieves the most relevant historical runs for InsightsAgent context — not just chronological averages.

```
Pipeline run completes
        │
        ▼
ExportAgent calls VECTOR_STORE.add_run(run_id, kpi_text, metadata)
        │
        ▼
Gemini text-embedding-004 embeds the KPI summary text (768-dim)
        │  (TF-IDF bag-of-words fallback if no API key — offline/test mode)
        ▼
Stored as row in vectors.npy + entry in index.json
        │
        │  ← next pipeline run ─────────────────────────────────────────┐
        ▼                                                                │
InsightsAgent calls VECTOR_STORE.format_context(current_kpi_text)       │
        │                                                                │
        ▼                                                                │
Cosine similarity search over stored vectors → top-K similar runs       │
        │                                                                │
        ▼                                                                │
"Top-3 similar historical runs (by KPI pattern similarity):             │
  1. [2026-05-18] sim=0.94 — FCR 72% AHT 4.2 min escalation 8%…"       │
        │                                                                │
        ▼                                                                │
Injected into ANALYZE_PROMPT historical context section ────────────────┘
```

The interface is backend-agnostic: replace `VectorMemoryStore._save()/_load()` with ChromaDB or Pinecone calls without changing the public `add_run()` / `query()` API.

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

**Security:** Every transcript passes through `PII_SCANNER.scan_transcript()` and
`INPUT_SANITIZER.sanitize_transcript()` before entering the pipeline.

**Outputs:** `raw_transcripts`, `validated_transcripts`, `validation_errors`

---

### Agent 2 — ExtractionAgent (`pipeline/agents/extraction_agent.py`)

**Responsibilities:** Drive Gemini API calls for all validated transcripts with ReAct loop.

**ReAct loop** (see [Agentic Control Loops](#agentic-control-loops) above for detail):
- Initial extraction via `analyze_batch()` (Act)
- Per-result `score_field_coverage()` (Observe)
- For results below `REACT_QUALITY_THRESHOLD`: `gap_fill_transcript()` (Reason + Act)
- `react_stats` injected into PipelineState for telemetry

**API parameters:**
- `response_mime_type="application/json"` — guaranteed valid JSON
- `thinking_budget=0` — full `max_output_tokens=8192` for 70-field JSON
- `temperature=0.1` — near-deterministic extraction
- `GEMINI_RATE_LIMITER.acquire()` before every call (15 RPM sliding window)

**Backoff:** exponential on 429 (`30s → 60s → 120s`), linear on 5xx

**Outputs:** `analysis_results`, `failed_call_ids`, `react_stats`

---

### Agent 3 — QualityAgent (`pipeline/agents/quality_agent.py`)

**Responsibilities:** Inline 100-point QA scoring before aggregation.

| Dimension | Points | What is checked |
|-----------|--------|-----------------|
| Completeness | 30 | 19 required fields are non-null / non-empty |
| Enum validity | 25 | String fields match their allowed value sets |
| Consistency | 25 | Cross-field rules (FCR ≠ escalation, upsell intent vs outcome, etc.) |
| Plausibility | 20 | Duration [30–7200s], non-negative counts, issue count in [0,5] |

**Grade bands:** `HIGH` ≥ 85 · `MEDIUM` 60–84 · `LOW` < 60 (excluded from aggregation)

**Dataset verdict:** PASS if ≥90% of calls score ≥60.

**Dynamic routing:** if the QualityGate fires (pass rate < 40%), `_quality_gate_failed`
is set in `qa_report` and the graph routes directly to ExportAgent.

**Outputs:** `analysis_results` (QA-enriched), `qa_report`, `qa_passed_results`

---

### Agent 4 — AggregationAgent (`pipeline/agents/aggregation_agent.py`)

**Responsibilities:** Executive KPI computation from QA-passed results.

KPIs computed: FCR rate, AHT, escalation rate, avoidable call rate, agentic AI resolvability,
repeat call risk distribution, sentiment improvement rate, phase-level duration breakdown,
cost-lever savings opportunity (at $6.00/call industry benchmark).

**Outputs:** `aggregated_metrics`, `token_usage`

---

### Agent 5 — InsightsAgent (`pipeline/agents/insights_agent.py`)

**Responsibilities:** The second LLM agent — 3-pass deliberation loop over KPIs.

**Context enrichment before deliberation:**
1. `MEMORY.get_context_for_insights()` — flat run history (avg FCR/AHT trends, quota events)
2. `VECTOR_STORE.format_context(current_kpi_text)` — top-K semantically similar historical runs

**Deliberation loop** (see [Agentic Control Loops](#agentic-control-loops) above):
- Pass 1 Analyze: `ANALYZE_PROMPT` with CoT instructions and historical context
- Pass 2 Critique: `CRITIQUE_PROMPT` grades each recommendation A/B/C
- Pass 3 Synthesize: `SYNTHESIZE_PROMPT` rewrites weak recommendations

**`source` field in output:**
- `gemini_llm_deliberated` — all 3 passes succeeded
- `gemini_llm` — 1 or 2 passes (degraded but LLM-generated)
- `rule_based_fallback` — all LLM calls failed; rules derive insights from KPI thresholds

**Outputs:** `agent_insights` (with `deliberation_passes` count and `critique` quality grade)

---

### Agent 6 (node 6) — ApprovalGate (`pipeline/graph.py`)

**Responsibilities:** Human-in-the-loop checkpoint before any outputs are written to disk.

- `REQUIRE_HUMAN_APPROVAL=False` (default): transparent pass-through — zero cost in CI
- `REQUIRE_HUMAN_APPROVAL=True`: displays KPI summary + deliberation source, waits for `y/N`
- `APPROVAL_TIMEOUT_S`: auto-approves after N seconds (configurable); `0` blocks indefinitely
- Non-interactive environments (CI, subprocess, EOF): auto-approve silently
- Rejection raises `RuntimeError` and halts the pipeline cleanly

**Outputs:** `approval_granted` (bool)

---

### Agent 7 — ExportAgent (`pipeline/agents/export_agent.py`)

**Responsibilities:** Persist all outputs and write the immutable audit trail.

| File | Purpose |
|------|---------|
| `call_results_{ts}.csv` | Per-call flat CSV for BI tools / analysts |
| `summary.json` | Streamlit dashboard source of truth (overwritten each run) |
| `full_results_{ts}.json` | Complete per-call JSON with QA scores embedded |
| `qa_report_{ts}.json` | Standalone QA audit report |
| `insights_{ts}.json` | InsightsAgent deliberated recommendations |
| `run_manifest_{ts}.json` | Immutable audit record: all counts, agent list, file paths |
| `audit_log_{ts}.json` | Every agent start/end, governance check, tool call, error |

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
    agent_insights:        dict   # InsightsAgent (source, passes, critique)
    export_paths:          dict   # ExportAgent

    # Telemetry
    validation_errors:     list
    failed_call_ids:       list
    token_usage:           dict
    react_stats:           dict   # ReAct loop coverage improvement telemetry
    approval_granted:      bool   # human approval gate result
```

---

## Governance Layer (`pipeline/governance.py`)

| Component | Trigger | Behaviour |
|-----------|---------|-----------|
| `BudgetGuard` | After each ExtractionAgent batch | Raises `BudgetExceededError` if cumulative cost > $5.00; warns at 80% |
| `QualityGate` | After QualityAgent scores all results | Raises `QualityGateError` if pass rate < 40%; sets `_quality_gate_failed` flag for graph routing |
| `PIIScanner` | DataIngestionAgent, per transcript | Detects 6 PII types (phone, SSN, email, credit card, DOB, account number); auto-redacts before LLM |
| `AuditLog` | Every agent boundary | Append-only structured event log: `agent_start`, `agent_end`, `tool_call`, `governance_check`, `pii_detection`, `error` |

---

## Batch Orchestration

```
run_batches.py
  │
  └── Orchestrator (pipeline/orchestrator.py)
        │
        │  WorkPlanner.plan() → [BatchTask × N]
        │  AgentHealthMonitor — per-agent success/failure rates
        │
        ├── Task 1: subprocess → run_pipeline.py --offset 0  --n 20
        ├── Task 2: subprocess → run_pipeline.py --offset 20 --n 20
        ├── Task 3: subprocess → run_pipeline.py --offset 40 --n 20
        ├── Task 4: subprocess → run_pipeline.py --offset 60 --n 20
        └── Task 5: subprocess → run_pipeline.py --offset 80 --n 20
              (failed tasks retried up to max_retries=2, then logged to AgentMemory)
```

Process isolation: each batch runs as a subprocess — a crash cannot corrupt other
batches' checkpoints or state. Interrupted batches resume automatically.

---

## File Structure

```
telecom-call-intelligence/
├── pipeline/
│   ├── config.py              ← All constants (model, thresholds, security limits)
│   ├── security.py            ← InputSanitizer, OutputSanitizer, AgentScopeGuard,
│   │                              SecretGuard, RateLimiter
│   ├── vector_memory.py       ← VectorMemoryStore (Gemini embeddings, cosine similarity)
│   ├── agents/
│   │   ├── data_agent.py      ← Agent 1: DataIngestionAgent
│   │   ├── extraction_agent.py  ← Agent 2: ExtractionAgent (ReAct loop)
│   │   ├── quality_agent.py   ← Agent 3: QualityAgent (100-pt QA)
│   │   ├── aggregation_agent.py ← Agent 4: AggregationAgent (KPIs)
│   │   ├── insights_agent.py  ← Agent 5: InsightsAgent (deliberation loop)
│   │   └── export_agent.py    ← Agent 7: ExportAgent
│   ├── graph.py               ← LangGraph (7 nodes, conditional routing,
│   │                              approval gate, LangSmith tracing setup)
│   ├── orchestrator.py        ← WorkPlanner, AgentHealthMonitor, adaptive retry
│   ├── governance.py          ← BudgetGuard, QualityGate, PIIScanner, AuditLog
│   ├── memory.py              ← AgentMemory — flat JSON cross-run store
│   ├── tools.py               ← ToolRegistry — JSON-schema tool definitions
│   ├── analyzer.py            ← Gemini client (CoT, ReAct gap-fill, checkpoint, backoff)
│   ├── aggregator.py          ← KPI computation
│   ├── hf_loader.py           ← HuggingFace streaming + offset batching
│   ├── token_tracker.py       ← Token cost accounting
│   └── logger.py              ← Structured logging
├── prompts/
│   └── system_prompt.txt      ← 70-field extraction schema
├── tests/
│   ├── test_config.py
│   ├── test_governance.py
│   ├── test_memory.py
│   ├── test_orchestrator.py
│   ├── test_tools.py
│   ├── test_graph.py
│   └── test_security.py       ← 49 security tests
├── dashboard/app.py           ← Streamlit dashboard (9 panels)
├── run_pipeline.py
├── run_batches.py
├── merge_outputs.py
└── qa_audit.py
```

---

## Design Principles

1. **Stateless agents** — each agent receives state, produces updated state, holds no instance data. Safe to instantiate once and reuse across invocations.

2. **Immutable state handoff** — every agent returns `{**state, new_key: new_value}`. No mutation; any agent can be replayed in isolation with the same inputs.

3. **Defence in depth** — security is applied at every boundary: input sanitization before LLM, output sanitization after LLM, scope guards before tool invocation, secret checks after any LLM response.

4. **Graceful degradation** — InsightsAgent degrades pass-by-pass (3→2→1→rule-based). QualityAgent skips with a warning on empty input. The pipeline always completes with an audit trail.

5. **Observable** — every agent logs at INFO level with its name prefix `[AgentName]`. LangSmith traces capture full node-level spans when `LANGCHAIN_TRACING_V2=true`. The AuditLog records every decision.

6. **Composable** — to parallelise ExtractionAgent, replace `extract_node` with a LangGraph `Send`-based fan-out. No other files change. `MAX_CONCURRENT_EXTRACTIONS` is already in config.

7. **Reproducible** — any run is fully reproducible with `(offset, n, seed)`. The run manifest records the exact parameters, agent list, and all output file paths.
