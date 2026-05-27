# CLAUDE.md — AI Assistant Guide for Telecom Call Intelligence

This file tells Claude Code how to work in this repository. Read it before making changes.

---

## Project Overview

**Telecom Call Intelligence** is a production-grade, multi-agent AI pipeline that:
1. Streams real telecom call transcripts from HuggingFace (`talkmap/telecom-conversation-corpus`)
2. Extracts 70+ structured fields per call using **Gemini 2.5 Flash Lite** (Google AI Studio)
3. Scores extraction quality inline with a 100-point QA model
4. Aggregates KPIs (FCR, AHT, avoidable call rate, AI resolvability)
5. Synthesises strategic recommendations via a second Gemini LLM call (InsightsAgent)
6. Exports CSVs, JSON reports, and an audit trail; serves a Streamlit dashboard

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
                                   ExtractionAgent     (2)  ← Gemini extraction
                                   QualityAgent        (3)  ← 100-pt QA scoring
                                   AggregationAgent    (4)  ← KPI computation
                                   InsightsAgent       (5)  ← Gemini recommendations
                                   ExportAgent         (6)  ← CSV/JSON/audit
```

Key files:
- `pipeline/config.py` — **single source of truth** for all constants
- `pipeline/graph.py` — LangGraph 6-node pipeline with conditional routing
- `pipeline/orchestrator.py` — batch work planning, health monitoring, retry
- `pipeline/governance.py` — BudgetGuard, QualityGate, PIIScanner, AuditLog
- `pipeline/security.py` — InputSanitizer, OutputSanitizer, AgentScopeGuard, SecretGuard, RateLimiter
- `pipeline/token_tracker.py` — Gemini token accounting and cost estimation
- `pipeline/memory.py` — persistent cross-run agent memory (`outputs/agent_memory.json`)
- `pipeline/tools.py` — formal JSON-schema tool registry (5 tools)
- `pipeline/agents/` — one file per agent

---

## Development Commands

```bash
make install-dev    # install all deps (prod + dev)
make test           # run 198-test suite
make test-fast      # skip @slow and @integration tests
make lint           # ruff linter
make check          # lint + type-check + test (full gate)
make run            # 3-call smoke test
make run-batches    # 100-call production run (5×20 batches)
make dashboard      # Streamlit dashboard on localhost:8501
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
- **Never commit `.env`** — it contains `GEMINI_API_KEY`. The `.gitignore` already excludes it.
- **Never print or log API keys**, even truncated.
- **Never push to a public remote** — repo is private.

### Code conventions
- All pipeline constants live in `pipeline/config.py`. Don't add new constants to individual modules.
- Agents are **stateless**: `run(state: dict) -> dict`. No instance state between calls.
- State handoff is **immutable**: always `return {**state, "new_key": new_value}`.
- Tests live in `tests/`. New modules get new test files. Mark tests that make API calls with `@pytest.mark.slow`.
- No AI-generated comments explaining what the code does. Comments explain WHY (a non-obvious constraint, invariant, or workaround).

### Model and API
- Current model: `gemini-2.5-flash-lite` (defined in `pipeline/config.py` as `EXTRACTION_MODEL` and `INSIGHTS_MODEL`)
- `thinking_budget=0` — **must not be removed**. Without it, thinking tokens consume the token budget and JSON output is truncated.
- `max_output_tokens=8192` — sized to fit the 70-field extraction JSON; do not reduce.
- Free tier: `gemini-2.5-flash-lite` = **500 RPD / 15 RPM** (Google AI Studio; last verified 2026-Q2). For larger runs switch to `gemini-2.0-flash-lite` (1 500 RPD / 30 RPM) by updating `EXTRACTION_MODEL` and `INSIGHTS_MODEL` in `pipeline/config.py`. Daily quota resets at midnight Pacific.

### Adding new agents
1. Create `pipeline/agents/your_agent.py` with a stateless class + `run(state: dict) -> dict`
2. Export from `pipeline/agents/__init__.py`
3. Add a singleton in `pipeline/graph.py` and wire the node
4. Add tests in `tests/test_agents/test_your_agent.py`
5. Register any tools in `pipeline/tools.py`
6. Update `PipelineState` TypedDict with any new state keys
7. Update `ARCHITECTURE.md`

---

## What NOT to do

- Don't add a `requirements.txt` entry for `google-generativeai` — it's deprecated. Use `google-genai`.
- Don't import directly from `pipeline.analyzer` for the model name — import from `pipeline.config`.
- Don't hardcode `"outputs"` as a string path — use `pipeline.config.OUTPUT_DIR`.
- Don't skip `thinking_budget=0` in Gemini calls.
- Don't add mock tests for things that should hit the real governance logic — `BudgetGuard`, `QualityGate`, `PIIScanner`, and `AuditLog` are all fast, pure Python and should be tested directly.
- Don't commit `outputs/*.json`, `outputs/*.csv`, or checkpoint files — `.gitignore` excludes them except `summary.json`.

---

## Running Tests

```bash
.venv/bin/python -m pytest tests/ -v          # all 198 tests
.venv/bin/python -m pytest tests/ -m "not slow"  # skip API tests
```

Expected: **198 passed** in < 2 seconds. If a test fails, check whether config.py constants changed or a governance threshold was adjusted.
