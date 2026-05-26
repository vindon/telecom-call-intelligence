# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [3.0.1] — 2026-05-26

### Fixed

- **ReAct quota circuit breaker** (`pipeline/analyzer.py`, `pipeline/agents/extraction_agent.py`) — module-level `_react_quota_exhausted` flag trips on the first 429 `ClientError` inside `gap_fill_transcript()`; all subsequent gap-fill calls return `first_pass` immediately, preserving daily quota for main extraction across batches. `ExtractionAgent._react_loop()` also short-circuits the full loop when the flag is already set.
- **Free-tier quota documentation** — corrected `pipeline/config.py` comment and `CLAUDE.md` from wrong "500 RPD" to accurate **20 RPD / 15 RPM** for `gemini-2.5-flash-lite`. Added note recommending `gemini-2.0-flash-lite` (1 500 RPD) for multi-batch production runs.

### Changed

- **Dashboard rebuilt** (`dashboard/app.py`) — complete redesign from dark hacker theme to professional executive-grade light theme:
  - **Hero banner**: dark navy-to-blue gradient (`#0F172A → #1E40AF`) with circular ambient highlights; title "**Telecom Call Intelligence**"; subtitle "Customer Call Metadata Segmentation"; white tagline for Cost-to-Serve / Phase Intelligence / Agentic AI Opportunity Sizing
  - **Typography**: Inter 800-weight, 2.6rem KPI values with tight letter-spacing; all section sizes increased
  - **KPI cards**: white with coloured 4px top-accent border, drop shadow, hover lift
  - **Charts**: white background, `#F1F5F9` gridlines, 14px semibold titles — all Plotly charts on light
  - **Traffic signal action table**: custom HTML table replaces `st.dataframe`; glowing CSS dots — 🔴 CRITICAL / 🟡 HIGH / 🟢 QUICK WIN — with pill badges and priority legend
  - **7 sections**: Core KPIs · Cost Opportunity · Phase & Waterfall · Issue Mix & Deflection · Agent & Sentiment · Upsell Intelligence · Executive Action Plan

---

## [3.0.0] — 2026-05-26

### Added — Autonomous Agentic Patterns

- **ReAct extraction loop** (`pipeline/agents/extraction_agent.py`, `pipeline/analyzer.py`) — per-transcript Observe → Reason → Act control loop; `score_field_coverage()` scores critical field presence after each extraction; `gap_fill_transcript()` issues a targeted retry prompt for null fields only; up to `REACT_MAX_ITERATIONS` extra passes per transcript; `react_stats` injected into `PipelineState` for telemetry
- **Chain-of-Thought prompts** — `_cot_reasoning` added as the mandatory first field in all LLM JSON responses; forces step-by-step reasoning before field extraction (ExtractionAgent) and before recommendations (InsightsAgent); zero extra API calls, works natively with `response_mime_type="application/json"`
- **InsightsAgent deliberation loop** (`pipeline/agents/insights_agent.py`) — 3-pass self-reflection cycle replacing the single-pass LLM call: Pass 1 Analyze (CoT, temp=0.3), Pass 2 Critique (self-grades each recommendation A/B/C on data-groundedness, specificity, non-duplication; temp=0.1), Pass 3 Synthesize (rewrites weak recommendations using critique; temp=0.3); graceful per-pass degradation; `deliberation_passes` and `critique` quality grade added to `agent_insights`; fixes the duplicate `rule_based_fallback` recommendation bug from v2.0
- **Vector memory** (`pipeline/vector_memory.py`) — semantic long-term memory using Gemini `text-embedding-004` (768-dim) with numpy cosine similarity; `VectorMemoryStore.add_run()` embeds each run's KPI summary; `query()` / `format_context()` retrieve top-K most similar historical runs for InsightsAgent context injection; TF-IDF bag-of-words fallback when API key unavailable (offline/test mode); persists to `outputs/vector_memory/` as `vectors.npy` + `index.json`; interface-compatible with ChromaDB/Pinecone swap
- **Security layer** (`pipeline/security.py`) — five components protecting every agent boundary:
  - `InputSanitizer` — 10 prompt injection patterns (DAN, jailbreak, XML role injection, Llama template injection, instruction override), 50 000-char token bomb cap, null byte / encoding attack cleanup, secret pattern redaction in source transcripts
  - `OutputSanitizer` — code execution patterns (`__import__`, `eval`, `exec`, `subprocess`, XSS) → `[CONTENT_FILTERED]`; response bomb check (32 KB cap); per-field string length cap (2 000 chars); secret redaction in LLM output fields
  - `AgentScopeGuard` — per-agent authorized tool set; cross-agent tool hijacking raises `SecurityViolation` before invocation
  - `SecretGuard` — Google/OpenAI API key, JWT, Bearer token, and password patterns scrubbed from state serialisation, log messages, and raw LLM responses; `assert_no_secrets_in_output()` called on every Gemini response before JSON parse
  - `RateLimiter` — sliding-window 15 req/60 s; `GEMINI_RATE_LIMITER.acquire()` called before every Gemini API call in `analyzer.py` and `insights_agent.py`; prevents runaway consumption from ReAct loops or injected loops
- **`SecurityViolation` exception** — typed exception with `check` and `detail` attributes; raised by all security components for uniform handling
- **Human approval gate** (`pipeline/graph.py` — `approval_gate_node`) — 7th node inserted between InsightsAgent and ExportAgent; `REQUIRE_HUMAN_APPROVAL=False` (default) is a transparent pass-through; when `True`, displays KPI summary + deliberation source, prompts `y/N` with configurable `APPROVAL_TIMEOUT_S` auto-approve; non-interactive environments (CI, EOF) auto-approve silently; rejection raises `RuntimeError` and halts cleanly; `approval_granted` added to `PipelineState`
- **LangSmith tracing** — `_configure_tracing()` called at `build_pipeline()` time; LangGraph auto-traces all 7 nodes when `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` are set; `LANGSMITH_PROJECT` constant in `pipeline/config.py`
- **49 new unit tests** (`tests/test_security.py`) — full coverage of all five security components; zero API calls; all 198 tests pass in < 6 seconds

### Changed

- **Pipeline nodes** — 6 → 7; `approval_gate_node` inserted between `insights` and `export`; `_banner()` signature updated to accept `str | int` for step label
- **`PipelineState`** — two new fields: `react_stats` (ReAct telemetry dict), `approval_granted` (bool)
- **`pipeline/config.py`** — 12 new constants: `REACT_MAX_ITERATIONS`, `REACT_QUALITY_THRESHOLD`, `DELIBERATION_ENABLED`, `MAX_CONCURRENT_EXTRACTIONS`, `REQUIRE_HUMAN_APPROVAL`, `APPROVAL_TIMEOUT_S`, `LANGSMITH_PROJECT`, `VECTOR_MEMORY_ENABLED`, `VECTOR_MEMORY_PATH`, `VECTOR_MEMORY_TOP_K`, `MAX_TRANSCRIPT_CHARS`, `MAX_FIELD_STRING_LEN`, `MAX_RESPONSE_BYTES`
- **`pipeline/analyzer.py`** — `_build_user_message()` updated with `_cot_reasoning` CoT instruction; `INPUT_SANITIZER.sanitize_transcript()` and `GEMINI_RATE_LIMITER.acquire()` added to `analyze_transcript()`; `SECRET_GUARD` and `OUTPUT_SANITIZER` checks on every Gemini response; `_build_gap_fill_message()`, `score_field_coverage()`, `gap_fill_transcript()` added for ReAct
- **`pipeline/agents/extraction_agent.py`** — complete rewrite to add `_react_loop()` wrapping `analyze_batch()`; `SCOPE_GUARD.check()` called at agent start; `react_stats` returned in state
- **`pipeline/agents/insights_agent.py`** — complete rewrite with `_deliberation_loop()`, `_single_pass_llm()`, `_gemini_call()`, `_build_analyze_prompt()`, `_kpi_context()`, `_get_rich_context()`; three new prompt templates (`ANALYZE_PROMPT`, `CRITIQUE_PROMPT`, `SYNTHESIZE_PROMPT`); vector store retrieval in `_get_rich_context()`; `OUTPUT_SANITIZER.sanitize_insights()` on all outputs; `SECRET_GUARD` and `GEMINI_RATE_LIMITER` on all Gemini calls
- **`pipeline/graph.py`** — `_configure_tracing()` added; `VECTOR_STORE.load()` called at build time; `approval_gate_node` wired between `insights` and `export`
- **`requirements.txt`** — `langsmith>=0.1.0` added
- **Test count** — 149 → 198

### Fixed

- **InsightsAgent duplicate recommendations** — the v2.0 rule-based fallback padded with repeated "Implement Continuous Monitoring" entries; the deliberation loop produces 5 distinct, data-grounded recommendations; rule-based fallback also fixed to avoid duplicates

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
