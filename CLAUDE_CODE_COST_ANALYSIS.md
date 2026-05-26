# Claude Code — Build Cost & Efficiency Analysis
## Telecom Call Intelligence Platform

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

## 6. What Is Still Required

The following items are out of scope for v3.0 and are planned for v4.0 (Enterprise) or remain on the backlog.

### High priority — blocks production use
| Item | Effort | Value |
|------|--------|-------|
| Switch to `gemini-2.0-flash-lite` for multi-batch runs (1,500 RPD) | Low — change 2 constants in `config.py` | Unblocks 100-call full dataset processing |
| Complete the 100-call run with correct model | Low | Produces real KPI data for dashboard |
| Dashboard screenshot in README.md | Low | Improves repo's first impression for partners/investors |
| Streamlit Cloud deployment | Medium | Makes dashboard accessible without local setup |

### Medium priority — enterprise readiness
| Item | Effort | Value |
|------|--------|-------|
| Real ACD transcript ingestion (S3 / Azure Blob / Snowflake) | High | Moves from synthetic to production data |
| Agent ID and queue name tagging | Medium | Enables agent-level coaching queue |
| CRM callback validation for FCR | High | Replaces LLM-inferred FCR with ground truth |
| Parameterise extraction prompt per carrier | Medium | Improves accuracy for carrier-specific terminology |
| Role-based access control on dashboard | Medium | Required for multi-team enterprise access |

### Lower priority — intelligence improvements
| Item | Effort | Value |
|------|--------|-------|
| Confidence scoring per extracted field | Medium | Surfaces low-confidence extractions for human review |
| Multi-model comparison (Gemini vs Claude vs GPT-4o) | Medium | Validates model selection with data |
| Webhook / event-driven trigger (near-real-time) | High | Enables call-to-insight in < 60 seconds |
| Predictive deflection integration | High | Closes the loop from insight to pre-call intervention |
| Agent coaching queue generation | Medium | Surfaces transcript-evidenced coaching opportunities |
| Integration with Pega / Salesforce / ServiceNow | High | Embeds intelligence in existing workflow tools |

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
