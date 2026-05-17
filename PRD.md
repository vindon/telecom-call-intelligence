# Product Requirements Document

**Product:** Telecom Call Intelligence Platform
**Version:** 1.0
**Status:** Production
**Last updated:** 2026-05-17

---

## 1. Executive Summary

Contact centres are the highest-cost customer touchpoint in telecom. At $6.00 per interaction and millions of calls per month, even a 10% reduction in handle time or avoidable call volume translates to millions in annual savings — yet most operators analyse fewer than 5% of calls manually.

This platform applies large language models to 100% of call transcripts, extracting 70+ structured metadata fields per call, and delivers those insights as executive-ready KPIs and a real-time dashboard. It runs at < $0.003 per call on the Groq free tier, making it accessible for both production deployments and exploratory analysis.

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

## 4. Non-Goals (v1.0)

- Real-time / streaming analysis (this is batch-oriented)
- Agent-level performance dashboards (requires real agent IDs from ACD data)
- PII detection or redaction (out of scope for transcript dataset; add for production)
- Multi-language support (English only for v1.0)
- CRM / ticketing system integrations (connector layer is a v2 item)

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
| **Throughput** | 25–30 calls/min at Groq free tier (2s inter-call delay) |
| **Cost** | < $0.003 USD per call at current Groq pricing |
| **Reproducibility** | Identical output for same `(offset, n, seed)` triple |
| **Memory** | Bounded regardless of dataset size (streaming HF, never loads full corpus) |
| **Reliability** | Zero calls lost on process kill (checkpoint saves after every successful call) |
| **QA pass rate** | ≥ 90% of calls score ≥ 60 / 100 on the QA audit |
| **Startup time** | < 10 seconds to first API call after `python run_pipeline.py` |
| **Python compatibility** | Python 3.11+ |

---

## 8. Technical Constraints

- **Groq free tier:** 30 req/min · 14,400 req/day for `llama-3.3-70b-versatile`
- **LLM output format:** Must return flat valid JSON (enforced via system prompt Rule 1 + fence stripping)
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
| Cost accuracy | Token cost within 5% of Groq invoice | `_total_tokens` vs Groq console |

---

## 10. Milestones

| Version | Scope | Status |
|---------|-------|--------|
| v0.1 — Proof of concept | Basic pipeline: fetch → analyze → dashboard | Complete |
| v1.0 — Production | Batch system, checkpoint, token tracking, QA audit, ARCHITECTURE.md | **Complete** |
| v1.1 — Prompt tuning | QA-driven prompt improvements, A/B test on extracted field accuracy | Planned |
| v2.0 — Production data | Real transcript ingestion, agent ID mapping, CRM FCR validation | Planned |

---

## 11. Out-of-scope for v1.0

Items explicitly deferred:
- Webhook / event-driven trigger (call analysed within seconds of completion)
- PII redaction layer
- Multi-model comparison (GPT-4o vs Llama 3.3 70B on same transcripts)
- Confidence scoring per extracted field
- Streamlit Cloud deployment automation
- Role-based access control on the dashboard

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
