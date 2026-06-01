# Product Requirements Document

**Product:** Telecom Call Intelligence Platform
**Version:** 4.0
**Status:** Production
**Last updated:** 2026-06-01

---

## 1. Executive Summary

Contact centres are the highest-cost customer touchpoint in telecom. At $6.00 per interaction and millions of calls per month, even a 10% reduction in handle time or avoidable call volume translates to millions in annual savings — yet most operators analyse fewer than 5% of calls manually.

This platform applies a 7-agent LangGraph pipeline to 100% of call transcripts, extracting 70+ structured metadata fields per call using Claude Haiku 4.5, scoring extraction quality inline, generating strategic recommendations via NVIDIA NIM (Llama 3.3 70B) with Claude fallback, and delivering executive-ready KPIs via an analytics dashboard. A full decision trace (`decisions_{ts}.json`) records every material agent decision for governance and auditability.

---

## 2. Problem Statement

### Current state
- QA teams manually review 2–5% of calls, introducing selection bias and scale limits
- Handle time inefficiencies are discovered reactively, not proactively
- Avoidable calls (billing questions answerable via app, known outages) are not systematically tracked
- Agent coaching is based on anecdotal observation rather than data patterns
- Executive reporting relies on ACD metadata (call volume, handle time) — not call *content*

### Impact
- Unidentified self-serve deflection opportunities cost ~$510K/mo per 100K calls (est.)
- Undetected escalation patterns increase cost-per-resolution
- Missed proactive outreach opportunities create reactive, avoidable call volume
- Without FCR measurement, repeat call rate cannot be actively managed

---

## 3. Goals

### Primary goals
1. **Cost visibility** — Quantify the monthly savings opportunity from self-serve deflection, agentic AI resolution, and proactive outreach with a single pipeline run
2. **Quality at scale** — Achieve reliable structured extraction from 100% of transcripts (not a sample), with QA scoring to flag low-confidence records
3. **Speed to insight** — Deliver executive-ready KPIs within minutes of a run completing, with no manual data processing step

### Secondary goals
4. **Reproducibility** — Same inputs always produce the same outputs (deterministic sampling + LLM temperature = 0.1)
5. **Resilience** — A killed or failed mid-run loses no completed work (checkpoint system)
6. **Extensibility** — Data loader, prompt, and output schema are decoupled so production transcript sources can replace the HuggingFace corpus with minimal code changes

---

## 4. Non-Goals (v2.0)

- Real-time / streaming analysis (this is batch-oriented)
- Agent-level performance dashboards (requires real agent IDs from ACD data)
- Multi-language support (English only)
- CRM / ticketing system integrations (connector layer is a future item)
- Confidence scoring per extracted field (pipeline-level QA is in place; field-level is deferred)

---

## 5. User Personas

### Primary: Contact Centre Operations Director
**Goal:** Identify top cost-reduction opportunities and build the business case for investment in self-serve / AI capabilities
**Needs:** Executive KPIs (FCR, avoidable call %, savings opportunity), chart-ready visuals, shareable output

### Secondary: QA Manager / Workforce Management Analyst
**Goal:** Replace manual sampling with automated, consistent, scalable quality review
**Needs:** Per-call detail (agent skill, sentiment, compliance), audit trail, QA scores

### Tertiary: Data Scientist / ML Engineer
**Goal:** Build and validate the extraction pipeline, tune the prompt, extend to production data sources
**Needs:** Raw JSON outputs, QA audit results, ARCHITECTURE.md, modular code structure

---

## 6. Functional Requirements

### Pipeline (P0 — must have)
- [ ] Load transcripts from a configurable data source (HuggingFace corpus in v1.0)
- [ ] Stream transcripts without loading the full dataset into memory
- [ ] Validate each transcript before sending to the LLM (turn count, length)
- [ ] Extract 70+ structured fields per call via LLM with a defined JSON schema
- [ ] Handle API rate limits with exponential backoff and per-call retry
- [ ] Persist each result immediately after extraction (checkpoint, not batch-write)
- [ ] Resume interrupted runs without re-analyzing completed calls
- [ ] Run in sequential named batches with guaranteed non-overlapping conversation samples

### Aggregation & output (P0)
- [ ] Compute FCR rate, avoidable call %, AHT, escalation rate, sentiment improvement
- [ ] Compute monthly savings opportunity by cost lever
- [ ] Export per-call CSV, full results JSON, and `summary.json` for the dashboard
- [ ] Write a run manifest with call counts, failures, and file paths

### QA audit (P0)
- [ ] Score each result on completeness, enum validity, consistency, and plausibility
- [ ] Flag records below a configurable pass threshold
- [ ] Report aggregate pass rate with dimension-level breakdowns
- [ ] Identify the most common failure patterns

### Token tracking (P0)
- [ ] Capture prompt and completion token counts from every API response
- [ ] Compute USD cost per call and cumulative cost per run
- [ ] Embed cost summary in `summary.json` and the run manifest

### Dashboard (P0)
- [ ] Display all executive KPIs on load, no configuration required
- [ ] Show demo data when no run output is present
- [ ] Render cost waterfall, phase breakdown, issue distribution, sentiment comparison
- [ ] Display inference cost and token usage for the dataset

### Batch orchestration (P1 — important)
- [ ] Run N batches of M calls via subprocess (process isolation)
- [ ] Automatically merge batch outputs and run QA audit on completion
- [ ] Continue remaining batches even if one fails

### Merge utility (P1)
- [ ] Discover all batch JSON files automatically
- [ ] Deduplicate by `call_id` and re-run aggregation on the combined dataset
- [ ] Overwrite `summary.json` with combined results for the dashboard

---

## 7. Non-Functional Requirements

| Property | Target |
|----------|--------|
| **Throughput** | ~8 calls/min at Claude 50 RPM limit (2s inter-call delay); upgrade delay for higher volume |
| **Cost** | ~$0.0076 USD per call at Claude Haiku 4.5 pricing; ~$0.0008/call if using Gemini 2.0 Flash Lite |
| **Reproducibility** | Identical output for same `(offset, n, seed)` triple |
| **Memory** | Bounded regardless of dataset size (streaming HF, never loads full corpus) |
| **Reliability** | Zero calls lost on process kill (checkpoint saves after every successful call) |
| **QA pass rate** | ≥ 90% of calls score ≥ 60 / 100 on the QA audit |
| **Startup time** | < 10 seconds to first API call after `python run_pipeline.py` |
| **Python compatibility** | Python 3.11+ |

---

## 8. Technical Constraints

- **EXTRACTION_MODEL is the single switch** — changing it in `pipeline/config.py` propagates to the client, rate limiter, cost tracker, and startup key validator automatically
- **Claude Haiku 4.5 rate limit:** 50 RPM (`CLAUDE_RATE_LIMITER`). For Gemini: 15 RPM (`GEMINI_RATE_LIMITER`)
- **Gemini free tier (if switching):** 15 RPM · 500 RPD for `gemini-2.5-flash-lite`; use `gemini-2.0-flash-lite` (1,500 RPD) for multi-batch runs
- **LLM output format:** `response_mime_type="application/json"` enforces native JSON on Gemini calls — no fence stripping required
- **thinking_budget=0:** Must be set on all Gemini 2.5 calls — thinking tokens consume the output budget
- **max_output_tokens=8192:** Required to fit the 70-field JSON in a single response
- **NVIDIA NIM:** OpenAI-compatible endpoint at `https://integrate.api.nvidia.com/v1`; InsightsAgent auto-falls back to Claude if `NVIDIA_API_KEY` is absent
- **pandas 3.x:** ISO 8601 timestamp parsing requires `format="mixed"` (see ARCHITECTURE.md)
- **Plotly 6.7+:** `update_layout(**kwargs, key=value)` pattern raises `TypeError` — must split into two calls

---

## 9. Success Metrics

| Metric | Target | How measured |
|--------|--------|-------------|
| QA pass rate | ≥ 90% calls score ≥ 60 | `qa_audit.py` |
| Extraction completeness | 0 null `call_id` or `total_duration_seconds` | completeness dimension score |
| Enum validity | ≥ 95% of enum fields contain valid values | enum_validity dimension score |
| FCR consistency | fcr=True & escalation=True < 2% of calls | consistency dimension score |
| Pipeline reliability | 0 records lost on clean run | checkpoint + manifest comparison |
| Cost accuracy | Token cost within 5% of actual Gemini usage | `_total_tokens` vs AI Studio console |
| Test coverage | 224 unit tests, all passing, < 7s runtime | `make test` |
| Governance | 0 PII strings in LLM prompts | PIIScanner audit log |

---

## 10. Milestones

| Version | Scope | Status |
|---------|-------|--------|
| v0.1 — Proof of concept | Basic pipeline: fetch → analyze → dashboard | Complete |
| v1.0 — Production | Batch system, checkpoint, token tracking, QA audit, ARCHITECTURE.md | Complete |
| v2.0 — Agentic AI | 6-agent LangGraph pipeline, governance, memory, tool registry, orchestrator, 149 tests, CI | Complete |
| v3.0 — Agentic Patterns | ReAct loop, Chain-of-Thought, deliberation loop, vector memory, 5-component security, approval gate, 198 tests | Complete |
| v4.0 — Plug-and-Play + Traceability | Claude Haiku 4.5 primary extraction, NVIDIA NIM insights, model-aware cost/validation, DecisionLogger across all agents, 224 tests | **Complete** |
| v5.0 — Enterprise | Real transcript ingestion (S3/Snowflake/ACD), agent ID mapping, CRM FCR validation | Planned |

---

## 11. Out-of-scope for v4.0

Items explicitly deferred to v5.0:
- Webhook / event-driven trigger (call analysed within seconds of completion)
- Multi-model comparison (GPT-4o vs Gemini on same transcripts)
- Confidence scoring per extracted field (pipeline-level QA is in place)
- Streamlit Cloud deployment automation
- Role-based access control on the dashboard
- CRM / ACD integration (agent IDs, callback confirmation for FCR validation)

---

## Appendix A: Field schema reference

See `prompts/system_prompt.txt` for the full 70-field JSON extraction schema, phase definitions, and extraction rules.

## Appendix B: Cost model assumptions

- `COST_PER_CALL_USD = 6.00` — US telecom industry average, 2024 (Gartner)
- `MONTHLY_VOLUME = 100_000` — illustrative; replace with actual ACD volume
- Self-serve deflection: 85% cost avoidance (industry benchmark)
- Agentic AI resolution: 70% cost avoidance (AI still incurs infrastructure cost)
- Proactive outreach: 60% cost avoidance (some calls prevented, not all)

## Appendix C: Dataset limitations

See `README.md § Dataset` for the full list of known limitations with the HuggingFace corpus.
