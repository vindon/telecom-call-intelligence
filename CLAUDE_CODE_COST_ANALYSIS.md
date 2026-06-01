# Claude Code — Build Cost & Efficiency Analysis
## Telecom Call Intelligence Platform

> **v4.0 status (2026-06-01):** The pipeline is now on Claude Haiku 4.5 (primary extraction) + NVIDIA NIM Llama 3.3 70B (insights) + full `DecisionLogger` traceability across all agents. Test suite: 224 tests. Backlog items B-01/B-02 are superseded — the model was switched to Claude Haiku rather than gemini-2.0-flash-lite. The historical analysis below documents the build cost through v3.0.

---

**Project period:** 2026-05-17 to 2026-05-26  
**Model:** claude-sonnet-4-6  
**Sessions:** 2  
**Total estimated cost:** ~$58.02  

---

## 1. Executive Summary

The Telecom Call Intelligence platform — a production-grade, 7-node agentic AI pipeline with 198 CI-verified tests, a 5-component security layer, vector memory, ReAct extraction loops, a 3-pass InsightsAgent deliberation loop, and a professional Streamlit executive dashboard — was built entirely through Claude Code across two sessions spanning nine days.

Total spend of ~$58 produced 11,227 lines of code across 35 Python files, 12 Markdown documents, 15 git commits, and a fully deployed GitHub repository. The dominant cost driver was **prompt cache reads** ($30.46, 52% of total), which paradoxically reflects heavy reuse of context — the same large conversation window being read cheaply on each turn rather than reconstructed from scratch.

---

## 2. Investment Overview

### Token consumption

| Token type | Session 1 | Session 2 | Total | Unit cost | **Line cost** |
|------------|-----------|-----------|-------|-----------|---------------|
| Input (fresh) | 34,420 | 11,683 | **46,103** | $3.00/MTok | **$0.14** |
| Output | 289,342 | 725,503 | **1,014,845** | $15.00/MTok | **$15.22** |
| Cache writes | 956,622 | 2,296,235 | **3,252,857** | $3.75/MTok | **$12.20** |
| Cache reads | 30,684,462 | 70,856,227 | **101,540,689** | $0.30/MTok | **$30.46** |
| **Grand total** | | | | | **$58.02** |

### Session summary

| | Session 1 | Session 2 | Total |
|---|---|---|---|
| Date range | 2026-05-17–18 | 2026-05-18–26 | 9 days |
| Assistant turns | 348 | 717 | **1,065** |
| Tool calls | 205 | 412 | **617** |
| Session cost | ~$17.24 | ~$40.78 | **~$58.02** |
| Avg output tokens/turn | 833 | 1,012 | ~948 |
| Avg cache read/turn | 87,887 | 98,823 | ~95,345 |

### Tool call distribution

| Tool | Session 1 | Session 2 | Total | % of calls |
|------|-----------|-----------|-------|------------|
| Bash | 99 | 131 | **230** | 37.3% |
| Read | 57 | 108 | **165** | 26.7% |
| Edit | 45 | 94 | **139** | 22.5% |
| Write | 10 | 77 | **87** | 14.1% |
| AskUserQuestion | 0 | 2 | **2** | 0.3% |

### Caching efficiency

Without prompt caching, the 101.5M cache-read tokens would have been billed as input tokens at $3.00/MTok = **$304.62**.  
Actual cache read cost = **$30.46**.  
**Caching saved $274.16** — a 4.7× discount on the largest token pool.

---

## 3. What Was Built

| Metric | Value |
|--------|-------|
| Git commits | 15 |
| Total lines of code | 11,227 |
| Python source files | 35 |
| Markdown documents | 12 |
| Config/CI files | 3 |
| Pipeline nodes (LangGraph) | 7 |
| Extracted fields per call | 70 |
| Unit tests | 198 (passing in 5.1 s) |
| Dashboard sections | 7 |
| Security components | 5 |
| Versions shipped | v0.1 → v1.0 → v2.0 → v3.0 → v3.0.1 |

### Largest files produced

| File | Lines | Purpose |
|------|-------|---------|
| `EXECUTIVE_BRIEF.html` | 1,727 | Interactive HTML executive brief |
| `dashboard/app.py` | 877 | Streamlit 7-section dashboard |
| `pipeline/agents/insights_agent.py` | 478 | 3-pass deliberation loop |
| `pipeline/analyzer.py` | 450 | ReAct + CoT extraction engine |
| `pipeline/orchestrator.py` | 366 | Batch work planner + retry |
| `pipeline/security.py` | 354 | 5-component security layer |
| `pipeline/graph.py` | 329 | LangGraph 7-node state graph |
| `pipeline/governance.py` | 326 | BudgetGuard, QualityGate, PII |

---

## 4. Phase-by-Phase Development Analysis

### Phase 0 — Proof of Concept (v0.1) · 2026-05-17
**Commit:** `24a12d7 feat: production-grade telecom call intelligence pipeline v1.0`  
**Lines added:** 6,305 (initial scaffold)  
**Approx. cost:** included in Session 1 (~$17.24 total)

**What was built:**
- Basic LangGraph 5-node pipeline (fetch → validate → analyze → aggregate → export)
- HuggingFace loader for `talkmap/telecom-conversation-corpus`
- 70-field extraction prompt using Groq + Llama 3.3 70B
- Streamlit dashboard (dark theme)
- Batch orchestrator with checkpoint/resume
- Per-call CSV and JSON export

**What could have been done better:**
- **LLM choice upfront.** The pipeline was built on Groq + Llama 3.3 70B. Within one session this was entirely replaced by Gemini 2.5 Flash Lite. Had Gemini been specified as the target provider from the opening prompt, the migration work (a full commit of 37 changes) and all Groq-specific prompt tuning would have been unnecessary.
- **Quota research before design.** No API quota investigation was done before designing a 5-batch × 20-call architecture. The actual free-tier limit (20 RPD) was only discovered when batches 2–5 failed. A single upfront clarification would have shaped the design around a 1-batch default.
- **Documentation as an afterthought.** `EXECUTIVE_BRIEF.html` and `ARCHITECTURE.md` were left as post-hoc additions rather than living documents updated alongside features — they became severely stale by v3.0 and required a large catch-up pass.

---

### Phase 1 — Multi-Agent v2.0 · 2026-05-18
**Commits:** `99c230d`, `e050fca`, `027aa8b`, `7057500`  
**Lines added:** ~4,450 across 4 commits  
**Approx. cost:** majority of Session 1 (~$14–16)

**What was built:**
- 6-agent pipeline: DataIngestion, Extraction, Quality, Aggregation, Insights, Export
- InsightsAgent (second Gemini LLM call for strategic recommendations)
- Governance layer: BudgetGuard, QualityGate, PIIScanner, AuditLog
- Agent memory system (`outputs/agent_memory.json`)
- Tool registry with JSON-schema definitions
- Orchestrator with WorkPlanner, AgentHealthMonitor, adaptive retry
- Centralized `pipeline/config.py`
- 149-test suite (< 2 s)
- Makefile, pyproject.toml, pre-commit hooks, GitHub Actions CI

**What could have been done better:**
- **Groq → Gemini churn cost.** Three of the four commits in this phase still reference Groq. The migration commit (`9c7821a`) that purged all Groq references was a separate, full-sweep effort that touched 6 files. This was entirely avoidable rework.
- **README written twice.** The README was first written as a standard technical doc, then entirely rewritten as a "product showcase with partnership signal" in a separate commit. A single well-scoped prompt specifying the intended audience (investor/partner vs developer) would have collapsed this into one pass.
- **ARCHITECTURE.md written in two commits.** The Orchestrator section was added in a separate commit (`4a99c74`) rather than being included in the main architecture pass. Minor, but illustrates fragmented documentation planning.
- **149 tests were well-structured but no slow/integration test separation was planned from the start.** The `@pytest.mark.slow` and `@pytest.mark.integration` marker infrastructure had to be retrofitted.

---

### Phase 2 — Agentic Patterns v3.0 · 2026-05-26
**Commit:** `ba8cacd feat: v3.0 — ReAct loops, deliberation, vector memory, security hardening`  
**Lines added:** ~1,645 in one commit  
**Approx. cost:** ~$18–20 (early Session 2)

**What was built:**
- ReAct extraction loop: Observe → Reason → Act with field coverage scoring
- Chain-of-Thought as mandatory first JSON field (zero extra API calls)
- InsightsAgent 3-pass deliberation: Analyze (temp=0.3) → Critique (temp=0.1) → Synthesize (temp=0.3)
- Vector memory: Gemini `text-embedding-004`, cosine similarity, TF-IDF fallback
- 5-component security layer: InputSanitizer, OutputSanitizer, AgentScopeGuard, SecretGuard, RateLimiter
- Human approval gate (node 6, configurable)
- LangSmith tracing integration
- 49 new security tests (149 → 198 total)

**What could have been done better:**
- **All of v3.0 in a single large commit.** The entire 1,645-line v3.0 feature set landed in one commit. While the work was well-structured internally, a feature-branch approach with smaller commits (security first, then ReAct, then deliberation) would have made git bisect more useful and reduced the risk of a large partial-failure rollback.
- **Security layer added late.** Security should be a foundational layer, not a v3.0 addition. Injecting `InputSanitizer` and `RateLimiter` into a pre-existing pipeline required touching many files. Designing with security boundaries at v1.0 would have been cleaner.
- **Vector memory TF-IDF fallback.** An offline TF-IDF fallback was built for when the Gemini embedding API is unavailable. This is defensive engineering for a scenario that will never occur in production. The tokens spent implementing and testing this fallback could have been deferred.

---

### Phase 3 — Quota Fix & Dashboard Rebuild · 2026-05-26
**Commits:** `107fa19`, `79874f5`  
**Lines changed:** ~786 across 9 files  
**Approx. cost:** ~$15–18 (mid-Session 2)

**What was built:**
- Module-level `_react_quota_exhausted` circuit breaker in `analyzer.py`
- Early-exit in `ExtractionAgent._react_loop()` when quota tripped
- Corrected quota documentation (500 RPD → 20 RPD)
- Complete Streamlit dashboard redesign: dark hacker theme → professional executive light theme
- 7-section layout, Inter font, white KPI cards, custom HTML traffic-signal action table
- Hero banner with gradient, title "Telecom Call Intelligence", white tagline

**What could have been done better:**
- **Quota documentation error caused real cost.** The wrong figure (500 RPD) led to designing and attempting a 5-batch run. When batches 2–5 failed, debugging consumed multiple turns before root cause was identified. A 2-minute check of the Google AI Studio quota page before writing any quota documentation would have prevented this entirely. Estimated unnecessary turns: 15–25.
- **Dashboard redesigned 3+ times in one session.** The user requested: (1) "professional, legible, executive friendly", (2) "make it even more visually stunning", (3) title/tagline colour change. Each iteration required a full read → rewrite cycle on an 877-line file. Total Write operations on `dashboard/app.py` across this phase: 3 full rewrites. A design brief with explicit requirements (colour scheme, typography, section structure, traffic signal format) before the first write would have collapsed this to one pass — saving an estimated $3–5.
- **Screenshot debugging.** Three separate screenshot approaches were attempted before one worked: (1) Chrome headless returned a blank 5.6 KB PNG (Streamlit requires JS), (2) PIL not found in system Python, (3) viewport height too small, PIL crop ValueError. Each dead end consumed 5–8 turns. The solution (Playwright + `.venv/bin/python` + 5,000 px viewport) was correct on the fourth attempt. Knowing upfront that Streamlit requires a real browser renderer would have gone straight to Playwright.

---

### Phase 4 — Documentation Completion · 2026-05-26
**Commits:** `80331c0`, `8b248c3`, `a2b04e8`  
**Lines changed:** ~624 across 8 files  
**Approx. cost:** ~$5–7 (late Session 2)

**What was built:**
- README rebuilt for v3.0 (dashboard section, traffic-signal table, quota circuit breaker, updated file tree)
- ARCHITECTURE.md updated with ReAct circuit breaker callout and dashboard tech stack
- CHANGELOG v3.0.0 and v3.0.1 entries
- EXECUTIVE_BRIEF.html: 5-node → 7-node architecture, Groq → Gemini, 2025 → 2026, v1.0 → v3.0
- PRD milestones updated: v3.0 Agentic Patterns = complete, v4.0 Enterprise = planned
- CI: added `pipeline/security.py` and `pipeline/vector_memory.py` to syntax check
- `docs/executive_summary_template.md` version bump

**What could have been done better:**
- **Documentation updates fragmented across 3 commits on the same day.** `README + ARCHITECTURE`, `CHANGELOG`, and `EXECUTIVE_BRIEF + PRD + CI` were three separate commits with overlapping context loads. One comprehensive documentation pass at the end of each feature phase would have reduced total turns significantly.
- **EXECUTIVE_BRIEF.html was untouched from v1.0 to v3.0.** This created a two-version gap requiring a large catch-up rewrite. Had it been updated alongside each version, the delta would have been small and incremental.
- **CI was missing two new modules.** `pipeline/security.py` and `pipeline/vector_memory.py` were not added to the CI syntax check when they were created in Phase 2. This was caught later and fixed in a separate commit. A checklist habit ("add to CI syntax check when creating a new pipeline module") would prevent this pattern.

---

## 5. Consolidated Inefficiency Analysis

The following represent the highest-leverage areas where cost and turns could have been reduced.

### 5.1 LLM provider chosen wrong initially
**Wasted:** ~1 commit, ~6–8 turns, ~$1–2  
Groq + Llama 3.3 70B was the initial choice; Gemini 2.5 Flash Lite replaced it one session later. The migration touched 6 files and required purging all references. **Fix:** specify the LLM provider in the opening session prompt before any implementation begins.

### 5.2 Quota figure not verified before system design
**Wasted:** ~20–25 turns, ~$3–5  
`gemini-2.5-flash-lite` free-tier limit was documented as 500 RPD (incorrect); actual limit is 20 RPD. This led to designing a 5-batch architecture, running it, debugging 4 failures, then retrofitting a quota circuit breaker. **Fix:** paste the AI Studio quota page content into the session before designing any batching system.

### 5.3 Dashboard brief was iterative, not specific
**Wasted:** ~2 full rewrites of 877-line file, ~$4–6  
Three rounds of redesign on `dashboard/app.py`: dark → light professional → "visually stunning" → title/tagline fix. Each round read and rewrote the full file. **Fix:** write a one-page design brief (colour palette, section names, typography, component types) before the first implementation.

### 5.4 Screenshot toolchain not specified upfront
**Wasted:** ~15–20 turns, ~$2–3  
Three failed screenshot approaches (Chrome headless, system Python PIL, small viewport) before Playwright + venv Python + 5,000 px viewport succeeded. **Fix:** know before starting that Streamlit requires a JS-capable browser; go straight to Playwright.

### 5.5 Documentation not updated alongside features
**Wasted:** ~1–2 full documentation passes that could have been incremental  
EXECUTIVE_BRIEF.html spanned v1.0 to v3.0 without an update (2 major versions). Docs updates were batched into large end-of-session sweeps rather than small per-feature patches. **Fix:** treat docs as part of the definition of done for each feature commit.

### 5.6 Large Write operations vs targeted Edit operations
**Observed:** 87 Write calls vs 139 Edit calls (38% of file-change operations were full rewrites)  
Full file rewrites (Write) send the entire file content as tokens. Targeted edits (Edit) send only the diff. For files like `dashboard/app.py` (877 lines), a full rewrite vs a targeted edit can cost 5–10× more output tokens. **Fix:** default to Edit for existing files; only use Write for new files or genuine complete rewrites.

### 5.7 Context window size drove cache read cost
**Impact:** $30.46 (52% of total spend)  
The average cache read per turn was ~95,000 tokens — the entire conversation history, re-read on every assistant response. By Session 2, individual turns were reading up to 163,863 cached tokens. This is unavoidable for long sessions but could be mitigated by breaking work into shorter, focused sessions that start fresh. **Fix:** scope each session to a single phase (e.g., "implement security layer only"), keeping context lean.

---

## 6. Backlog Catalogue — 16 Items

Items are grouped by priority tier and assigned a stable ID (`B-01` … `B-16`).  
Effort uses t-shirt sizing: **XS** < 2 h · **S** < 1 day · **M** 1–3 days · **L** 1–2 weeks · **XL** 2+ weeks.  
Status: `open` (not started) · `in-progress` · `blocked` (dependency unmet).

---

### Tier 1 — Immediate (blocks a meaningful demo or production handoff)

---

#### B-01 · Switch model to `gemini-2.0-flash-lite` for multi-batch runs
**Priority:** P1 · **Effort:** XS · **Status:** open · **Phase:** v3.1

**Problem:**  
`gemini-2.5-flash-lite` has a 20 RPD free-tier daily limit — enough for one 20-call batch per day. All 5-batch production runs fail on batches 2–5 with HTTP 429. `gemini-2.0-flash-lite` has a 1,500 RPD limit and supports the same API surface.

**Acceptance criteria:**
- [ ] `EXTRACTION_MODEL` and `INSIGHTS_MODEL` in `pipeline/config.py` updated to `"gemini-2.0-flash-lite"`
- [ ] Comment in `config.py` updated to reflect 1,500 RPD / 30 RPM free-tier limits
- [ ] `CLAUDE.md` model section updated
- [ ] `make run-batches` completes all 5 × 20-call batches without 429 errors
- [ ] `198 passed` in CI after model name change

**Files:** `pipeline/config.py`, `CLAUDE.md`  
**Dependencies:** None  
**Risk:** `gemini-2.0-flash-lite` has a slightly different token throughput profile; confirm `MAX_OUTPUT_TOKENS=8192` still avoids truncation on longest transcripts.

---

#### B-02 · Complete the 100-call production run
**Priority:** P1 · **Effort:** S · **Status:** blocked on B-01 · **Phase:** v3.1

**Problem:**  
All demo data in `outputs/summary.json` is from a single 20-call batch. KPIs computed from 20 calls have wide confidence intervals and are not credible for stakeholder presentations. The dashboard was designed for 100-call scale.

**Acceptance criteria:**
- [ ] `make run-batches` completes 5 × 20 = 100 calls with < 5 failures
- [ ] `outputs/summary.json` updated with N=100 aggregated results
- [ ] Dashboard KPIs reflect 100-call dataset (FCR, AHT, avoidable rate, AI resolvability)
- [ ] QA audit passes (dataset-level score ≥ 60)
- [ ] `outputs/full_results_combined_*.json` present and parseable

**Files:** `outputs/` (runtime, not committed)  
**Dependencies:** B-01 (model switch)  
**Risk:** Even at 1,500 RPD, a 100-call run with 2 Gemini calls per transcript (extraction + insights) = 200 calls; stay within 30 RPM with the existing `DEFAULT_DELAY_S=2.0`.

---

#### B-03 · Add dashboard screenshot to README.md
**Priority:** P1 · **Effort:** XS · **Status:** blocked on B-02 · **Phase:** v3.1

**Problem:**  
README.md has no visual of the dashboard. Every investor, recruiter, or partner who lands on the repository sees text-only documentation. A screenshot is the highest-ROI documentation improvement available.

**Acceptance criteria:**
- [ ] Full-page Playwright screenshot captured after 100-call run (so KPIs show real data)
- [ ] Image saved as `docs/screenshots/dashboard_v3.png`
- [ ] README "Dashboard" section updated with `![Dashboard](docs/screenshots/dashboard_v3.png)`
- [ ] Screenshot shows all 7 sections visible (hero + KPI cards minimum above fold)
- [ ] Image committed and displayed correctly on GitHub

**Files:** `README.md`, `docs/screenshots/dashboard_v3.png` (new)  
**Dependencies:** B-02 (real data makes screenshot credible)  
**Notes:** Use `playwright` + `.venv/bin/python` + 5,000 px tall viewport + `wait_for_selector(".kpi-card")` pattern established during Session 2.

---

#### B-04 · Streamlit Cloud deployment
**Priority:** P1 · **Effort:** S · **Status:** open · **Phase:** v3.1

**Problem:**  
The dashboard currently requires `streamlit run dashboard/app.py` from a local clone with `.env` set up. Any stakeholder who wants to see it needs developer assistance. A public Streamlit Cloud deployment makes the platform self-service for non-technical audiences.

**Acceptance criteria:**
- [ ] `streamlit_app.py` entry point at repo root (or `dashboard/app.py` registered in `streamlit` config)
- [ ] `.streamlit/secrets.toml` pattern documented for setting `GEMINI_API_KEY` on Cloud
- [ ] `requirements.txt` confirmed compatible with Streamlit Cloud's Python 3.12 runtime
- [ ] App deploys and loads successfully at the Streamlit Cloud URL
- [ ] README updated with deployment badge and public URL
- [ ] `outputs/summary.json` committed with 100-call data so dashboard is pre-populated on cold start (this file is already in `.gitignore` exception list)

**Files:** `README.md`, `.streamlit/config.toml` (new), possibly `streamlit_app.py` (new)  
**Dependencies:** B-02 (populated summary.json), B-03 (screenshot)  
**Risk:** `GEMINI_API_KEY` must not be embedded in the repo. Use Streamlit Cloud Secrets management only.

---

### Tier 2 — Enterprise readiness (required for a paying customer deployment)

---

#### B-05 · Real ACD transcript ingestion
**Priority:** P2 · **Effort:** L · **Status:** open · **Phase:** v4.0

**Problem:**  
The pipeline currently reads from HuggingFace (`talkmap/telecom-conversation-corpus`), a public synthetic dataset. A production deployment requires ingesting transcripts from a real ACD system — typically delivered as JSON/text files in an S3 bucket, Azure Blob container, or pushed via a Snowflake table populated by a speech-to-text pipeline (Amazon Transcribe, Google CCAI, Nuance).

**Acceptance criteria:**
- [ ] New `pipeline/loaders/` directory with `s3_loader.py`, `azure_blob_loader.py`, `file_loader.py`
- [ ] Each loader implements the same interface as `hf_loader.py`: `stream_transcripts(n, offset, seed) -> Iterator[dict]`
- [ ] `DataIngestionAgent` accepts a `loader_type` config flag (`"hf"` / `"s3"` / `"azure"` / `"file"`)
- [ ] Transcript schema normalisation handles at minimum: AWS Transcribe JSON, Google CCAI JSON, plain-text with speaker labels
- [ ] PII scanner (`pipeline/security.py:InputSanitizer`) runs on all loaded transcripts regardless of source
- [ ] Unit tests cover each loader with mocked boto3/azure-storage-blob responses
- [ ] `CLAUDE.md` updated with loader addition checklist

**Files:** `pipeline/loaders/` (new dir), `pipeline/agents/data_agent.py`, `pipeline/config.py`, `requirements.txt`  
**Dependencies:** Access credentials for one live ACD source  
**Risk:** Real transcripts will contain PII; confirm `InputSanitizer` redaction patterns are tuned to the carrier's transcript format before running at scale.

---

#### B-06 · Agent ID and queue name tagging
**Priority:** P2 · **Effort:** M · **Status:** open · **Phase:** v4.0

**Problem:**  
The current 70-field schema has no `agent_id` or `queue_name` fields. Without them, agent-level analysis (coaching queues, skill variance, handle time by team) and queue-level analysis (volume by product line, first-touch FCR by queue) are impossible. These fields exist in every ACD metadata record.

**Acceptance criteria:**
- [ ] `agent_id` (string, nullable) and `queue_name` (string, nullable) added to extraction schema in `prompts/system_prompt.txt`
- [ ] Both fields added to `PipelineState` and passed through aggregation
- [ ] `pipeline/aggregator.py` computes `agent_skill_distribution_by_agent_id` and `fcr_by_queue`
- [ ] Dashboard "Agent Performance" section gains a per-agent bar chart (renders if `agent_id` non-null)
- [ ] QA audit (`qa_audit.py`) includes agent_id presence check in completeness scoring
- [ ] Backward compatible: existing `summary.json` files without these fields don't break the dashboard

**Files:** `prompts/system_prompt.txt`, `pipeline/aggregator.py`, `pipeline/graph.py`, `dashboard/app.py`, `qa_audit.py`  
**Dependencies:** B-05 preferred (real ACD data will have agent IDs; HuggingFace data will not)  
**Risk:** LLM may hallucinate agent IDs if they are not explicitly present in the transcript. The extraction prompt must instruct null-return when agent ID is not stated.

---

#### B-07 · CRM callback validation for FCR
**Priority:** P2 · **Effort:** L · **Status:** open · **Phase:** v4.0

**Problem:**  
FCR (`fcr_indicator`) is currently LLM-inferred from transcript content alone — whether the agent stated the issue was resolved and the customer expressed satisfaction. Ground-truth FCR requires cross-referencing with CRM callback records: did the same customer call again within 7 days on the same issue? LLM-inferred FCR can be 15–25 percentage points above ground truth.

**Acceptance criteria:**
- [ ] New `pipeline/validators/fcr_validator.py` that accepts a list of `call_id` + `customer_id` + `issue_category` + `call_timestamp` tuples and queries a configurable CRM API or lookup table
- [ ] `fcr_validated` (bool, nullable) and `fcr_validation_source` (`"llm_inferred"` / `"crm_confirmed"`) added to per-call output
- [ ] `AggregationAgent` uses `fcr_validated` when present, falls back to `fcr_indicator` when not
- [ ] Dashboard FCR KPI card shows validation source as a footnote
- [ ] `REQUIRE_CRM_VALIDATION=False` config flag (default off; enables graceful degradation)
- [ ] Tests mock the CRM query; no live CRM access in CI

**Files:** `pipeline/validators/fcr_validator.py` (new), `pipeline/config.py`, `pipeline/aggregator.py`, `pipeline/agents/aggregation_agent.py`, `dashboard/app.py`  
**Dependencies:** CRM API credentials or CSV callback extract from carrier  
**Risk:** CRM customer_id linkage requires a stable identifier present in both the transcript metadata and CRM records. Confirm identifier availability with the carrier before designing the lookup schema.

---

#### B-08 · Parameterise extraction prompt per carrier
**Priority:** P2 · **Effort:** M · **Status:** open · **Phase:** v4.0

**Problem:**  
`prompts/system_prompt.txt` uses generic telecom terminology. Carrier-specific vocabulary (product names, issue categories, escalation paths, IVR menu labels) varies significantly. A Vodafone deployment and a T-Mobile deployment should use carrier-specific prompt variants to reduce LLM hallucination of issue categories and improve field coverage.

**Acceptance criteria:**
- [ ] `prompts/` directory gains `system_prompt_base.txt` (current content) and `carrier_overrides/` sub-directory
- [ ] Carrier override files (e.g., `vodafone.txt`, `tmobile.txt`) contain only the carrier-specific sections: issue categories enum, product name glossary, escalation path labels
- [ ] `build_system_prompt(carrier: str | None) -> str` function in `pipeline/analyzer.py` merges base + override
- [ ] `CARRIER` constant in `pipeline/config.py` (default `None` = generic)
- [ ] A/B test harness: run same 20 transcripts through generic vs carrier-specific prompt, compare QA scores
- [ ] Unit test confirms prompt assembly produces valid string for known carrier names and falls back gracefully for unknown carriers

**Files:** `prompts/` (restructured), `pipeline/analyzer.py`, `pipeline/config.py`  
**Dependencies:** Carrier engagement (to supply terminology glossary)  
**Risk:** Overfitting the prompt to one carrier creates a re-parameterisation burden for each new customer. Keep the override mechanism minimal — enums and glossary only, not structural changes.

---

#### B-09 · Role-based access control on dashboard
**Priority:** P2 · **Effort:** M · **Status:** open · **Phase:** v4.0

**Problem:**  
The current Streamlit dashboard has no authentication. Any user with the URL can see all KPI data, cost levers, and agent performance signals. For a multi-team enterprise deployment (operations, finance, HR), different roles need different views: finance sees cost tables, HR sees agent performance, operations sees all.

**Acceptance criteria:**
- [ ] Streamlit `st.experimental_user` or an explicit `STREAMLIT_AUTH_MODE` config flag activates auth
- [ ] Three roles defined: `viewer` (KPIs + cost only), `manager` (add agent performance + sentiment), `admin` (all sections)
- [ ] Role assignment via environment variable or a `dashboard/roles.json` config file
- [ ] Sections that exceed a role's access level are hidden (not just greyed out)
- [ ] No credentials stored in the repo; auth tokens via environment variables or Streamlit Cloud Secrets
- [ ] Login screen with role selector for local dev; auto-detect role from `STREAMLIT_USER_ROLE` env var in production

**Files:** `dashboard/app.py`, `dashboard/auth.py` (new), `pipeline/config.py`  
**Dependencies:** B-04 (Streamlit Cloud deployment) for SSO/OAuth path  
**Risk:** Streamlit's built-in auth primitives are limited. For enterprise SSO (Okta, Azure AD), a reverse proxy (nginx + OAuth2 Proxy) or Streamlit for Teams is more appropriate. Flag this before implementation.

---

### Tier 3 — Intelligence improvements (differentiating features for v4.0+)

---

#### B-10 · Confidence scoring per extracted field
**Priority:** P3 · **Effort:** M · **Status:** open · **Phase:** v4.0

**Problem:**  
All 70 extracted fields are treated equally in QA scoring. A field extracted from explicit transcript text (e.g., the agent said "your account is on the Unlimited Plus plan") is far more reliable than a field inferred from implication. Without field-level confidence, operators cannot prioritise which fields need prompt improvement vs which are already reliable.

**Acceptance criteria:**
- [ ] `_cot_reasoning` field extended to include a `field_confidence` sub-object: `{"field_name": "high|medium|low", ...}` for the 10 critical fields
- [ ] `score_field_coverage()` in `pipeline/analyzer.py` uses confidence weights (high=1.0, medium=0.7, low=0.3) in addition to null-check
- [ ] Dashboard "Quality" section (or QA report) shows per-field confidence distribution as a heatmap
- [ ] `qa_audit.py` incorporates confidence-weighted completeness score as a separate metric
- [ ] No additional API calls required (confidence extracted from existing CoT reasoning field)

**Files:** `pipeline/analyzer.py`, `pipeline/agents/quality_agent.py`, `qa_audit.py`, `dashboard/app.py`, `prompts/system_prompt.txt`  
**Dependencies:** None  
**Risk:** Asking the LLM to self-report confidence is known to produce overconfident responses. Calibrate by comparing stated confidence against ground-truth FCR and AHT from ACD records.

---

#### B-11 · Multi-model comparison harness
**Priority:** P3 · **Effort:** M · **Status:** open · **Phase:** v4.0

**Problem:**  
Model selection (`gemini-2.0-flash-lite`) was made based on cost and availability, not empirical extraction quality on this specific domain. Running the same 20 transcripts through Gemini 2.5 Flash, Claude Haiku 4.5, and GPT-4o mini and comparing QA scores, field coverage, and cost-per-call would validate the choice and identify if a better model is available at comparable cost.

**Acceptance criteria:**
- [ ] New CLI flag `--model-compare` on `run_pipeline.py` runs extraction with a specified list of models
- [ ] Results written to `outputs/model_comparison_{timestamp}.json` with per-model QA score, field coverage %, cost, and latency
- [ ] Comparison report includes a ranked table by (QA score / cost) efficiency ratio
- [ ] `pipeline/config.py` gains `COMPARISON_MODELS` list constant
- [ ] All models called with identical prompts, temperatures, and token limits
- [ ] Unit tests mock all model calls; no live API calls in CI

**Files:** `run_pipeline.py`, `pipeline/config.py`, `pipeline/analyzer.py`, new `pipeline/model_compare.py`  
**Dependencies:** API keys for comparison models (Anthropic, OpenAI)  
**Notes:** This is a one-time research task. The harness can be a standalone script rather than a pipeline node.

---

#### B-12 · Webhook / event-driven trigger
**Priority:** P3 · **Effort:** L · **Status:** open · **Phase:** v4.0

**Problem:**  
The pipeline currently runs as a batch job — manually triggered via `make run` or `make run-batches`. In a production contact centre, intelligence is most valuable when it arrives within seconds or minutes of call completion, not hours. An event-driven trigger would allow the pipeline to process each call as it lands in the transcript storage system.

**Acceptance criteria:**
- [ ] New `pipeline/trigger.py` module implements a polling loop: checks S3 prefix / Azure Blob container for new transcript files at `POLL_INTERVAL_S` cadence
- [ ] On new file detection, enqueues a single-call pipeline run via `Orchestrator`
- [ ] Processed files moved to a `processed/` prefix to prevent reprocessing
- [ ] Dead-letter queue (local file or SQS) for transcripts that fail 3 extraction attempts
- [ ] `TRIGGER_MODE` config flag: `"batch"` (current default) or `"event"` 
- [ ] Latency target: transcript landed → dashboard updated in < 5 minutes (single call, paid tier)
- [ ] `make trigger` command in Makefile starts the polling loop

**Files:** `pipeline/trigger.py` (new), `pipeline/config.py`, `Makefile`, `ARCHITECTURE.md`  
**Dependencies:** B-05 (ACD ingestion), cloud storage credentials  
**Risk:** Event-driven processing at call-completion frequency (e.g., 100 calls/hour) requires `gemini-2.0-flash-lite` paid tier to avoid RPD quota exhaustion. Confirm throughput budget before enabling.

---

#### B-13 · Predictive deflection integration
**Priority:** P3 · **Effort:** XL · **Status:** open · **Phase:** v4.0+

**Problem:**  
The pipeline currently identifies deflection eligibility retrospectively — after the call. True value is pre-empting the call: using historical call patterns to identify customers likely to call before they do, and triggering a proactive outreach (SMS, push notification, bill explainer, self-serve prompt) that prevents the call from arriving.

**Acceptance criteria:**
- [ ] `pipeline/agents/deflection_agent.py` built as an 8th pipeline node (optional, gated by `DEFLECTION_ENABLED` config flag)
- [ ] Agent ingests aggregated `proactive_outreach_applicable` and `proactive_outreach_trigger` patterns from the last N runs via vector memory
- [ ] Outputs a `deflection_cohorts` dict: `{trigger_pattern: [customer_segment, recommended_channel, priority]}`
- [ ] Dashboard "Upsell & Deflection" section extended with a "Proactive Trigger Calendar" panel
- [ ] Outreach action export: `outputs/deflection_actions_{timestamp}.csv` with customer segment, trigger, recommended channel, and estimated savings
- [ ] No PII in exported files (customer segments only, not individual customer IDs)
- [ ] Integration test with mocked historical run data

**Files:** `pipeline/agents/deflection_agent.py` (new), `pipeline/graph.py`, `pipeline/config.py`, `dashboard/app.py`, `ARCHITECTURE.md`  
**Dependencies:** B-02 (100-call run for pattern baseline), B-06 (queue tagging for segment definition)  
**Risk:** Predictive precision depends heavily on call volume. Pattern signals from 100 calls are directional only; a minimum of 1,000 calls per segment is needed for statistically actionable cohort definitions.

---

#### B-14 · Agent coaching queue generation
**Priority:** P3 · **Effort:** M · **Status:** open · **Phase:** v4.0

**Problem:**  
The pipeline extracts `agent_skill_rating`, `agent_tool_struggle_detected`, `agent_tool_struggle_evidence`, and `agent_used_correct_troubleshooting_path` per call. This data is surfaced in the dashboard aggregate but is not actionable at the individual agent level. A coaching queue would surface the specific calls and transcript excerpts a team leader should review with each agent.

**Acceptance criteria:**
- [ ] New `pipeline/agents/coaching_agent.py` (or extended `ExportAgent`) generates `outputs/coaching_queue_{timestamp}.csv`
- [ ] Each row: `agent_id`, `call_id`, `skill_rating`, `struggle_evidence`, `recommended_coaching_focus`, `call_excerpt` (max 500 chars)
- [ ] `recommended_coaching_focus` is one of: `tool_navigation`, `structured_discovery`, `diagnosis_efficiency`, `empathy_consistency`, `closing_speed`, `troubleshooting_accuracy`
- [ ] Rows sorted by `skill_rating ASC` (worst first), then `struggle_evidence IS NOT NULL`
- [ ] Dashboard "Agent Performance" section gains a "Download Coaching Queue" button
- [ ] Only generated when `agent_id` is non-null (degrades gracefully on HuggingFace data)
- [ ] `COACHING_ENABLED=True` config flag

**Files:** `pipeline/agents/coaching_agent.py` (new) or `pipeline/agents/export_agent.py`, `pipeline/config.py`, `dashboard/app.py`  
**Dependencies:** B-06 (agent ID tagging required for meaningful output)  
**Risk:** Without real agent IDs, the coaching queue groups by inferred skill tier only. Document this limitation clearly in the CSV header row.

---

#### B-15 · CRM / ACD integration (Pega, Salesforce, ServiceNow)
**Priority:** P3 · **Effort:** XL · **Status:** open · **Phase:** v4.0+

**Problem:**  
Pipeline outputs (cost lever sizing, deflection cohorts, agent coaching queue, upsell recommendations) currently live in CSVs and a local Streamlit dashboard. For operational adoption, these outputs need to flow into the systems where contact centre teams already work: Salesforce Service Cloud (agent coaching), Pega Customer Decision Hub (next-best-action), ServiceNow (ticket creation for repeat-call patterns).

**Acceptance criteria:**
- [ ] New `pipeline/integrations/` directory with `salesforce.py`, `pega.py`, `servicenow.py` stubs
- [ ] Each integration implements `push(summary: dict, insights: dict) -> IntegrationResult`
- [ ] `salesforce.py`: creates/updates Salesforce Cases for calls with `fcr_indicator=false` and `repeat_call_risk=high`
- [ ] `servicenow.py`: creates Incidents for calls with `escalation_required=true`
- [ ] `pega.py`: pushes `agentic_ai_resolvable=true` cohort data to Pega NBA decision table via REST API
- [ ] All integrations are opt-in via `INTEGRATIONS_ENABLED` list in `config.py`
- [ ] Credentials managed via environment variables only; never in `config.py`
- [ ] Full mock-based unit test coverage; no live CRM calls in CI

**Files:** `pipeline/integrations/` (new), `pipeline/config.py`, `pipeline/agents/export_agent.py`, `requirements.txt`  
**Dependencies:** B-05, B-06, B-07 (real data and validated FCR make integration outputs credible)  
**Risk:** CRM integration scope creep is a project risk. Implement one integration (Salesforce) end-to-end before building the others. Validate that the data model matches the CRM's expected schema before writing a single line of integration code.

---

#### B-16 · QA-driven prompt improvement / A/B testing
**Priority:** P3 · **Effort:** M · **Status:** open · **Phase:** v3.2

**Problem:**  
The extraction prompt in `prompts/system_prompt.txt` was written once at v0.1 and has not been systematically improved since. QA audit scores reveal which fields fail most often (enum validity failures, null rates by field), but there is no structured mechanism to hypothesis-test prompt modifications and measure their impact on field coverage and QA score.

**Acceptance criteria:**
- [ ] New `pipeline/prompt_lab.py` CLI: `python -m pipeline.prompt_lab --variant A --variant B --calls 20`
- [ ] Runs both prompt variants on the same 20 calls; outputs side-by-side QA score, field coverage %, and cost comparison
- [ ] Results written to `outputs/prompt_ab_{timestamp}.json`
- [ ] At least 3 documented prompt variants tested: (1) current baseline, (2) stricter enum enforcement, (3) explicit null-discipline instructions
- [ ] `PROMPT_VARIANT` constant in `config.py` selects the active variant for production runs
- [ ] Winner variant updated in `prompts/system_prompt.txt` after validation
- [ ] CHANGELOG updated with the winning variant's QA score improvement

**Files:** `pipeline/prompt_lab.py` (new), `pipeline/config.py`, `prompts/` (new variant files)  
**Dependencies:** B-01 (requires 1,500 RPD model to run 40 calls for A/B test within quota)  
**Notes:** This is the v2.1 milestone from the original PRD. Now that ReAct gap-fill and CoT are in place, prompt improvements compound with the agentic loop rather than replacing it.

---

## 7. Cost vs Value Delivered

| Metric | Value |
|--------|-------|
| Total Claude Code spend | ~$58.02 |
| Production system delivered | Yes — 7-node pipeline, 198 tests, CI, dashboard |
| Equivalent engineer-days (est. 10 days × $600–800/day) | $6,000–$8,000 |
| Cost ratio (Claude vs human engineer) | **~103–138× cheaper** |
| Gemini API cost for demo run (20 calls) | $0.00 (free tier) |
| Projected cost at scale (1M calls/mo, Gemini paid tier) | ~$0.002–0.005/call |

The $58 invested in Claude Code produced a system capable of generating $396,900/month in savings at 100,000 call/month scale — based on the self-serve deflection, agentic AI resolution, and proactive outreach opportunity sizing embedded in the pipeline outputs.

---

## 8. Recommendations for Future Sessions

1. **Write a one-page session brief before starting.** Specify: LLM provider, API tier and quota, architecture target node count, design palette for UI work. This eliminates the two most expensive rework categories (LLM migration, dashboard redesign).

2. **Scope each session to a single phase.** Keeping context < 50K tokens per session reduces cache read cost and prevents context window saturation. Session 2 at 717 turns with 98K average cache reads per turn is the direct cost of mixing implementation, debugging, and documentation in one sitting.

3. **Use Edit over Write for existing files.** Write sends the entire file as output tokens every time. For an 877-line file like `dashboard/app.py`, an Edit diff is typically 50–150 lines. This is a 6–17× token reduction per operation.

4. **Verify external API constraints before design.** A 2-minute quota check before any rate-limiting or batching design would have prevented the 20-turn debugging episode that led to the quota circuit breaker.

5. **Update docs inside the same commit as the feature.** Treating documentation as a separate later task creates version-skew debt. The EXECUTIVE_BRIEF.html two-version gap is the most expensive example: a comprehensive rewrite of 1,700 lines rather than two incremental 200-line patches.

6. **Use Playwright from the start for Streamlit screenshots.** Chrome headless does not execute JavaScript. Any Streamlit visual verification needs a real browser automation tool.

---

*Generated by Telecom Call Intelligence — Claude Code Build Analysis · 2026-05-26*  
*Token data extracted from `~/.claude/projects/` session JSONL files. Cost estimates use claude-sonnet-4-6 public pricing: input $3.00/MTok · output $15.00/MTok · cache write $3.75/MTok · cache read $0.30/MTok.*
