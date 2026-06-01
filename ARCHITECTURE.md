# Telecom Call Intelligence — Technical Architecture v4.0

## System Overview

An end-to-end **autonomous multi-agent pipeline** implementing Anthropic's Agentic AI framework. Raw telecom call transcripts are ingested, extracted into 70+ structured fields via ReAct control loops with Chain-of-Thought prompting, scored inline by a 100-point QA model, aggregated into executive KPIs, and synthesised into board-ready strategic recommendations via a 3-pass self-reflective deliberation cycle. Every autonomous decision is logged with its reasoning and evidence. Every stage is secured, governed, and observable.

```
Local CSV (telecom_200k.csv — primary)  ·  HuggingFace stream (fallback, 3.7M turns)
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│              LangGraph StateGraph  ·  Multi-Agent Pipeline v4.0              │
│                                                                              │
│  ┌──────────────────────┐    ┌────────────────────────────────────────────┐  │
│  │  DataIngestion       │───▶│  Extraction Agent  (2/7)                   │  │
│  │  Agent  (1/7)        │    │  Claude Haiku 4.5 · 70 fields · CoT        │  │
│  │  stream · validate   │    │  ┌──────────── ReAct loop ───────────────┐ │  │
│  │  PII scan · log      │    │  │ Observe : score_field_coverage()      │ │  │
│  └──────────────────────┘    │  │ Reason  : identify null critical fields│ │  │
│                              │  │ Act     : targeted gap-fill call      │ │  │
│                              │  └───────────────────────────────────────┘ │  │
│                              └───────────────────┬────────────────────────┘  │
│                                                  │                           │
│                                                  ▼                           │
│  ┌──────────────────────┐    ┌──────────────────────────────────────────┐   │
│  │  Aggregation         │◀───│  Quality Agent  (3/7)                    │   │
│  │  Agent  (4/7)        │    │  100-pt QA · exclusion log               │   │
│  │  KPIs · cost levers  │    │  dynamic routing on gate failure         │   │
│  └───────────┬──────────┘    └──────────────────────────────────────────┘   │
│              │                                                               │
│              ▼                                                               │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Insights Agent  (5/7)  ·  NVIDIA NIM → Claude → Rule-based fallback  │ │
│  │  Vector memory → top-K semantically similar historical runs            │ │
│  │  ┌──────────────── Deliberation loop ─────────────────────────────┐   │ │
│  │  │  Pass 1  Analyze   : CoT KPI analysis → initial insights (0.3) │   │ │
│  │  │  Pass 2  Critique  : self-grade A/B/C — data-grounded, specific │   │ │
│  │  │  Pass 3  Synthesize: rewrite weak recommendations (0.3)        │   │ │
│  │  └────────────────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│              │                                                               │
│              ▼                                                               │
│  ┌──────────────────────┐    ┌──────────────────────────────────────────┐   │
│  │  Approval Gate (6/7) │───▶│  Export Agent  (7/7)                     │   │
│  │  human sign-off      │    │  CSV · full JSON · QA report · insights  │   │
│  │  auto-approve CI     │    │  decisions_{ts}.json · manifest · audit  │   │
│  └──────────────────────┘    └──────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Normal path:** all 7 nodes execute in sequence.
**Quality gate failure path:** QualityAgent routes directly to ExportAgent — pipeline always completes with audit trail.

---

## Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Orchestration** | LangGraph `StateGraph` | Explicit typed state schema; each agent is a pure function; compiled graph is inspectable; `Send` API available for fan-out parallelism |
| **LLM (Extraction) — primary** | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) | Set `EXTRACTION_MODEL` in `config.py` — all downstream clients, rate limiters, cost estimates, and provider labels resolve automatically |
| **LLM (Extraction) — fallback** | Gemini 2.0 Flash Lite | Activates when `ANTHROPIC_API_KEY` absent; free tier up to 1 500 req/day / 30 RPM |
| **LLM (Insights) — primary** | NVIDIA NIM `meta/llama-3.3-70b-instruct` | OpenAI-compatible API; reliable JSON via `response_format=json_object`; strong instruction-following for strategic recommendations |
| **LLM (Insights) — fallback 1** | Claude Haiku 4.5 | Activated when `NVIDIA_API_KEY` absent or quota exceeded |
| **LLM (Insights) — fallback 2** | Gemini 2.0 Flash Lite | Final LLM fallback; separate quota pool from extraction |
| **LLM (Insights) — fallback 3** | Rule-based | Derives insights from KPI thresholds — no API key required; pipeline always completes |
| **LLM (Embeddings)** | Gemini `text-embedding-004` | 768-dim embeddings for vector memory; same API key, no extra library; TF-IDF fallback offline |
| **Dataset (primary)** | Local CSV `telecom_200k.csv` | 200K conversations pre-downloaded; zero-latency load; auto-detected by `hf_loader.py` |
| **Dataset (fallback)** | HuggingFace `talkmap/telecom-conversation-corpus` | 3.73M turns, 200K conversations, MIT-licensed; streaming mode — bounded RAM regardless of corpus size |
| **QA Scoring** | Custom 100-pt model | Completeness(30) + Enum validity(25) + Consistency(25) + Plausibility(20) |
| **Vector memory** | numpy cosine similarity | Zero extra dependencies; interface-compatible with ChromaDB/Pinecone swap |
| **Tracing** | LangSmith (optional) | `LANGCHAIN_TRACING_V2=true` activates full node-level span capture |
| **Dashboard** | Streamlit + Plotly | Professional light theme; 8 sections; reads `summary.json`; built-in demo data fallback |

---

## Agentic Control Loops

### ReAct — ExtractionAgent

Standard Reason → Act → Observe loop applied per transcript, driven by field-coverage scoring:

```
┌────────────────────────────────────────────────────────────────────┐
│  Initial Act: analyze_transcript() → first_pass result             │
│                        │                                           │
│               Observe: score_field_coverage()                      │
│               (% of _CRITICAL_FIELDS that are non-null/non-empty)  │
│                        │                                           │
│          coverage < REACT_QUALITY_THRESHOLD (70)?                  │
│              │                         │                           │
│             YES                        NO → append to results      │
│              │                                                      │
│       Reason: build _missing list from _CRITICAL_FIELDS            │
│       Log: DecisionLogger("react_trigger", evidence={coverage})    │
│              │                                                      │
│        Act: gap_fill_transcript()                                   │
│        (targeted prompt: only the missing fields asked for)        │
│              │                                                      │
│       Observe: merge null fields + re-score                        │
│       (repeat up to REACT_MAX_ITERATIONS times)                    │
│              │                                                      │
│       Log: DecisionLogger("react_gap_fill_outcome")                │
└────────────────────────────────────────────────────────────────────┘
```

**Quota circuit breaker:** `_react_quota_exhausted` (module-level bool in `analyzer.py`):
- For **Gemini** provider: trips on the first 429 `ClientError` — daily quota exhausted; disables all subsequent gap-fills for the run so primary extraction quota is preserved
- For **Claude** provider: 429 is a transient per-minute rate limit, not daily exhaustion; CLAUDE_RATE_LIMITER already backs off; the circuit breaker does NOT trip — only that individual call is skipped

### Chain-of-Thought — Both LLM Agents

`_cot_reasoning` is the **first field** in every JSON response. The LLM must populate this before the 70 structured fields, forcing explicit reasoning before committing to values. Zero extra API calls — native to `response_mime_type="application/json"`.

```json
{
  "_cot_reasoning": "Customer called about a billing discrepancy. Agent identified
    a duplicate charge in the system. Refund was processed during the call. Sentiment
    moved from frustrated to satisfied — FCR applies, escalation does not.",
  "fcr": true,
  "resolution_status": "resolved",
  "escalated": false,
  ...
}
```

InsightsAgent's `ANALYZE_PROMPT` embeds explicit step-by-step reasoning instructions:

```
STEP-BY-STEP REASONING (Chain-of-Thought):
1. Which KPIs are significantly above or below industry benchmarks?
2. What root causes are most likely given the pattern of KPIs together?
3. Which interventions would have the highest ROI given this specific data?
4. What risks are NOT visible in this data but are implied by the patterns?
```

### Self-Reflection Deliberation — InsightsAgent

Three passes, each with a distinct role, producing self-correcting strategic output:

```
Pass 1 — Analyze (CoT)
  Input : KPI summary + historical context (flat memory + vector top-K)
  Prompt: ANALYZE_PROMPT with CoT step-by-step instructions
  Output: initial insights JSON with _cot_reasoning
  Temp  : 0.3

Pass 2 — Critique (self-reflection)
  Input : Pass 1 output + raw KPIs
  Prompt: CRITIQUE_PROMPT
  Task  : Grade each recommendation A/B/C:
          (A) data-grounded, (B) specific, (C) non-duplicated
  Output: overall_quality + per-recommendation grades + missing_insights
  Temp  : 0.1  (deterministic grading)

Pass 3 — Synthesize
  Input : Pass 1 output + Pass 2 critique
  Prompt: SYNTHESIZE_PROMPT
  Task  : Rewrite recommendations graded B/C; ensure every rec cites a KPI
  Output: final board-ready insights JSON
  Temp  : 0.3
```

Graceful degradation: Pass 2 fail → return Pass 1; Pass 3 fail → return Pass 2; all fail → rule-based fallback. The pipeline always completes.

---

## Decision Traceability Layer (`pipeline/decision_log.py`)

Every autonomous decision made by any agent is captured as a `DecisionRecord` with:
- **What** was decided (human-readable `decision` string)
- **Why** (free-text `reason`, capped 500 chars)
- **Evidence** (quantitative data that drove the decision — scores, counts, flags; never raw transcript text)
- **Alternatives** considered but not taken
- **Confidence** level (`high` / `medium` / `low`)

### Decision types by agent

| Agent | Decision type | Triggered when |
|-------|--------------|----------------|
| `DataIngestionAgent` | `transcript_skip` | Transcript too short, too few turns, or empty |
| `DataIngestionAgent` | `pii_redaction` | PIIScanner detects and redacts sensitive patterns |
| `ExtractionAgent` | `react_trigger` | Field coverage < `REACT_QUALITY_THRESHOLD` per call |
| `ExtractionAgent` | `react_gap_fill_outcome` | ReAct loop completes for the batch |
| `QualityAgent` | `qa_exclusion` | Record graded LOW (score < 60) — excluded from aggregation |
| `QualityAgent` | `qa_grade_assignment` | Borderline MEDIUM (60–65) — accepted but flagged |
| `QualityAgent` | `quality_gate_outcome` | Dataset-level quality gate PASS or FAIL |
| `AggregationAgent` | `aggregation_scope` | QA-filtered vs full-set aggregation decision |
| `AggregationAgent` | `cost_model_applied` | Provider pricing resolved from `EXTRACTION_MODEL` |
| `InsightsAgent` | `provider_selected` | NVIDIA NIM / Claude / rule-based selection and reason |
| `InsightsAgent` | `deliberation_outcome` | 3-pass deliberation completed with critique quality |
| `ApprovalGate` | `approval_decision` | Human approved / rejected / auto-approved |
| `GraphRouter` | `routing_decision` | Quality gate failure → emergency export routing |

### Output

All decisions accumulate in `PipelineState.decision_log` (immutable list of plain dicts). ExportAgent writes:
- `decisions_{ts}.json` — full record with `total_decisions`, `summary`, and `records` array
- `summary.json` — embeds `decision_summary` (counts by agent and type, notable decisions)

### Usage in agents

```python
from pipeline.decision_log import DecisionLogger

class MyAgent:
    def run(self, state: dict) -> dict:
        dl = DecisionLogger(self.name, state)
        dl.log(
            decision_type="my_decision_type",
            decision="Short description of what was decided",
            reason="Why this decision was taken — the constraint or evidence",
            evidence={"score": 42, "threshold": 60},
            call_id="C001",
            confidence="high",
            alternatives=["Alternative A considered but rejected because..."],
        )
        return {**state, "decision_log": dl.finalize()}
```

---

## Security Layer (`pipeline/security.py`)

Every agent boundary is protected. No LLM call proceeds without input sanitisation; no LLM output reaches downstream agents without output sanitisation.

### Threat model

| Threat | Component | Defence |
|--------|-----------|---------|
| Prompt injection in transcript | `InputSanitizer` | 10 regex patterns; neutralise with `[FILTERED]` (not reject — avoids DoS from one bad record) |
| Token bomb (oversized input) | `InputSanitizer` | Hard cap at `MAX_TRANSCRIPT_CHARS` (50K chars); truncate with `[TRUNCATED-SECURITY]` marker |
| Encoding attacks | `InputSanitizer` | Strip `\x00` and `�` before LLM |
| Secret leakage in input data | `InputSanitizer` | Google/Anthropic/OpenAI key patterns, JWTs, Bearer tokens → `[SECRET_REDACTED]` |
| Code execution in LLM output | `OutputSanitizer` | `__import__`, `eval`, `exec`, `subprocess`, XSS → `[CONTENT_FILTERED]` |
| Response bomb | `OutputSanitizer` | Hard cap at `MAX_RESPONSE_BYTES` (32 KB); raises `SecurityViolation` before JSON parse |
| Secret leakage in LLM output | `SecretGuard` | Pattern scan on raw LLM text before any downstream agent receives it |
| Cross-agent tool hijacking | `AgentScopeGuard` | Per-agent authorised tool set; violation raises `SecurityViolation` before invocation |
| State tampering | `InputSanitizer.validate_state_schema()` | Required keys verified at each agent boundary |
| Runaway API consumption | `RateLimiter` | Sliding-window caps: 50 req/60s (Claude), 15 req/60s (Gemini) |

### Security call flow

```python
# Every extraction call in analyzer.py — provider-agnostic path:

transcript = INPUT_SANITIZER.sanitize_transcript(transcript)    # injection + PII
CLAUDE_RATE_LIMITER.acquire()   # or GEMINI_RATE_LIMITER — resolved by _USE_CLAUDE

# Claude path:  _call_claude(client, system_prompt, user_msg, max_tokens)
# Gemini path:  client.models.generate_content(model=MODEL, ...)

SECRET_GUARD.assert_no_secrets_in_output(response_text)         # key leak check
OUTPUT_SANITIZER.check_response_size(response_text)             # response bomb
result = _parse_json_text(response_text)                        # strips markdown fences
result = OUTPUT_SANITIZER.sanitize_extraction_result(result)    # per-field sanitise
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
Gemini text-embedding-004 embeds KPI summary text → 768-dim vector
(TF-IDF bag-of-words fallback when API key unavailable)
        │
        ▼
Stored: vectors.npy + index.json  (outputs/vector_memory/)
        │
        │  ← next pipeline run ────────────────────────────────────────────┐
        ▼                                                                   │
InsightsAgent calls VECTOR_STORE.format_context(current_kpi_text)          │
        │                                                                   │
        ▼                                                                   │
Cosine similarity over all stored vectors → top-K most similar runs        │
        │                                                                   │
        ▼                                                                   │
"Top-3 similar historical runs (by KPI pattern similarity):                │
  1. [2026-05-18] sim=0.94 — FCR 72% AHT 4.2 min escalation 8%…"          │
        │                                                                   │
        ▼                                                                   │
Injected into ANALYZE_PROMPT historical context section ────────────────── ┘
```

The interface is backend-agnostic: replace `VectorMemoryStore._save()/_load()` with ChromaDB or Pinecone without changing the public `add_run()` / `query()` API.

---

## Agent Design

Each agent is a **stateless class** with a single `run(state: dict) -> dict` method. Agents are fully decoupled from the graph — swapping, replacing, or parallelising them requires changes only to `pipeline/graph.py`.

### Agent 1 — DataIngestionAgent (`pipeline/agents/data_agent.py`)

**Responsibilities:** Streaming acquisition, quality gating, PII scanning, decision logging.

**Streaming strategy:**
1. Stream rows until `(offset + n) × 6` unique `conversation_id` values are seen
2. Sort IDs lexicographically → stable global ordering
3. Slice `[offset : offset + n×6]` to skip previously-processed conversations
4. `random.sample(slice, n, seed)` → final selection

**Decision logging:** Records `transcript_skip` for every rejected transcript (empty, too short, too few turns) with exact reason and evidence.

**Outputs:** `raw_transcripts`, `validated_transcripts`, `validation_errors`, `decision_log`

---

### Agent 2 — ExtractionAgent (`pipeline/agents/extraction_agent.py`)

**Responsibilities:** Drive Claude Haiku API calls for all validated transcripts with ReAct gap-fill loop.

**Provider:** Determined by `EXTRACTION_MODEL` in `config.py`:
- `claude-*` → `anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)`; `CLAUDE_RATE_LIMITER.acquire()` (50/60s)
- `gemini-*` → `genai.Client(api_key=GEMINI_API_KEY)`; `GEMINI_RATE_LIMITER.acquire()` (15/60s)

**Key parameters:**
- `temperature=0.1` — near-deterministic structured extraction
- `max_output_tokens=8192` — sized to fit 70-field JSON
- `thinking_budget=0` (Gemini only) — prevents thinking tokens from truncating extraction JSON
- `response_mime_type="application/json"` (Gemini only) — guaranteed valid JSON

**Budget:** Uses `token_tracker.cost_usd(prompt_tokens, completion_tokens)` for accurate provider-aware cost — not a hardcoded rate.

**Circuit breaker:** `_react_quota_exhausted` flag in `analyzer.py`:
- Gemini 429: trips permanently for the run (daily quota exhausted)
- Claude 429: skips only the current call (transient per-minute limit)

**Outputs:** `analysis_results`, `failed_call_ids`, `react_stats`, `decision_log`

---

### Agent 3 — QualityAgent (`pipeline/agents/quality_agent.py`)

**Responsibilities:** Inline 100-point QA scoring; record all exclusion decisions.

| Dimension | Points | What is checked |
|-----------|--------|-----------------|
| Completeness | 30 | 19 required fields are non-null / non-empty |
| Enum validity | 25 | String fields match their allowed value sets |
| Consistency | 25 | Cross-field logical rules (FCR ≠ escalation, upsell intent vs outcome) |
| Plausibility | 20 | Duration [30–7200s], non-negative counts, issue count in [0,5] |

**Grade bands:** `HIGH` ≥ 85 · `MEDIUM` 60–84 · `LOW` < 60 (excluded from aggregation)

**Decision logging:** Every `LOW` exclusion and every borderline `MEDIUM` (60–65) is recorded with score, threshold, and reasoning.

**Dynamic routing:** If `QualityGate` fires (pass rate < 40%), `_quality_gate_failed` is set in `qa_report` and the graph routes directly to ExportAgent.

**Outputs:** `analysis_results` (QA-enriched), `qa_report`, `qa_passed_results`, `decision_log`

---

### Agent 4 — AggregationAgent (`pipeline/agents/aggregation_agent.py`)

**Responsibilities:** Executive KPI computation from QA-passed results.

KPIs computed: FCR rate, AHT, escalation rate, avoidable call rate, agentic AI resolvability, repeat call risk distribution, sentiment improvement rate, phase-level duration breakdown, cost-lever savings opportunity (at $6.00/call industry benchmark).

**Decision logging:** Records `aggregation_scope` (QA-filtered vs full set) and `cost_model_applied` (provider pricing resolved from `EXTRACTION_MODEL`).

**Outputs:** `aggregated_metrics`, `token_usage`, `decision_log`

---

### Agent 5 — InsightsAgent (`pipeline/agents/insights_agent.py`)

**Responsibilities:** Second LLM agent — 3-pass deliberation with provider hierarchy.

**Provider hierarchy:**
1. NVIDIA NIM `meta/llama-3.3-70b-instruct` — OpenAI-compatible, `NVIDIA_API_KEY` required
2. Claude Haiku 4.5 — `ANTHROPIC_API_KEY` required
3. Gemini 2.0 Flash Lite — separate quota pool from extraction
4. Rule-based fallback — KPI threshold rules; no API key needed

**Context enrichment before deliberation:**
1. `MEMORY.get_context_for_insights()` — flat run history (FCR/AHT trends, quota events)
2. `VECTOR_STORE.format_context(current_kpi_text)` — top-K semantically similar historical runs

**`source` field values in output:**
- `llm_deliberated` — all 3 passes succeeded
- `llm_single_pass` — 1 pass succeeded (fallback after pass 2/3 failure)
- `rule_based_fallback` — all LLM calls failed

**Decision logging:** Records `provider_selected` (with reasoning for fallback chain position) and `deliberation_outcome` (critique quality grade when 3 passes complete).

**Outputs:** `agent_insights` (with `deliberation_passes`, `critique`, `source`), `decision_log`

---

### Agent 6 (node) — ApprovalGate (`pipeline/graph.py`)

**Responsibilities:** Human-in-the-loop checkpoint before any outputs are written.

- `REQUIRE_HUMAN_APPROVAL=False` (default): transparent pass-through, logs `auto-approved`
- `REQUIRE_HUMAN_APPROVAL=True`: displays KPI summary + insights source, prompts `y/N`
- `APPROVAL_TIMEOUT_S`: auto-approves after N seconds; `0` blocks indefinitely
- Non-interactive environments (CI, EOF): auto-approve silently
- Rejection: raises `RuntimeError` and halts the pipeline cleanly

**Decision logging:** Always records `approval_decision` — approved/rejected/auto-approved — with FCR, insights source, and timeout as evidence.

**Outputs:** `approval_granted`, `decision_log`

---

### Agent 7 — ExportAgent (`pipeline/agents/export_agent.py`)

**Responsibilities:** Persist all pipeline outputs and the complete audit trail to disk.

| File | Purpose |
|------|---------|
| `call_results_{ts}.csv` | Per-call flat CSV for BI tools / analysts |
| `summary.json` | Streamlit dashboard source of truth (overwritten each run); includes `decision_summary` |
| `full_results_{ts}.json` | Complete per-call JSON with QA scores embedded |
| `qa_report_{ts}.json` | Standalone QA audit report |
| `insights_{ts}.json` | InsightsAgent deliberated recommendations |
| `decisions_{ts}.json` | Full decision log: total count, summary by agent/type, all records |
| `run_manifest_{ts}.json` | Immutable audit record: all counts, agent list, file paths, decision count |
| `audit_log_{ts}.json` | Every agent start/end, governance check, tool call, PII detection, error |

**Outputs:** `export_paths`

---

## State Schema

```python
class PipelineState(TypedDict):
    # ── Run configuration ────────────────────────────────────────────
    n_calls:               int
    seed:                  int
    offset:                int
    inter_call_delay:      float
    checkpoint_key:        str

    # ── Agent outputs (in execution order) ──────────────────────────
    raw_transcripts:       list   # DataIngestionAgent
    validated_transcripts: list   # DataIngestionAgent
    analysis_results:      list   # ExtractionAgent → enriched by QualityAgent
    qa_report:             dict   # QualityAgent
    qa_passed_results:     list   # QualityAgent
    aggregated_metrics:    dict   # AggregationAgent
    agent_insights:        dict   # InsightsAgent (source, passes, critique)
    export_paths:          dict   # ExportAgent

    # ── Telemetry ────────────────────────────────────────────────────
    validation_errors:     list
    failed_call_ids:       list
    token_usage:           dict
    react_stats:           dict   # ReAct loop coverage improvement telemetry
    approval_granted:      bool   # human approval gate result

    # ── Traceability ─────────────────────────────────────────────────
    decision_log:          list   # DecisionRecord dicts — agent reasoning audit trail
```

State is **immutable**: every agent returns `{**state, new_key: new_value}`. Agents never mutate state in-place. Any agent can be replayed in isolation with the same input.

---

## Governance Layer (`pipeline/governance.py`)

| Component | Trigger | Behaviour |
|-----------|---------|-----------|
| `BudgetGuard` | After ExtractionAgent batch | Raises `BudgetExceededError` if cumulative cost > `BUDGET_USD` (from `config.py`); warns at 80%; uses `token_tracker.cost_usd()` — provider-aware, not hardcoded |
| `QualityGate` | After QualityAgent scores all results | Raises `QualityGateError` if pass rate < `MIN_PASS_RATE` (from `config.py`); sets `_quality_gate_failed` for graph routing |
| `PIIScanner` | DataIngestionAgent, per transcript | Detects 6 PII types (phone, SSN, email, credit card, DOB, account number); auto-redacts to `[REDACTED]` |
| `AuditLog` | Every agent boundary | Append-only structured event log: `agent_start`, `agent_end`, `tool_call`, `governance_check`, `pii_detection`, `error` |

**Both `BUDGET_USD` and `MIN_PASS_RATE` are defined in `pipeline/config.py`** — change them once, the singletons pick it up automatically.

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
              (failed tasks retried up to max_retries, then logged to AgentMemory)
```

Process isolation: each batch runs as a subprocess — a crash cannot corrupt other batches' checkpoints or state. Interrupted batches resume automatically from checkpoint.

**Startup validation:** `run_pipeline.py` validates API keys immediately on launch — before any imports that might fail silently. Key checked depends on `EXTRACTION_MODEL`: Claude → `ANTHROPIC_API_KEY`, Gemini → `GEMINI_API_KEY`. Missing key exits immediately with a clear message.

---

## File Structure

```
telecom-call-intelligence/
├── pipeline/
│   ├── config.py              ← All constants (model, thresholds, limits, paths)
│   ├── security.py            ← InputSanitizer, OutputSanitizer, AgentScopeGuard,
│   │                              SecretGuard, RateLimiter (Claude + Gemini)
│   ├── decision_log.py        ← DecisionRecord, DecisionLogger, summarize_decisions
│   ├── vector_memory.py       ← VectorMemoryStore (Gemini embeddings, cosine similarity)
│   ├── agents/
│   │   ├── data_agent.py          ← Agent 1: DataIngestionAgent
│   │   ├── extraction_agent.py    ← Agent 2: ExtractionAgent (Claude Haiku + ReAct)
│   │   ├── quality_agent.py       ← Agent 3: QualityAgent (100-pt QA)
│   │   ├── aggregation_agent.py   ← Agent 4: AggregationAgent (KPIs)
│   │   ├── insights_agent.py      ← Agent 5: InsightsAgent (NVIDIA NIM deliberation)
│   │   └── export_agent.py        ← Agent 7: ExportAgent
│   ├── graph.py               ← LangGraph (7 nodes, conditional routing,
│   │                              approval gate, decision logging, LangSmith)
│   ├── orchestrator.py        ← WorkPlanner, AgentHealthMonitor, adaptive retry
│   ├── governance.py          ← BudgetGuard, QualityGate, PIIScanner, AuditLog
│   ├── memory.py              ← AgentMemory — flat JSON cross-run store
│   ├── tools.py               ← ToolRegistry — JSON-schema tool definitions
│   ├── analyzer.py            ← Claude/Gemini client (CoT, ReAct, checkpoint, backoff)
│   ├── aggregator.py          ← KPI computation + cost-lever estimates
│   ├── hf_loader.py           ← CSV loader + HuggingFace streaming + offset batching
│   ├── token_tracker.py       ← Model-aware token cost accounting
│   └── logger.py              ← Structured logging (INFO→stdout, DEBUG→file)
├── prompts/
│   └── system_prompt.txt      ← 70-field extraction schema + CoT instructions
├── tests/
│   ├── test_config.py
│   ├── test_decision_log.py   ← 24 decision traceability tests
│   ├── test_governance.py
│   ├── test_memory.py
│   ├── test_orchestrator.py
│   ├── test_tools.py
│   ├── test_graph.py
│   └── test_security.py       ← 51 security tests
├── dashboard/app.py           ← Streamlit executive dashboard (8 sections, light theme)
├── run_pipeline.py            ← Single-batch entry point (model-aware key validation)
├── run_batches.py             ← Multi-batch orchestrator (delegates to Orchestrator)
├── merge_outputs.py           ← Merge batch JSONs → combined dataset
└── qa_audit.py                ← Standalone QA scoring tool
```

---

## Design Principles

1. **Stateless agents** — each agent receives state, produces updated state, holds no instance data. Safe to instantiate once and reuse across invocations.

2. **Immutable state handoff** — every agent returns `{**state, new_key: new_value}`. No mutation. Any agent can be replayed in isolation with the same inputs.

3. **Defence in depth** — security applied at every boundary: input sanitisation before LLM, output sanitisation after LLM, scope guards before tool invocation, secret checks after every LLM response.

4. **Graceful degradation** — InsightsAgent degrades pass-by-pass (3→2→1→rule-based). QualityAgent skips with a warning on empty input. The pipeline always completes with a manifest and audit trail.

5. **Decision traceability** — every autonomous decision is recorded with WHAT, WHY, evidence, and alternatives. Operators can retrace and challenge any agent decision from the `decisions_{ts}.json` file.

6. **Observable** — every agent logs at INFO with `[AgentName]` prefix. LangSmith traces full node-level spans when `LANGCHAIN_TRACING_V2=true`. AuditLog records every governance check. DecisionLog records every reasoning step.

7. **Composable** — to parallelise ExtractionAgent, replace `extract_node` with a LangGraph `Send`-based fan-out. `MAX_CONCURRENT_EXTRACTIONS` is already in config. No other files change.

8. **Plug-and-play models** — `EXTRACTION_MODEL` in `config.py` is the single knob. All downstream clients, rate limiters, cost estimates, provider labels, and API key validation resolve automatically. One change, zero regressions.

9. **Reproducible** — any run is fully reproducible from `(offset, n, seed)`. The run manifest records the exact parameters, agent list, decision count, and all output file paths.
