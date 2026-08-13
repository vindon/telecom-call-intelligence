# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [4.6.0] — 2026-08-13

### Fixed — Architecture audit: dead code, duplicated seams, broken interface promise

A deep-module architecture review (`mattpocock-skills:codebase-design`) of `pipeline/` surfaced six findings, all fixed:

- **`vector_memory.VECTOR_STORE.add_run()` was never called.** The module's own docstring claimed "Called by ExportAgent at the end of each pipeline run" — it wasn't. `ExportAgent` now embeds each run's KPI profile (FCR/AHT/escalation/AI-resolvable) into the vector store after every non-emergency export, guarded by `VECTOR_MEMORY_ENABLED` and never allowed to fail the export itself. Until this fix, `InsightsAgent`'s semantic nearest-run retrieval (`_get_rich_context()`) was querying a store that no run had ever written to.
- **`MEMORY_PATH` was defined twice** (`config.py` and `memory.py`, separately-valued constants that happened to agree). `memory.py` now imports it from `config.py`.
- **Anthropic/Gemini/NVIDIA client construction was duplicated across 6 sites** (`analyzer.py`, `agents/extraction_agent.py`, `agents/insights_agent.py`, `vector_memory.py`, `api/main.py`, `demo/app.py`), each independently re-applying the `timeout=`/`max_retries=1` policy from CLAUDE.md's spend-control rule. New `pipeline/llm_clients.py` (`get_anthropic_client()`/`get_gemini_client()`/`get_nvidia_client()`) is now the single seam; every call site delegates to it.
- **The Gemini-quota and NVIDIA-unavailable circuit breakers were the same logic reimplemented twice** (module-level bool + sentinel file, tripped via `global` on a timeout/quota error). New `pipeline/circuit_breaker.CircuitBreaker` is shared by both; `GEMINI_QUOTA_SENTINEL`/`NVIDIA_UNAVAILABLE_SENTINEL` moved into `config.py` as the single source for paths `orchestrator.py` also needed (it was independently reconstructing the same two paths a third time to clear them at run start).
- **`governance.AuditLog`'s 6 `record_*` methods each repeated the same `AuditEntry(timestamp=self._now(), ...); self._entries.append(...)` boilerplate.** Extracted a private `_append()` helper; public methods and every call site unchanged (each method still enforces its own truncation/shape invariant — e.g. `record_pii` truncating `call_id` to 12 chars — so this was a boilerplate fix, not an interface collapse).
- **`pipeline/tools.py`'s `ToolRegistry` was dead code.** Zero call sites invoked `REGISTRY` — every agent called the underlying modules directly. Its tool implementations had also drifted from the agents' real behavior (`_export_results` wrote one file; the real `ExportAgent` writes seven), so wiring agents through it would have meant duplicating agent logic a second time rather than removing duplication. Deleted, along with `tests/test_tools.py` and the now-unneeded `pipeline/tools.py` ruff per-file-ignore.

Net: 399 tests (was 404 — +15 new across `test_export_agent.py`/`test_llm_clients.py`/`test_circuit_breaker.py`, −20 for the removed `test_tools.py`).

---

## [4.5.0] — 2026-08-09

### Added — Data Quality Gate (phase reconciliation, timestamp ground truth, transcript completeness)

- **`qa_audit.check_data_quality()`** — three deterministic (non-LLM) checks run per call in `QualityAgent`, alongside the 100-pt QA score, and gate aggregation the same way LOW-grade records do:
  - `check_phase_reconciliation()` — sum of the 6 sequential phases (welcome, discovery, diagnosis, resolution, hold, closing) must reconcile to `total_duration_seconds`
  - `check_timestamp_ground_truth()` — `total_duration_seconds` cross-checked against `raw_duration_seconds`, threaded through from the source dataset's own turn timestamps (`hf_loader.py` → `data_agent.py` → `extraction_agent.py`)
  - `check_transcript_completeness()` — new `transcript_truncated`/`truncation_reason` schema fields (LLM-graded), corroborated by a free heuristic (`looks_truncated_heuristic()`)
- Dataset-level `data_quality_pass_rate_pct` rolls into `qa_report`/`summary.json`; a computed `aht_disclaimer` is written into the dashboard's `summary.json` when it drops below `QUALITY_WARN_RATE`, rendered as a live banner (`.data-disclaimer` in `dashboard/app.py`)
- **`governance.QualityGate`** — extended to check `data_quality_pass_rate_pct` as an independent catastrophic-failure dimension alongside the QA score. Previously blind to it: a run could score ~100% on the QA score while catastrophically failing phase reconciliation and the gate would never fire.
- **`retroactive_dq_audit.py`** — new standalone script applying the gate to already-processed batches without any new LLM calls; phase reconciliation runs at full strength on existing records, timestamp ground truth is backfilled by deterministically re-fetching the original transcript slice (free, from the local CSV)

### Fixed — Phase-reconciliation false positives (root cause)

- `check_phase_reconciliation()` was summing all 8 phase-duration fields as mutually-exclusive sequential segments. Two of them — `phase_upsell_duration_seconds` and `phase_relationship_building_duration_seconds` — describe activity happening *during* another phase (an upsell pitch mid-diagnosis), not additional wall-clock time. Verified against 200 real extractions: the 6 truly-sequential fields already summed exactly to `total_duration_seconds` on 77%+ of calls; summing all 8 produced false-positive failures on ~73% of otherwise-correct records. Fields split into `SEQUENTIAL_PHASE_FIELDS` (summed, gated) and `OVERLAY_PHASE_FIELDS` (excluded from the sum, given a non-blocking `check_overlay_plausibility()` bound instead). `prompts/system_prompt.txt` rule 3 rewritten to match — it previously told the model "every second belongs to exactly one phase," which is factually wrong for the overlay fields. **Re-verified against the same 200 already-extracted calls with zero new API spend: data-quality pass rate went from 29.0% (old formula) to 92.5% (corrected formula).**
- `hf_loader.py` — the offset-based batch sampling used overlapping candidate windows (`all_ids_ordered[offset:offset+n*6]`) for offsets spaced by `n`, and `random.sample()` with a fixed seed against overlapping-but-shifted lists reliably repicked the same underlying conversation IDs. A 10-batch/200-call run only produced 136 truly unique conversations. Replaced with a single deterministic shuffle of the full ID universe sliced into disjoint ranges per offset (`_select_ids()`).
- `merge_outputs.py` — was aggregating every merged record unconditionally, bypassing the data quality gate that `QualityAgent` already enforces inside a single pipeline run, so a multi-batch merge could silently re-include calls already known to fail. Now applies the gate before computing KPIs, and reports `data_quality_pass_rate_pct` / a computed `aht_disclaimer` the same way a single run does.
  - **Follow-up bug, found within minutes of the first fix**: the initial version only computed `_dq_gate_passed` for records *missing* the tag, trusting any tag already present — but 78 of the 139 already-tagged 2026-08-09 records were tagged by `QualityAgent` using the OLD, buggy phase-reconciliation formula, *before* it was corrected earlier the same day. The "not already tagged" guard meant those stale, pre-fix verdicts kept being trusted. First regenerated `summary.json` showed 94/217 trusted — recomputing unconditionally for every record (no tag ever trusted; recomputation is pure Python, zero API cost, so there's no reason to skip it) gives the actually-correct **172/217 (79.3%)**, above `QUALITY_WARN_RATE` — no disclaimer needed on this run.
- `Orchestrator._run_task()` — the `subprocess.TimeoutExpired` and generic-exception handlers never recorded the failure in `agent_health` (only the exit-code≠0 branch did), so hangs and crashes were invisible in the health summary.
- Assorted stale docstrings/comments referencing moved functions (`data_agent.py::_looks_truncated` → `qa_audit.py::looks_truncated_heuristic`) and the removed retry mechanism.

### Added — Strict human-intervention failure policy

- **`Orchestrator.run()`** — the first batch task failure now halts the entire run immediately: no auto-retry, no proceeding to remaining batches. Writes `outputs/.halted_for_human_review.json`, which blocks every subsequent `run_batches.py` invocation until cleared with `--acknowledge-halt`. Replaces an auto-retry loop that, in production, silently retried a hung batch twice before a human noticed the wasted spend (~$1.8 of discarded work from two batches each retrying into the same hang).
- Removed the now-dead `max_retries`/`can_retry`/`attempts`/`DEFAULT_MAX_RETRIES` retry-count mechanism entirely rather than leaving it as an inert config flag.

### Added — Spend control for API hangs

- Every LLM client (`anthropic.Anthropic`, `OpenAI`, `genai.Client`) across the codebase (`analyzer.py`, `extraction_agent.py`, `insights_agent.py`, `vector_memory.py`, `api/main.py`, `demo/app.py`) now sets an explicit `timeout=` (`EXTRACTION_API_TIMEOUT_S=60`, `INSIGHTS_API_TIMEOUT_S=45` — config.py) and `max_retries=1`. Previously none set a timeout, defaulting to the SDK's 600s — the same order of magnitude as `Orchestrator`'s own 600s per-batch subprocess timeout, so a slow provider could hang right up to that limit and get the whole batch killed and retried from scratch.
- **NVIDIA NIM circuit breaker** (`insights_agent.py`) — on a confirmed timeout, marks NVIDIA unavailable for the rest of the run (`outputs/.nvidia_unavailable` sentinel, cleared by `Orchestrator` at the start of a new run) so subsequent passes/batches skip straight to the Claude fallback instead of re-paying the timeout on every call.

### Added — Pre-flight smoke test

- **`smoke_test.py`** — run before any paid batch: free checks (env vars, config sanity, full test suite, offset-disjointness against the actual planned batch parameters) plus an opt-in `--live` flag that runs one real ~$0.01-0.02 call through the full pipeline with a hard 150s timeout, verifying completeness, insights generation, and prompt-cache engagement. Self-cleaning — restores `summary.json` and deletes its own throwaway artifacts.

### Changed

- `run_batches.py` — added `--start-offset` (guarantee a fresh, non-overlapping sample vs. previous runs) and `--acknowledge-halt`; removed `--retries`.
- `pipeline_version` string corrected from stale `"4.1-multi-agent"` to match this release.

### Added — Success metrics surfaced honestly across every customer-facing surface

Of 217 real calls processed to date, 172 (79.3%) pass the full QA + data-quality gate; 45 are excluded with three named, categorized reasons (`phase_reconciliation` ×33, `transcript_truncation` ×15, `timestamp_ground_truth` ×1). This funnel — trusted vs. excluded, with reasons — is now presented consistently everywhere the product is shown, rather than only living in `summary.json`:

- **`pipeline/agents/quality_agent.py`** / **`merge_outputs.py`** — both now compute and emit `data_quality_failure_breakdown` (a `{failure_type: count}` dict) alongside the existing `data_quality_pass_rate_pct`/`n_trusted_for_aggregation`/`n_merged_total` fields in `qa_summary`, so the reason-level breakdown is available to every downstream consumer, not just the pass/fail rate.
- **`docs/executive_deck.html`** — new Slide 11/15 "Data Quality — The Honest Numbers"; cover and closing slides updated from stale 78-call figures to 172 verified / 217 processed.
- **`demo/architecture.html`** — new `#quality` section "Data Quality & Reliability" (stat grid + reasons table + enterprise-scale callout); Cost section numbers refreshed to the current 172-call sample (1,427,140 tokens, $2.365, 1.375¢/call).
- **`README.md`** — new "Proven at scale" section with the same funnel and reason breakdown.
- **`dashboard/app.py`** — new "Data Quality Gate — The Honest Numbers" panel in the QA & Pipeline Health tab: a 4-card verification funnel (processed / trusted / excluded-data-quality / excluded-low-QA) plus a live `chart_dq_failure_breakdown()` bar chart of exclusion reasons, both reading directly from `summary.json`'s `qa_summary` — no hardcoded numbers.

---

## [4.4.0] — 2026-06-24

### Added — Standalone Live Demo App

- **`demo/app.py`** — standalone FastAPI server exposing `/analyze` endpoint; primary path uses real Claude Haiku extraction via `pipeline.analyzer`; automatic fallback to pre-computed mock results when `ANTHROPIC_API_KEY` is absent or `DEMO_MOCK_ONLY=1` is set; full `InputSanitizer` / `OutputSanitizer` coverage at API boundary
- **`demo/index.html`** — self-contained demo UI (no build step); accepts raw transcript text, streams the 6-agent pipeline execution with per-stage timing, and renders the structured extraction output inline
- `make demo` target — launches `uvicorn demo.app:app --port 8001 --reload` from project root
- `Makefile` help updated with demo target description

### Added — BCG-Style Executive Deck

- **`docs/executive_deck.html`** — 12-slide cost intelligence report in BCG narrative style: problem framing, pipeline architecture, KPI evidence, cost-driver segmentation, AI roadmap, ROI model, and call to action; self-contained HTML (no external dependencies)

### Added — Dashboard: Live Pipeline Demo Tab

- Second Streamlit tab **"Live Pipeline Demo"** — animated 7-node LangGraph pipeline walkthrough with per-stage progress indicators, timing simulation, and structured output preview; no API call required; demonstrates the full agent sequence visually

### Added — Dashboard: Enhancements (Steps 1–4)

- **Mobile CSS** — responsive breakpoints for tablet and phone viewports; tab navigation collapses gracefully
- **ROI Calculator** — interactive sidebar widget; inputs: call volume, AHT, agent cost/hr; outputs: monthly cost-to-serve baseline, estimated avoidable-call saving, AI automation saving
- **PDF Export** — print-stylesheet activated via `window.print()` button; hides Streamlit UI chrome; renders all 6 dashboard sections as a single-page document
- **QA Tab** — new dashboard tab showing per-call QA scores, exclusion reasons, and score distribution histogram sourced from the active `qa_report_{ts}.json`

### Fixed

- Streamlit `theme.primaryColor` set to Verizon red `#CD040B` (`.streamlit/config.toml`) — was falling back to default teal
- Hero background changed to flat `#CD040B` — the prior `135deg` gradient rendered unevenly across screen widths
- Live Pipeline Demo animation appeared above the trigger button — moved below
- `dashboard/app.py` ruff CI failures resolved — F401 unused imports removed, line-length violations fixed; `make lint` and `make check` both pass clean

### Changed

- README updated with Live Demo Streamlit badge and hero CTA button linking to `https://telecom-call-intelligence.streamlit.app/`

---

## [4.3.0] — 2026-06-16

### Added — Issue Tree (Section 6) and `issue_breakdown` aggregator field

- `pipeline/aggregator.py`: `_segment_masks(df)` — returns 4 mutually-exclusive, priority-ordered `pd.Series` masks (prevent, automate_self_serve, automate_agentic, human); shared by both `_resolution_segments` (unchanged output) and the new breakdown function
- `pipeline/aggregator.py`: `_category_resolution_breakdown(df, n, baseline)` — cross-tab of `issue_1_category` × resolution segment × `issue_1_resolution_method`; returns `{"categories": [...], "build_queue": [...]}` sorted by dollar impact, written to `aggregate_metrics()["issue_breakdown"]`
- Dashboard Section 6 completely redesigned: replaces the static priority table with a data-driven **Issue Tree** showing what the agent actually did on each call type, how each call maps to Prevent / Automate / Human, and a ranked build queue (top-4 opportunities by monthly $ impact across all categories)
- 22 new tests: `TestSegmentMasks` (1) + `TestCategoryResolutionBreakdown` (8) + update to `TestTopLevelStructure` (new `issue_breakdown` key); suite is now **364 tests**

### Changed — dashboard hero copy

- Headline changed to **"Telecom Cost Intelligence for Care Calls"** with a subtitle identifying cost-to-serve drivers and proactive issue-resolution opportunities from real call transcripts
- Eyebrow changed from "Telecom Call Intelligence" to "Care Call Cost Analysis"

---

## [4.2.0] — 2026-06-15

### Added — Phase Drill-Down and phase-time P&L

- `pipeline/aggregator.py`: `_phase_pnl()` allocates the monthly cost baseline across **Serve (P1–P4 Welcome→Resolution) / Sell (P5 Upsell) / Retain (Hold+Closing)** in proportion to average phase duration — a time-based P&L, written to `cost_levers.{serve,sell,retain}_{time_pct,cost_usd}`
- `pipeline/aggregator.py`: `_phase_drilldown()` ranks `issue_1_category` by average duration within Discovery/Diagnosis/Resolution/Upsell (top 5 per phase), with per-intent **agent stall rate** (`agent_disproportionate_time_phase` match rate) — written to `phase_drilldown`
- Dashboard: new **Section 2 — Phase Drill-Down**, a tabbed view (one tab per phase) showing the top-5 intents driving that phase's handle time and where agents stall
- Dashboard: hero cost panel ("Insights from N Calls Analysed") now shows **Cost to Serve / Sell / Retain** allocated by phase-time share of AHT (replaces the prior issue-category-based heuristic split)
- 9 new aggregator tests (29 total) covering `_phase_pnl` and `_phase_drilldown`; suite is now 354 tests

### Fixed — dashboard segmentation and action-plan consistency

- Replaced the bogus 100%/0% Prevent/Automate/Human split with the correct mutually-exclusive, priority-ordered segmentation (`_resolution_segments`); hero headline generalised to "Call Data Segmentation: Prevent, Automate — or Escalate"
- Section 6 (Prioritised Action Plan) reordered so CRITICAL items lead by dollar impact; "Build Agentic AI Agents" rescoped to reference the Section 4 roadmap instead of a flat estimate

### Removed

- Dashboard "Performance Trends Across Runs" section (`load_run_history()`, `chart_trend()`) — multi-run trend charts did not produce a coherent narrative; removed along with the issue-category-based `_cost_buckets()` heuristic it shared inputs with

---

## [4.1.1] — 2026-06-11

### Added — full unit-test coverage for the agent layer

- **118 new tests (224 → 342)** covering the previously untested modules: all 6 agents (`tests/test_agents/`), `analyzer`, `aggregator`, `hf_loader`, `token_tracker`, and the FastAPI wrapper (`tests/test_api.py`)
- All LLM calls stubbed at module boundaries — the suite still runs with zero API calls in ~6 s; governance singletons (BudgetGuard, QualityGate, PIIScanner) are exercised for real, per the no-mocking rule
- Regression tests pinned for the v4.1.0 fixes: `False`/`0` not treated as missing fields, gap-fill token spend counted toward BudgetGuard, emergency export preserving `summary.json`, and the cross-process Gemini quota sentinel
- New `conftest.py` factories: `make_record` (schema-accurate extraction record matching `qa_audit` REQUIRED_FIELDS/ENUM_RULES) and `make_transcript` (hf_loader output schema)

### Known gap (documented, unchanged)

- `_rule_based_insights()` pads with only 3 generic recommendations, so an all-healthy KPI profile yields 3 (not 5) recommendations — only the LLM paths guarantee exactly 5

---

## [4.1.0] — 2026-06-10

### Fixed — ReAct correctness and cost accounting

- **`_CRITICAL_FIELDS` schema mismatch** (`pipeline/analyzer.py`): `fcr`, `issue_category`, and `resolution_status` did not exist in the extraction schema, capping field coverage at 57% and forcing a wasted gap-fill API call on *every* transcript (~2× extraction cost). Replaced with the real schema fields (`fcr_indicator`, `issue_1_category`, `escalation_required`); phantom columns no longer leak into exported CSVs
- **Boolean false counted as missing**: `value in (None, "", 0)` treated `False` as a missing field (False == 0 in Python) — new `_is_missing()` helper treats only null/empty-string as missing
- **Gap-fill tokens now counted**: ReAct retry token usage was discarded, so `BudgetGuard` under-enforced; gap-fill prompt/completion tokens now accumulate into the per-call token totals
- **Orchestrator retry off-by-one**: `attempts` was incremented in both `run()` and `_run_task()`, silently consuming one retry per task; `attempts` now counts retries only
- **Emergency export no longer blanks the dashboard**: on the quality-gate-failure path, `summary.json` (empty metrics) is preserved instead of overwritten
- **Cost-model decision record** showed $0.00/$0.00 pricing due to a key-name mismatch (`price_input_per_mtok` vs `price_input_per_mtok_usd`)
- **False sanitizer warnings**: `sanitize_insights()` was applied to critique-pass responses (different schema); per-pass responses now use the generic sanitizer, with `sanitize_insights()` applied once to the final dict

### Changed — config as single source of truth

- `INSIGHTS_MODEL` is now the NVIDIA NIM model (`meta/llama-3.3-70b-instruct`), replacing `NVIDIA_INSIGHTS_MODEL`; removed the dead Gemini insights fallback (`_gemini_call`) — the chain is NIM → Claude → rule-based as documented
- All hardcoded `Path("outputs")` occurrences replaced with `pipeline.config.OUTPUT_DIR` (governance, orchestrator, export agent, logger, tools, qa_audit, merge_outputs)
- Dead config constants wired up: `DEFAULT_*` now drive CLI argparse defaults; `QA_PASS_THRESHOLD`/`QA_HIGH_THRESHOLD` drive QA grading; `MAX_TRANSCRIPT_CHARS`/`MAX_FIELD_STRING_LEN` drive sanitizer limits; `VECTOR_MEMORY_ENABLED` gates vector memory load/retrieval
- `ExportAgent` now instruments `DecisionLogger` (new `export_scope` decision type); `ExtractionAgent` no longer stores logger state on the shared singleton
- `SecretGuard` sensitive-key set extended with `anthropic_api_key`, `nvidia_api_key`, `langchain_api_key`
- InsightsAgent now records per-pass LLM token usage in `agent_insights.token_usage`
- Orchestrator quota events record the actual configured model/provider instead of hardcoded "Google AI Studio"

### Tooling

- `ruff` F401 (unused imports) no longer globally ignored; `api/` added to lint/format targets; `make check` (lint + mypy + tests) passes clean
- `.gitignore` now covers `telecom_200k.csv` (682 MB) and all `outputs/` artifacts except `summary.json`
- `pyproject.toml` version aligned to 4.1.0; stale Gemini-era docstrings and agent-count mismatches corrected across the codebase

---

## [4.0.0] — 2026-06-01

### Added — Agent Decision Traceability

- **`pipeline/decision_log.py`** — new module: `DecisionRecord` dataclass (record_id, agent, decision_type, timestamp, decision, reason, evidence, call_id, confidence, alternatives); `DecisionLogger` (scoped to one agent invocation, accumulates across pipeline via `finalize()`); `summarize_decisions()` for dashboard embedding
- **`PipelineState.decision_log`** — new `list` field accumulating `DecisionRecord` dicts across all 7 agents
- **Decision logging in every agent:**
  - `DataIngestionAgent`: `transcript_skip` (every rejected transcript with exact reason) + `pii_redaction`
  - `ExtractionAgent`: `react_trigger` (per-call, when coverage < threshold) + `react_gap_fill_outcome` (batch summary)
  - `QualityAgent`: `qa_exclusion` (every LOW exclusion) + `qa_grade_assignment` (borderline MEDIUM 60–65) + `quality_gate_outcome`
  - `AggregationAgent`: `aggregation_scope` + `cost_model_applied`
  - `InsightsAgent`: `provider_selected` (with full fallback chain reasoning) + `deliberation_outcome`
  - `ApprovalGate`: `approval_decision` (approved / rejected / auto-approved)
  - `GraphRouter`: `routing_decision` (normal vs emergency export path)
- **`ExportAgent`**: writes `decisions_{ts}.json` (total count, summary by agent/type, full records array); embeds `decision_summary` in `summary.json`; adds `decisions` path to `export_paths` and `run_manifest`
- **`tests/test_decision_log.py`** — 24 new tests (DecisionRecord fields and serialisation, DecisionLogger accumulation and idempotency, summarize_decisions coverage)

### Added — Plug-and-Play Model Architecture

- **`EXTRACTION_MODEL`-driven everything** — changing `pipeline/config.py → EXTRACTION_MODEL` now automatically propagates to: API client selection (Anthropic vs Gemini), rate limiter (`CLAUDE_RATE_LIMITER` vs `GEMINI_RATE_LIMITER`), cost accounting (`token_tracker._resolve_pricing()`), provider label in aggregator output, budget guard enforcement, and API key startup validation
- **`pipeline/token_tracker.py`** — rewritten with `_PRICING` dict keyed by model prefix; `_resolve_pricing(model)` resolves provider, input/output prices, and tier note; `PRICE_INPUT_PER_MTOK`, `PRICE_OUTPUT_PER_MTOK`, `PROVIDER` exported as module-level constants
- **`pipeline/aggregator.py`** — `inference_provider` and `model` fields derived from `EXTRACTION_MODEL`, not hardcoded
- **`api/main.py`** — extraction client selection now provider-aware; `HealthResponse` reflects actual provider; error messages name the correct API key
- **`pipeline/agents/extraction_agent.py` `_react_loop`** — client creation is now provider-aware (was hardcoded Gemini, caused `AttributeError` when Claude was configured)

### Added — Startup & Budget Safety

- **Model-aware startup key validation** (`run_pipeline.py`) — replaces hardcoded `GEMINI_API_KEY` check; validates `ANTHROPIC_API_KEY` when `EXTRACTION_MODEL` starts with `claude`, `GEMINI_API_KEY` otherwise; `NVIDIA_API_KEY` absence prints INFO warning (optional, graceful fallback); exits immediately with a clear message rather than failing 30–60s into the run
- **`BudgetGuard` wired to config** (`pipeline/governance.py`) — singleton now reads `max_cost_usd` from `BUDGET_USD` in `config.py` (was hardcoded `5.00` — changing config had no effect); `QualityGate` similarly reads `MIN_PASS_RATE`
- **`config.py BUDGET_USD` commentary** — added provider-specific cost guidance: Claude Haiku ~$0.0076/call → $5.00 ≈ 650 calls; Gemini ~$0.0008/call → $5.00 ≈ 6 000 calls
- **Startup banner** (`run_pipeline.py`) — now shows actual `EXTRACTION_MODEL` + provider from `token_tracker.PROVIDER` and `BUDGET_USD`; was hardcoded `"gemini-2.5-flash-lite (Google AI Studio)"`

### Fixed

- **Budget estimation used Gemini pricing for Claude** (`extraction_agent.py`) — `est_cost = total_tokens / 1_000_000 * 0.10` hardcoded Gemini rate; with Claude Haiku ($4.00/MTok output) this underestimated cost by ~40×; `BudgetGuard` would not have tripped on real overruns. Fixed: now uses `token_tracker.cost_usd(prompt_tokens, completion_tokens)` which resolves pricing from `EXTRACTION_MODEL`
- **`_react_quota_exhausted` circuit breaker tripped on Claude 429** (`analyzer.py`) — the flag was designed for Gemini daily quota exhaustion (permanent for the day) but also triggered on Claude's transient per-minute 429s, permanently disabling gap-fill for the entire run. Fixed: circuit breaker only trips for Gemini; Claude 429 logs a warning and skips the individual call
- **`api/main.py` endpoint broken with Claude** — two critical bugs: (1) `"transcript"` key instead of `"transcript_text"` caused `KeyError` in `_build_user_message()`; (2) hardcoded Gemini client creation even when `_USE_CLAUDE=True` caused `AttributeError`. Both fixed
- **Anthropic key not in `SecretGuard`** — `sk-ant-*` key pattern was absent from `_SECRET_PATTERNS`; Anthropic API keys would not be detected or redacted by security layer. Fixed: added `re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}")`
- **NVIDIA not in secret env-var pattern** — `NVIDIA_API_KEY=...` would not be caught by `SecretGuard` env-var pattern. Fixed: added `NVIDIA` to `(?:GEMINI|GOOGLE|OPENAI|ANTHROPIC|NVIDIA)_API_KEY`

### Changed

- **`PipelineState`** — new field `decision_log: list`
- **`run_pipeline.py` initial state** — seeds `decision_log: []`, `react_stats: {}`, `approval_granted: False`
- **`ExportAgent` console output** — prints `✓ Decisions : {path}  ({n} records)` line
- **`tests/test_graph.py`** — `test_state_has_all_required_keys` updated to include `decision_log`
- **Test count** — 200 → 224 (24 new decision traceability tests)

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
