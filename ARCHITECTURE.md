# Telecom Call Intelligence — Technical Architecture

## System Overview

An end-to-end pipeline that ingests raw telecom call transcripts from a public
HuggingFace corpus, extracts 70+ structured metadata fields per call using an
LLM, aggregates KPIs, and serves an executive analytics dashboard.

```
HuggingFace Streaming
        │
        ▼
  ┌─────────────────────────────────────────────────────────┐
  │  LangGraph StateGraph                                   │
  │                                                         │
  │  [Fetch] → [Validate] → [Analyze] → [Aggregate] → [Export] │
  │     1           2           3            4           5   │
  └─────────────────────────────────────────────────────────┘
        │                         │                   │
        ▼                         ▼                   ▼
  transcripts              Groq API            outputs/
  (turn-level)           Llama 3.3 70B        summary.json
                         (per-call JSON)      call_results_{ts}.csv
                                              full_results_{ts}.json
                                              run_manifest_{ts}.json
                                                     │
                                                     ▼
                                           Streamlit Dashboard
```

---

## Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Orchestration** | LangGraph `StateGraph` | Explicit state schema; each node is a pure function; trivial to add/reorder nodes; compiled graph is inspectable |
| **LLM** | Groq / Llama 3.3 70B | Best open-source model for structured JSON extraction; 128K context (no truncation); deterministic at `temperature=0.1`; free tier fits 100-call batches |
| **Dataset** | HuggingFace `talkmap/telecom-conversation-corpus` | 3.73M turns, 200K conversations, MIT-licensed, real telecom call data |
| **Streaming** | `datasets` streaming mode | Never loads the full 3.73M-row dataset into memory; bounded RAM regardless of corpus size |
| **Dashboard** | Streamlit + Plotly | Rapid iteration; Python-native; sufficient for executive KPI displays |
| **Logging** | Python `logging` module | Structured levels (INFO→stdout, DEBUG→file); no external dependencies |
| **Token tracking** | Manual from `response.usage` | Groq returns exact prompt/completion counts; cost model is applied client-side |

---

## Data Flow

### Node 1 — Fetch (`pipeline/hf_loader.py`)

**Streaming strategy** — avoids loading all 3.73M rows:

1. Stream rows until `(offset + n) × 6` unique `conversation_id` values are seen.
   The 6× buffer handles uneven turn distribution across conversations.
2. Sort all collected IDs lexicographically → stable global ordering.
3. Slice `[offset : offset + n×6]` to skip previously-processed conversations.
4. `random.sample(slice, n, seed)` → final selection.

This guarantees:
- No conversation appears in more than one batch (given consistent offset multiples)
- Each batch is reproducible with the same `(offset, n, seed)` triple
- Memory stays bounded regardless of dataset size

**Timestamp parsing fix** (pandas 3.x):

```python
# WRONG — silently coerces ~92% of rows to NaT on pandas ≥ 3.0
pd.to_datetime(col, utc=True)

# CORRECT — handles mixed precision ISO 8601
pd.to_datetime(col, format="mixed", errors="coerce")
```

The corpus mixes whole-second (`2024-01-15T09:00:00`) and fractional-second
(`2024-01-15T09:00:00.123Z`) timestamps in the same column. Only `format="mixed"`
handles both.

### Node 2 — Validate (`pipeline/graph.py::validate_node`)

Lightweight quality gate before spending API quota:

| Check | Threshold | Rationale |
|-------|-----------|-----------|
| Non-empty transcript | Required | Nothing to analyze |
| Min transcript length | 150 chars | Too short → LLM cannot extract meaningful signal |
| Min turn count | 4 turns | Fewer → not a real conversation |

### Node 3 — Analyze (`pipeline/analyzer.py`)

**Prompt engineering:**

- System prompt: 174-line instruction set defining 8 call phases, a 70-field flat JSON schema, and 10 extraction rules. Output ONLY valid JSON — no preamble.
- User message: call metadata header + full timestamped transcript.
- `temperature=0.1`: near-deterministic; maximises JSON structural consistency.
- `max_tokens=2048`: sufficient for the full schema with rationale fields.

**Retry logic:**

| Error type | Behaviour |
|-----------|-----------|
| `JSONDecodeError` | Retry up to 3×, 2s sleep between |
| `RateLimitError` | Exponential backoff: 30s × 2^attempt |
| `APIStatusError` | Linear backoff: 5s × attempt |
| Any other exception | Log stack trace, 3s sleep, retry |

**Token injection:**

```python
result["_prompt_tokens"]     = response.usage.prompt_tokens
result["_completion_tokens"] = response.usage.completion_tokens
result["_total_tokens"]      = response.usage.total_tokens
```

All three fields are injected into the result dict after every successful parse.
Downstream — `aggregator.py`, `token_tracker.py`, `qa_audit.py` — can access them.

### Node 4 — Aggregate (`pipeline/aggregator.py`)

Computes all KPIs, distributions, and cost-lever estimates from the per-call JSON
list. All monetary figures scale from a 100K-call monthly volume baseline using
the industry benchmark of $6.00 / call cost-to-serve.

**Cost-lever model:**

| Lever | Assumption |
|-------|-----------|
| Self-serve deflection | 85% cost avoidance per deflected call |
| Agentic AI resolution | 70% cost avoidance (AI still needs infra cost) |
| Proactive outreach | 60% cost avoidance (some calls prevented) |

### Node 5 — Export (`pipeline/graph.py::export_node`)

| Output | Path | Purpose |
|--------|------|---------|
| Per-call CSV | `outputs/call_results_{ts}.csv` | Validation against ACD records |
| Summary JSON | `outputs/summary.json` | Dashboard reads this on every load |
| Full results JSON | `outputs/full_results_{ts}.json` | QA audit input; batch merging |
| Run manifest | `outputs/run_manifest_{ts}.json` | Immutable audit record per run |

---

## LangGraph State Schema

```python
class PipelineState(TypedDict):
    # Run configuration
    n_calls:               int     # Target calls for this batch
    seed:                  int     # RNG seed for HF sampling
    offset:                int     # Conversations to skip (batching)
    inter_call_delay:      float   # Seconds between Groq API calls
    checkpoint_key:        str     # ID for checkpoint file

    # Pipeline data (accumulated through nodes)
    raw_transcripts:       list    # from Node 1
    validated_transcripts: list    # from Node 2
    analysis_results:      list    # from Node 3
    aggregated_metrics:    dict    # from Node 4
    export_paths:          dict    # from Node 5

    # Telemetry
    validation_errors:     list    # calls dropped at Node 2
    failed_call_ids:       list    # calls that failed at Node 3
    token_usage:           dict    # summary from token_tracker
```

State is immutable at each node: every node returns `{**state, key: new_value}`.

---

## Batch / Checkpoint System

### Why batches?

The Groq free tier allows 14,400 requests/day and 30/min. Running 100 calls
sequentially at 2s inter-call delay takes ~7 minutes, well within daily limits.
Batches exist primarily for:

1. **Process isolation** — a crash in batch 3 does not lose batches 1–2.
2. **Checkpoint resume** — a killed process loses at most the current call.
3. **Parallelism** (future) — batches could run on separate machines.

### Batch numbering

```
run_batches.py --batches 5 --n 20
  Batch 1: offset=0,  n=20  → conversations  0–19  (after sorting)
  Batch 2: offset=20, n=20  → conversations 20–39
  Batch 3: offset=40, n=20  → conversations 40–59
  Batch 4: offset=60, n=20  → conversations 60–79
  Batch 5: offset=80, n=20  → conversations 80–99
```

Each batch is invoked as a subprocess by `run_batches.py`. The checkpoint key
is `offset{N}_n{M}_seed{S}`, encoding all sampling parameters.

### Checkpoint lifecycle

```
Node 3 start
    │
    ├─ checkpoint exists? ──yes──► load results, build done_ids set
    │                              skip already-done transcripts
    ├─ no ──────────────────────► start fresh
    │
    ▼
  for each transcript:
    ├─ analyze → success ──────► append to .checkpoint_{key}.jsonl
    └─ failure ────────────────► log, continue

Node 3 end (no failures)
    └─► delete checkpoint file

Node 3 end (with failures)
    └─► keep checkpoint (retry will skip successes)
```

### Merging batches

`merge_outputs.py` auto-discovers `outputs/full_results_[0-9]*.json`, deduplicates
by `call_id` (last file wins), re-runs `aggregate_metrics()`, and overwrites
`outputs/summary.json` so the dashboard shows combined results.

---

## Prompt Engineering

**Schema extraction vs free-form summarisation**

The system prompt is a strict schema specification, not a question. Every field
is defined with allowed values. Rules 1 and 4–5 eliminate ambiguity:

```
Rule 1: Output ONLY valid JSON. No text before or after it.
Rule 4: pipe-separated lists use | with no spaces around it.
Rule 5: Populate issue_1 through issue_5 sequentially.
```

**Phase extraction**

Phases are explicitly numbered and described. The model is instructed to derive
durations from HH:MM:SS timestamps in the transcript — no guessing required.

**FCR discipline**

```
Rule 9: fcr_indicator: true ONLY if issue resolved in this call
        with no indication customer needs to call back.
```

Without this guard, models tend to be optimistic about FCR. The explicit
conditional suppresses false positives.

**Fence stripping**

Despite `Rule 1`, some models prepend ` ```json ` fences. `_strip_fences()` in
`analyzer.py` handles this gracefully on every response before JSON parsing.

---

## Rate Limiting Strategy

```
Groq free tier: 30 req/min → ~2.0s minimum inter-call delay
                14,400 req/day

Default: inter_call_delay=2.0s → ~25 req/min (safe margin)

On RateLimitError: exponential backoff
  attempt 0 → sleep 30s
  attempt 1 → sleep 60s
  attempt 2 → sleep 120s

On APIStatusError: linear backoff
  attempt 0 → sleep 5s
  attempt 1 → sleep 10s
  attempt 2 → sleep 15s
```

The tqdm progress bar updates after every call (success or failure) so the
operator has real-time visibility into throughput and failure rate.

---

## QA Framework

QA scores are computed in `qa_audit.py` against four dimensions:

| Dimension | Max pts | What it checks |
|-----------|---------|----------------|
| **Completeness** | 30 | 19 required fields are non-null |
| **Enum validity** | 25 | 18 string-enum fields match allowed values |
| **Consistency** | 25 | 5 cross-field logical rules |
| **Plausibility** | 20 | Numeric ranges, non-negative durations |

**Grade thresholds:**

| Grade | Score | Meaning |
|-------|-------|---------|
| HIGH | ≥ 85 | Reliable for production reporting |
| MEDIUM | 60–84 | Usable but warrants spot-check |
| LOW | < 60 | Flag for manual review |

**Dataset verdict:** PASS if ≥ 90% of calls score ≥ 60 (configurable with `--threshold`).

---

## Output Schema

### `summary.json` (dashboard input)

```json
{
  "meta": {
    "total_calls_analyzed": 100,
    "analysis_timestamp":   "2026-05-17T13:45:00.000Z",
    "model":                "llama-3.3-70b-versatile",
    "inference_provider":   "Groq",
    "dataset":              "talkmap/telecom-conversation-corpus"
  },
  "kpis": {
    "total_calls_analyzed":      100,
    "avg_handle_time_minutes":   7.2,
    "fcr_rate_pct":              68.0,
    "avoidable_call_rate_pct":   34.0,
    "agentic_ai_resolvable_pct": 41.0,
    ...
  },
  "phase_avg_seconds": { "Welcome & Auth": 45, ... },
  "distributions": {
    "issue_category":           { "billing": 38.2, "technical": 27.1, ... },
    "customer_sentiment_start": { "neutral": 45.0, "negative": 30.2, ... },
    ...
  },
  "cost_levers": {
    "cost_per_call_usd":             6.00,
    "monthly_volume_estimate":       100000,
    "total_savings_opportunity_usd": 1820000,
    ...
  },
  "token_usage": {
    "model":                       "llama-3.3-70b-versatile",
    "provider":                    "Groq",
    "total_prompt_tokens":         412000,
    "total_completion_tokens":     87000,
    "total_tokens":                499000,
    "total_cost_usd":              0.3114,
    "avg_cost_per_call_usd":       0.003114,
    "pricing_note":                "Prices as of 2025-Q2. ..."
  }
}
```

---

## Cost Model

### Inference (Groq)

Pricing as of 2025-Q2 for `llama-3.3-70b-versatile`:

| Direction | Rate |
|-----------|------|
| Input | $0.59 / 1M tokens |
| Output | $0.79 / 1M tokens |

Typical per-call cost: ~$0.003 USD (≈4,000 prompt + 900 completion tokens).

### Contact centre (illustrative)

| Lever | Assumptions |
|-------|------------|
| Baseline | $6.00/call × 100K monthly calls = $600K/mo |
| Self-serve deflection | 85% savings × deflectable call % |
| Agentic AI | 70% savings × AI-resolvable call % |
| Proactive care | 60% savings × proactive-applicable call % |

Replace `MONTHLY_VOLUME` and `COST_PER_CALL_USD` in `aggregator.py` with actuals.

---

## Configuration Reference

All runtime parameters are CLI arguments with documented defaults.

### `run_pipeline.py`

| Flag | Default | Description |
|------|---------|-------------|
| `--n` | 100 | Calls to analyze |
| `--seed` | 42 | RNG seed for HF sampling |
| `--offset` | 0 | Conversations to skip |
| `--delay` | 2.0 | Seconds between Groq calls |

### `run_batches.py`

| Flag | Default | Description |
|------|---------|-------------|
| `--batches` | 5 | Number of sequential batches |
| `--n` | 20 | Calls per batch |
| `--seed` | 42 | Shared seed across all batches |
| `--delay` | 2.0 | Seconds between Groq calls |
| `--skip-merge` | false | Skip post-batch merge + QA |

### `qa_audit.py`

| Flag | Default | Description |
|------|---------|-------------|
| `--file` | latest | Path to full_results JSON |
| `--threshold` | 60 | Min score to count as passing |

### Environment variables (`.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes | Groq API key (free tier at console.groq.com) |

---

## Running Locally

### Quick start (3-call smoke test)

```bash
cp .env.example .env          # add your GROQ_API_KEY
pip install -r requirements.txt
python run_pipeline.py --n 3
streamlit run dashboard/app.py
```

### Full 100-call run (single batch)

```bash
python run_pipeline.py --n 100
```

### Full 100-call run (5 batches of 20, with resume support)

```bash
python run_batches.py --batches 5 --n 20
```

### Resume a killed batch

Restart with the exact same flags. Checkpointed calls are skipped automatically:

```bash
# Original run was killed at call 12/20
python run_pipeline.py --n 20 --offset 0 --seed 42
# → Loads outputs/.checkpoint_offset0_n20_seed42.jsonl (12 records)
# → Analyzes only calls 13–20
```

### Run QA audit standalone

```bash
python qa_audit.py                              # audit latest results
python qa_audit.py --file outputs/full_results_combined_20260517_123456.json
python qa_audit.py --threshold 70               # stricter pass bar
```

---

## Scaling to Production

| Concern | Current approach | Production path |
|---------|-----------------|-----------------|
| **Volume** | 100 calls / run | Parallel workers, multiple Groq API keys, or paid tier |
| **Dataset** | HuggingFace corpus | Replace `hf_loader.py` with your ACD / telephony connector |
| **Storage** | Local JSON / CSV | Write to object storage (S3, GCS) and a document DB |
| **Dashboard** | Local Streamlit | Deploy to Streamlit Cloud, or port to Next.js + a charting lib |
| **Scheduling** | Manual | Wrap `run_batches.py` in a cron job or Airflow DAG |
| **Model** | Groq free tier | Groq paid tier, or self-host Llama 3.3 70B via vLLM |
| **Prompt** | Static `.txt` file | Versioned in a prompt registry; A/B tested against QA scores |

---

## Known Limitations

1. **Sample bias** — The HuggingFace corpus is a public dataset, not your calls.
   KPIs and distributions reflect this corpus, not your actual call centre.

2. **Cost estimates are illustrative** — The $6.00/call and 100K/month numbers
   are industry benchmarks. Replace with your ACD data before presenting to executives.

3. **LLM hallucination** — The model may infer fields not explicitly stated in the
   transcript. The QA audit catches structural errors but not factual ones. Manual
   spot-checking of 5–10% of results is recommended before the first production run.

4. **Timestamp sensitivity** — Phase durations depend on the model correctly reading
   HH:MM:SS timestamps. Very long or poorly formatted transcripts may have lower
   phase accuracy.

5. **Free-tier rate limits** — Groq free tier caps at 30 req/min and 14,400/day.
   A 100-call run uses <1% of the daily limit. A 10,000-call run requires paid tier
   or multi-key distribution.

6. **No real-time streaming** — The pipeline is batch-oriented. Live call analysis
   would require a streaming architecture (e.g., Kafka → real-time Groq calls →
   streaming dashboard).
