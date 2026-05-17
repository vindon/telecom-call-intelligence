# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [2.0.0] — 2026-05-18

### Added — Agentic AI Architecture

- **6-agent multi-agent pipeline** (`pipeline/agents/`) — DataIngestionAgent, ExtractionAgent, QualityAgent, AggregationAgent, InsightsAgent, ExportAgent; each is stateless with `run(state: dict) -> dict`
- **InsightsAgent** — second Gemini LLM call synthesising KPIs into strategic recommendations (5 prioritised actions, 3 quick wins, 2 risk flags); graceful degradation to rule-based fallback on quota exhaustion
- **Governance layer** (`pipeline/governance.py`) — `BudgetGuard` (hard-stop at $5 USD), `QualityGate` (catastrophic failure at <40% pass rate), `PIIScanner` (6 PII pattern types with redaction), `AuditLog` (append-only structured event trace)
- **Agent memory system** (`pipeline/memory.py`) — persistent cross-run JSON store at `outputs/agent_memory.json`; tracks run history (last 50), failure log, quota events, model performance; injects historical context into InsightsAgent prompt
- **Tool registry** (`pipeline/tools.py`) — formal JSON-schema tool definitions for all 5 agent operations; uniform invocation audit trail with latency tracking; LLM-discoverable via `REGISTRY.manifest()`
- **Orchestrator** (`pipeline/orchestrator.py`) — `WorkPlanner` (ceiling-division batch planning), `AgentHealthMonitor` (per-agent success/failure tracking), `Orchestrator` (adaptive retry, process isolation, structured report)
- **Centralized config** (`pipeline/config.py`) — single source of truth for all constants: model names, temperatures, token limits, paths, governance thresholds, QA thresholds
- **Dynamic routing** — LangGraph `add_conditional_edges` bypasses AggregationAgent + InsightsAgent on catastrophic quality gate failure; pipeline always completes with an export
- **Unit test suite** (`tests/`) — 149 tests across governance, memory, orchestrator, tools, config, and graph; 0 tests depend on real API calls; < 2 second full run
- **`pyproject.toml`** — ruff, mypy, and pytest configuration unified in one file
- **`requirements-dev.txt`** — pytest, pytest-cov, pytest-mock, ruff, mypy, pre-commit
- **`Makefile`** — `make test`, `make lint`, `make check`, `make run`, `make run-batches`, `make dashboard`
- **`CLAUDE.md`** — AI assistant guide (conventions, what not to do, agent addition checklist)
- **`.pre-commit-config.yaml`** — ruff lint + format, secret detection, no-commit-to-main gate
- **`SECURITY.md`** — vulnerability disclosure policy
- **Updated CI** (`ci.yml`) — ruff lint, pytest, LangGraph compile check, tool registry validation, config module verification; GEMINI_API_KEY from GitHub Secrets

### Changed

- **LLM provider** — Groq + `llama-3.3-70b-versatile` → Google Gemini 2.5 Flash Lite via `google-genai` SDK
- **`run_batches.py`** — now delegates entirely to `Orchestrator`; adds `--retries` and `--rpm` flags
- **`pipeline/analyzer.py`** — imports MODEL, MAX_TOKENS, TEMPERATURE from `pipeline/config.py`; `MAX_TOKENS` raised from 2048 → 8192; `thinking_budget=0` added to prevent JSON truncation
- **`pipeline/agents/insights_agent.py`** — imports INSIGHTS_MODEL, INSIGHTS_TEMPERATURE, MAX_OUTPUT_TOKENS from `pipeline/config.py`
- **`ARCHITECTURE.md`** — updated with Orchestrator section, governance/memory/tools in file tree
- **`CONTRIBUTING.md`** — updated setup instructions, branch strategy, agent addition checklist
- **`requirements.txt`** — `google-generativeai` (deprecated) replaced with `google-genai>=1.0.0`

### Fixed

- **JSON truncation** — Gemini 2.5 thinking tokens consumed extraction token budget; fixed by `thinking_budget=0` + `MAX_TOKENS=8192`
- **Model quota** — switched from `gemini-2.5-flash` → `gemini-2.5-flash-lite` when daily quota exhausted; model selection now in centralised config

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
