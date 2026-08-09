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
- `pipeline/decision_log.py` — `DecisionRecord`, `DecisionLogger`, `summarize_decisions()`
- `pipeline/orchestrator.py` — batch work planning, health monitoring, retry
- `pipeline/governance.py` — BudgetGuard (reads `BUDGET_USD`), QualityGate, PIIScanner, AuditLog
- `pipeline/security.py` — InputSanitizer, OutputSanitizer, AgentScopeGuard, SecretGuard, RateLimiter
- `pipeline/token_tracker.py` — model-aware token accounting; `cost_usd(prompt, completion)` dispatches by `EXTRACTION_MODEL`
- `pipeline/memory.py` — persistent cross-run agent memory (`outputs/agent_memory.json`)
- `pipeline/tools.py` — formal JSON-schema tool registry (5 tools)
- `pipeline/agents/` — one file per agent

---

## Development Commands

```bash
make install-dev    # install all deps (prod + dev)
make test           # run 364-test suite
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
- **Never commit `.env`** — it contains `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `NVIDIA_API_KEY`. The `.gitignore` already excludes it.
- **Never print or log API keys**, even truncated.
- **Never push to a public remote** — repo is private.

### Code conventions
- All pipeline constants live in `pipeline/config.py`. Don't add new constants to individual modules.
- Agents are **stateless**: `run(state: dict) -> dict`. No persistent instance state between calls.
- State handoff is **immutable**: always `return {**state, "new_key": new_value}`.
- Every agent **must** use `DecisionLogger` and return `"decision_log": dl.finalize()`. This is the traceability contract.
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

### Decision traceability — required for every agent
Every agent must instrument decisions with `DecisionLogger`:

```python
from pipeline.decision_log import DecisionLogger

def run(self, state: dict) -> dict:
    dl = DecisionLogger(self.name, state)
    dl.log(
        decision_type="my_decision_type",
        decision="what was decided",
        reason="why — max 500 chars",
        evidence={"score": 87, "threshold": 60},   # no PII, no transcript text
        call_id="optional",
        confidence=0.9,
        alternatives=["option_b"],
    )
    return {**state, "decision_log": dl.finalize()}
```

Named decision types: `transcript_skip`, `pii_redaction`, `react_trigger`, `react_gap_fill_outcome`, `qa_exclusion`, `qa_grade_assignment`, `quality_gate_outcome`, `aggregation_scope`, `cost_model_applied`, `provider_selected`, `deliberation_outcome`, `routing_decision`, `approval_decision`, `export_scope`, `data_quality_gate_outcome`, `phase_reconciliation_failure`, `timestamp_ground_truth_mismatch`, `transcript_truncation_detected`.

### Data quality gate — AHT/timestamp integrity (separate from the 100-pt QA score)

Phase-level AHT breakdowns and `total_duration_seconds` are LLM-inferred from transcript text, not measured. `QualityAgent` runs three deterministic (non-LLM) checks per call via `qa_audit.check_data_quality()`, in addition to the 100-pt score:

- **Phase reconciliation** — sum of all `phase_*_duration_seconds` fields must not exceed `total_duration_seconds` beyond `PHASE_RECONCILIATION_TOLERANCE_S`/`_PCT` (config.py). Regression-tested in `tests/test_qa_audit_phase_reconciliation.py`.
- **Timestamp ground truth** — `total_duration_seconds` is cross-checked against `_raw_duration_seconds` (the actual first-to-last-turn span from the source dataset's own timestamps, threaded through `hf_loader.py` → `data_agent.py` → `extraction_agent.py`), within `TIMESTAMP_GROUND_TRUTH_TOLERANCE_S`/`_PCT`.
- **Transcript completeness** — the LLM-graded `transcript_truncated`/`truncation_reason` schema fields (prompts/system_prompt.txt), corroborated by a cheap heuristic (`data_agent.py::_looks_truncated`) that is evidence-only and never gates alone.

Records failing any check get `_dq_gate_passed=False` and are excluded from aggregation alongside LOW-grade QA records — this is a data-integrity fact, not a quality nuance, so it is **not** blended into the 100-pt score. The dataset-level `data_quality_pass_rate_pct` rolls into `qa_report["summary"]` and, when it drops below `QUALITY_WARN_RATE`, `ExportAgent` writes a computed `aht_disclaimer` string into `summary.json` that the dashboard renders as a banner (`.data-disclaimer` in `dashboard/app.py`) — a run-specific caveat in the actual report, not just static doc text.

**Disclaimer, stated plainly:** this system's AHT and phase-level cost economics are only as accurate as the completeness of the input transcript and the fidelity of its timestamps. Don't drive staffing or cost decisions from a run where `data_quality_pass_rate_pct` is low without reviewing the flagged calls first.

### Adding new agents
1. Create `pipeline/agents/your_agent.py` with a stateless class + `run(state: dict) -> dict`
2. Instrument with `DecisionLogger` (see above) — not optional
3. Export from `pipeline/agents/__init__.py`
4. Add a singleton in `pipeline/graph.py` and wire the node
5. Add tests in `tests/test_agents/test_your_agent.py`
6. Register any tools in `pipeline/tools.py`
7. Update `PipelineState` TypedDict with any new state keys
8. Update `ARCHITECTURE.md` and `CHANGELOG.md`

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
.venv/bin/python -m pytest tests/ -v              # all 364 tests
.venv/bin/python -m pytest tests/ -m "not slow"   # skip API tests
```

Expected: **364 passed** in < 7 seconds. If a test fails, check whether `config.py` constants changed or a governance threshold was adjusted.

---

## Proactive Standards — How Claude Must Operate in This Repo

This project is Vinoth's primary portfolio piece for landing work. Every session must meet the standard an investor or senior hiring manager would apply. Reactive assistance is not acceptable.

### Mandatory proactive checks — do these without being asked

**Before ending any session:**
1. Run `git status` and `git log --oneline -5` — if commits exist that haven't been pushed, flag it and ask to push
2. Scan for docstring/comment/banner inconsistencies introduced by new code (agent count, model names, version strings)
3. Check that any new constants in `config.py` are actually imported and used — dead config is a red flag
4. Verify tests still pass after any edit: `make test`

**When reading code that spans multiple modules:**
- Always trace cross-module invariants. If `governance.py` defines a budget guard and `orchestrator.py` spawns subprocesses, ask: *does the guard actually enforce across process boundaries?*
- If a flag or sentinel is module-level in Python, assume it resets per subprocess unless proven otherwise
- Rate limiters, budget guards, circuit breakers — all require inter-process verification

**When asked "what am I missing?" or "is anything wrong?":**
- This is a deep audit request, not a surface check. Read the critical path files and trace actual failure modes
- Do not answer until you have read at least: `config.py`, `orchestrator.py`, `governance.py`, and the primary agent(s) under discussion
- Failure modes to always check: budget/rate cross-process safety, state mutation leaking across agents, PII in decision logs, stale docstrings, agent count mismatches in banners

### Portfolio standard — enforce this on every change
- Every file that mentions an agent count, model name, or version must be consistent with `config.py` and the current architecture
- GitHub must always be in sync with local `main` — check at session start
- Nothing half-finished goes into `main`. If a fix touches a bug, check for its siblings
- The README, ARCHITECTURE.md, and CHANGELOG.md must reflect the current state after any significant change

### What "two layers deep" means in practice
When you see `BUDGET_GUARD.check(cost)` in an agent, the first layer is "does this guard work?" The second layer is "does this guard work when the caller is a subprocess spawned by `run_batches.py`?" Always ask the second-layer question before declaring something correct.
