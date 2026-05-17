# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [1.0.0] — 2026-05-17

### Added
- **Batch orchestrator** (`run_batches.py`) — runs N×M sequential batches with subprocess isolation; auto-invokes merge and QA audit on completion
- **Checkpoint / resume system** — each successful Groq API call is persisted to `outputs/.checkpoint_{key}.jsonl` immediately; a killed process loses no work; restart with the same flags to resume
- **Token cost tracking** — `_prompt_tokens`, `_completion_tokens`, `_total_tokens` injected into every result dict from `response.usage`; `pipeline/token_tracker.py` computes USD cost per call and per run
- **QA audit engine** (`qa_audit.py`) — 100-point scoring across completeness (30), enum validity (25), consistency (25), and plausibility (20); dataset verdict PASS/FAIL at configurable threshold
- **Merge utility** (`merge_outputs.py`) — auto-discovers batch JSONs, deduplicates by `call_id`, re-aggregates, and updates `summary.json`
- **Structured logging** (`pipeline/logger.py`) — INFO to stdout, DEBUG to `outputs/pipeline.log`; all pipeline modules use `get_logger(__name__)`
- **Offset-based batching** — `--offset` flag on `run_pipeline.py` guarantees non-overlapping conversation samples across runs
- **`ARCHITECTURE.md`** — full technical reference covering data flow, LangGraph state schema, rate limiting strategy, batch/checkpoint design, QA framework, cost model, and scaling guide
- **`PRD.md`** — product requirements document with goals, personas, functional requirements, and success metrics
- **`docs/executive_summary_template.md`** — structured template for presenting pipeline findings to executives

### Changed
- `pipeline/analyzer.py` — rewritten to include token tracking, checkpoint saves, and structured logging; all `print()` calls replaced with `log.*`
- `pipeline/graph.py` — `PipelineState` extended with `offset`, `checkpoint_key`, `token_usage` fields; all nodes log via `get_logger`; export node embeds token usage in manifest and `summary.json`
- `pipeline/aggregator.py` — now calls `token_summary()` and embeds `token_usage` block in all outputs
- `run_pipeline.py` — `--offset` flag added; checkpoint key auto-generated from run parameters; token cost displayed on completion

### Fixed
- **pandas 3.x date parsing** — replaced `utc=True` with `format="mixed"` in `hf_loader.py`; previously caused ~92% of timestamps to be coerced to NaT
- **Plotly 6.7 keyword conflict** — all `update_layout(**PLOTLY_LAYOUT, key=value)` calls split into two sequential `update_layout()` calls to avoid `TypeError: multiple values for keyword argument`

---

## [0.1.0] — 2026-05-10

### Added
- Initial LangGraph pipeline: 5-node StateGraph (fetch → validate → analyze → aggregate → export)
- HuggingFace streaming loader for `talkmap/telecom-conversation-corpus`
- 70-field extraction prompt for telecom call transcripts
- Groq API integration with `llama-3.3-70b-versatile`, exponential backoff on rate limits
- Streamlit executive dashboard with 9 panels (KPIs, cost levers, phase breakdown, sentiment, agent performance)
- Per-call CSV and full results JSON export
- Run manifest with call counts and failure tracking
