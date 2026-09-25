# CLAUDE.md — AI Assistant Guide for Telecom Call Intelligence

This file tells Claude Code how to work in this repository. Read it before making changes.

---

## Project Overview

**Telecom Call Intelligence** is a production-grade, multi-agent AI pipeline that:
1. Streams real telecom call transcripts from HuggingFace (`talkmap/telecom-conversation-corpus`)
2. Extracts 70+ structured fields per call using **Claude Haiku 4.5** (Anthropic)
3. Scores extraction quality inline with a 100-point QA model
4. Aggregates KPIs (FCR, AHT, avoidable call rate, AI resolvability)
5. Synthesises strategic recommendations via **NVIDIA NIM** (Llama 3.3 70B) with Claude fallback
6. Exports CSVs, JSON reports, decision trace, and an audit trail; serves a Streamlit dashboard

**License:** Proprietary — Copyright © 2026 Vinoth N. All rights reserved.
**Repo:** Private GitHub repository. Do not share code, outputs, or API keys externally.

---

## Architecture

```
run_batches.py → Orchestrator → 5× subprocess → run_pipeline.py
                                                       │
                                              LangGraph StateGraph
                                                       │
                                   DataIngestionAgent  (1)
                                   ExtractionAgent     (2)  ← Claude Haiku extraction
                                   QualityAgent        (3)  ← 100-pt QA scoring
                                   AggregationAgent    (4)  ← KPI computation
                                   InsightsAgent       (5)  ← NVIDIA NIM / Claude recommendations
                                   ExportAgent         (6)  ← CSV/JSON/decisions/audit
```

Key files:
- `pipeline/config.py` — **single source of truth** for all constants (models, budget, thresholds)
- `pipeline/graph.py` — LangGraph 7-node pipeline with conditional routing and approval gate
- `pipeline/decision_log.py` — `DecisionRecord`, `DecisionLogger`, `summarize_decisions()` — pattern + full decision-type list: `docs/decision-logging.md`
- `pipeline/orchestrator.py` — batch work planning, health monitoring, strict halt-on-failure policy (see below)
- `pipeline/governance.py` — BudgetGuard (reads `BUDGET_USD`), QualityGate, PIIScanner, AuditLog
- `pipeline/security.py` — InputSanitizer, OutputSanitizer, AgentScopeGuard, SecretGuard, RateLimiter
- `pipeline/token_tracker.py` — model-aware token accounting; `cost_usd(prompt, completion)` dispatches by `EXTRACTION_MODEL`
- `pipeline/memory.py` — persistent cross-run agent memory (`outputs/agent_memory.json`)
- `pipeline/vector_memory.py` — semantic cross-run memory (embeds each run's KPI profile; written by ExportAgent, queried by InsightsAgent)
- `pipeline/llm_clients.py` — single seam for constructing Anthropic/Gemini/NVIDIA clients (timeout/max_retries policy lives here, not at each call site)
- `pipeline/tracing.py` — Langfuse LLM observability (opt-in via `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`); one trace per `call_id` for extraction+gap-fill, one per run for insights; redacts raw transcript content before export
- `pipeline/circuit_breaker.py` — shared provider-unavailability breaker (Gemini quota exhaustion, NVIDIA timeout)
- `pipeline/drift.py` — `DriftGuard`, cross-run KPI drift detection against `AgentMemory`'s history; wired into `ExportAgent`, detection/reporting only
- `pipeline/agents/` — one file per agent

---

## Development Commands

```bash
make install-dev    # install all deps (prod + dev)
make test           # run 503-test suite
make test-fast      # skip @slow and @integration tests
make lint           # ruff linter
make check          # lint + type-check + test (full gate)
make run            # 3-call smoke test
make run-batches    # 100-call production run (5×20 batches)
make dashboard      # Streamlit dashboard on localhost:8501
make eval-golden    # golden-set extraction-accuracy eval (~$0.11, real API calls — never run without confirming cost first)
```

> **Screenshotting the dashboard:** headless Chrome `--screenshot` captures before React hydrates → blank frame. Use Playwright instead:
> ```bash
> .venv/bin/python -c "
> from playwright.sync_api import sync_playwright
> with sync_playwright() as p:
>     b = p.chromium.launch(); pg = b.new_page(viewport={'width':1400,'height':900})
>     pg.goto('http://localhost:8501/', wait_until='networkidle'); pg.wait_for_timeout(3000)
>     pg.screenshot(path='/tmp/dashboard.png'); b.close()"
> ```

### Claude Code hooks (auto-active)
- **Pre-write guard**: blocks any Edit/Write to `.env` or `outputs/*.json|csv`
- **Post-write formatter**: runs `ruff format` + `ruff check --fix` on every `.py` save

---

## Critical Rules

### Security — never violate these
- **Never commit `.env`** — it contains `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `NVIDIA_API_KEY`. The `.gitignore` already excludes it.
- **Never print or log API keys**, even truncated.
- **Never push to a public remote** — repo is private.

### Code conventions
- All pipeline constants live in `pipeline/config.py`. Don't add new constants to individual modules.
- Agents are **stateless**: `run(state: dict) -> dict`. No persistent instance state between calls.
- State handoff is **immutable**: always `return {**state, "new_key": new_value}`.
- Every agent **must** use `DecisionLogger` and return `"decision_log": dl.finalize()` — see `docs/decision-logging.md`. This is the traceability contract.
- Tests live in `tests/`. New modules get new test files. Mark tests that make API calls with `@pytest.mark.slow`.
- No AI-generated comments explaining what the code does. Comments explain WHY (a non-obvious constraint, invariant, or workaround).

### Model and API
- **Primary extraction model**: `claude-haiku-4-5-20251001` — set as `EXTRACTION_MODEL` in `pipeline/config.py`
- **Primary insights model**: `meta/llama-3.3-70b-instruct` via NVIDIA NIM (OpenAI-compatible endpoint) — set as `INSIGHTS_MODEL`
- **Fallback chain**: NVIDIA NIM → Claude Haiku → rule-based (InsightsAgent auto-selects based on key availability)
- `EXTRACTION_MODEL` is the single switch that controls which client, rate limiter, pricing, and key validation fire. Change only in `config.py`.
- Claude: 50 RPM rate limit (`CLAUDE_RATE_LIMITER`). Gemini: 15 RPM (`GEMINI_RATE_LIMITER`).
- `thinking_budget=0` on Gemini calls — **must not be removed**. Without it, thinking tokens truncate JSON output.
- `max_output_tokens=8192` — sized to fit the 70-field extraction JSON; do not reduce.

### Data quality gate — QA Score vs Data Quality Gate (never conflate)
Two named, independent checks: **QA Score** (0-100) grades whether the extraction is well-formed; **Data Quality Gate** (pass/fail) grades whether a call's *time data* can be trusted for cost-lever attribution — a call can score 100/100 on the first and still fail the second. Full mechanism, the phase-reconciliation bug story, and why they must never be blended: `docs/qa-data-quality-gate.md`. Read it before touching `qa_audit.py` or `aggregator.py`.

### Strict failure policy — human intervention required, no auto-retry
`Orchestrator.run()` halts the **entire** multi-batch run on the first task failure — no retry, no proceeding to the next batch. A halt writes `outputs/.halted_for_human_review.json` (gitignored), blocking every subsequent `run_batches.py` invocation until a human clears it with `--acknowledge-halt`. This replaced an auto-retry loop that, in production on 2026-08-09, silently retried a hung batch twice before a human noticed the wasted spend (~$1.8). No config flag re-enables auto-retry — don't add one without discussing it first. Every LLM client construction (`anthropic.Anthropic`, `OpenAI`, `genai.Client`) must set an explicit `timeout=` (`EXTRACTION_API_TIMEOUT_S`/`INSIGHTS_API_TIMEOUT_S` in config.py) and `max_retries=1`.

### Adding new agents
Use the `new-agent` skill (`.claude/skills/new-agent`) — it scaffolds the file, wires `graph.py`, adds a test, and reminds about `ARCHITECTURE.md`.

---

## What NOT to do

- Don't add a `requirements.txt` entry for `google-generativeai` — it's deprecated. Use `google-genai`.
- Don't import model names from `pipeline.analyzer` — import from `pipeline.config`.
- Don't hardcode `"outputs"` as a string path — use `pipeline.config.OUTPUT_DIR`.
- Don't skip `thinking_budget=0` in Gemini calls.
- Don't add mock tests for things that should hit the real governance logic — `BudgetGuard`, `QualityGate`, `PIIScanner`, and `AuditLog` are all fast, pure Python and must be tested directly.
- Don't commit `outputs/*.json`, `outputs/*.csv`, or checkpoint files — `.gitignore` excludes them except `summary.json`.
- Don't hardcode cost rates in agent code — use `token_tracker.cost_usd(prompt_tokens, completion_tokens)`.
- Don't store transcript text or customer PII in `evidence` dicts in `DecisionLogger`.
- Don't write agent code that reads `GEMINI_API_KEY` when `EXTRACTION_MODEL` starts with `claude` — the startup validator enforces model-aware key checks.

---

## Running Tests

```bash
.venv/bin/python -m pytest tests/ -v              # all 503 tests
.venv/bin/python -m pytest tests/ -m "not slow"   # skip API tests
```

Expected: **503 passed** in < 7 seconds. If a test fails, check whether `config.py` constants changed or a governance threshold was adjusted.

---

## Proactive Standards — How Claude Must Operate in This Repo

This is Vinoth's primary portfolio piece for landing work — every session must meet an investor/hiring-manager standard. Full rationale and the narrative-consistency incident: `docs/portfolio-standards.md`.

**Before ending any session:**
1. `git status` + `git log --oneline -5` — flag unpushed commits and ask to push
2. Scan for docstring/comment/banner inconsistencies (agent count, model names, version strings)
3. Check any new `config.py` constants are actually imported and used
4. `make test` — verify still passing

**Reading code that spans multiple modules:** trace cross-module invariants two layers deep — e.g. a budget guard must be verified across subprocess boundaries, not just within one module. Rate limiters, budget guards, circuit breakers all need inter-process verification. Full explanation: `docs/portfolio-standards.md`.

**On "what am I missing?" / "is anything wrong?":** this is a deep audit request. Read `config.py`, `orchestrator.py`, `governance.py`, and the relevant agent(s) before answering. Check: budget/rate cross-process safety, state mutation leaking across agents, PII in decision logs, stale docstrings, agent count mismatches in banners.

**Portfolio standard:** agent-count/model-name/version mentions must stay consistent with `config.py`; GitHub must stay in sync with local `main`; nothing half-finished goes into `main`; README/ARCHITECTURE.md/CHANGELOG.md reflect current state after any significant change. Single source of truth for economics/success-metrics narrative: `docs/executive_deck.html` — never write a number into a doc without tracing it to `outputs/summary.json` or a fresh computation. Full incident: `docs/portfolio-standards.md`.
