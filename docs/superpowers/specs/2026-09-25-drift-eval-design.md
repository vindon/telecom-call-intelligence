# Drift Check + Eval Harness — Design Spec

**Date:** 2026-09-25
**Status:** Approved for implementation planning
**Author:** Vinoth N (via Claude Code brainstorming session)

## Why

A portfolio piece is being built to showcase this pipeline's LangGraph
architecture, agent-to-agent handoffs, and its quality/observability posture
(see the companion, not-yet-detailed "portfolio artifacts" work below). That
narrative wants to claim "drift detection" and "evals" as enforced
capabilities. An audit of the actual codebase (`pipeline/`) on 2026-09-25
found neither exists today:

- **Quality** is real: `QualityAgent`'s 100-pt QA score + the deterministic
  Data Quality Gate (`qa_audit.check_data_quality()`, see
  `docs/qa-data-quality-gate.md`).
- **Observability** is real: Langfuse tracing (`pipeline/tracing.py`),
  optional LangSmith, and `DecisionLogger`'s per-agent reasoning trace
  (`docs/decision-logging.md`).
- **Drift** and **evals** are not: `AgentMemory` (`pipeline/memory.py`)
  already persists per-run KPI history and `get_trend_summary()` averages
  it, but nothing compares a new run against that history and flags a
  deviation. There is no golden-set or regression check for extraction
  quality anywhere in the codebase — `tests/` verifies code correctness,
  not model output quality.

This spec adds both, scoped as small, real, cheaply-verifiable additions
that reuse existing infrastructure rather than introducing new ML tooling.
The goal is that the eventual portfolio narrative is defensible under a
technical interviewer's questioning, not just well-written.

## Out of scope

- The portfolio artifacts themselves (interactive diagram, case study) —
  a separate design, brainstormed after this ships (see "Handoff" below).
- Any drift response *action* beyond flagging (e.g., auto-pausing runs,
  paging someone) — this is detection/reporting only, consistent with the
  existing `QualityGate`'s pattern of gating export, not the orchestrator.
- Statistical process control beyond mean/stdev (no PSI/CUSUM) — this
  project has ~20 historical runs, not enough volume for that to be
  meaningful; the simpler check is the honestly-scoped one.
- A UI for browsing drift/eval history — `outputs/*.json` and the console
  banner are sufficient, matching how the Data Quality Gate already surfaces.

---

## 1. Eval harness

### 1.1 Golden set

New file: `evals/golden_set.json` — a new top-level `evals/` directory,
parallel to `tests/`, `pipeline/`, `dashboard/`. Kept out of `tests/`
deliberately: everything in `tests/` is documented and CI-enforced as
"zero API calls, < 7 seconds" (`CLAUDE.md`); this harness makes real,
billed API calls and must never be mistaken for part of that fast suite.

Structure — a list of ~15 entries, chosen for diversity across
`issue_1_category` (billing, technical, retention, general, etc.) so the
eval isn't skewed to one call type:

```json
{
  "frozen_from": "outputs/full_results_20260809_135223.json",
  "frozen_date": "2026-09-25",
  "model_at_freeze": "claude-haiku-4-5-20251001",
  "cases": [
    {
      "call_id": "<real call_id from telecom_200k.csv>",
      "transcript_text": "<the full transcript, copied verbatim>",
      "call_date": "<from the source record>",
      "expected": {
        "issue_1_category": "billing",
        "fcr_indicator": true,
        "escalation_required": false,
        "customer_sentiment_start": "negative",
        "customer_sentiment_end": "positive",
        "all_issues_resolved": true,
        "total_duration_seconds": 420
      },
      "expected_qa_grade": "HIGH"
    }
  ]
}
```

**The transcript is copied inline, not referenced by `call_id` for a
later lookup.** Checked `pipeline/hf_loader.py` while writing this spec:
it only exposes offset/seed-based sampling
(`load_telecom_transcripts(n, seed, offset)`) — there is no "fetch by
call_id" function, and adding one just for this would be a second way to
read the same CSV. Storing `transcript_text` directly in
`golden_set.json` makes the eval self-contained (immune to
`telecom_200k.csv` being regenerated, reordered, or unavailable) and
matches the "frozen" intent — both the input and the expected output are
frozen at creation time, not just the output.

**Ground truth is a frozen, QA-verified historical extraction — not
hand-labeled from scratch.** Selection rule for the 15 cases: pull from an
existing `outputs/full_results_*.json` run, filter to records that scored
HIGH QA grade *and* passed the Data Quality Gate (`_dq_gate_passed=true`),
then pick 15 spanning distinct `issue_1_category` values (round-robin, not
random, so rare categories aren't accidentally excluded). The matching raw
transcript text for each selected `call_id` is pulled from
`telecom_200k.csv` once, at golden-set creation time, and copied into
`golden_set.json` — a one-time build step
(`scripts/build_golden_set.py`), not something the eval script does on
every run. `build_golden_set.py` prints its 15 selections (transcript
excerpt + expected fields) for a human skim before writing the file —
these values become the standard everything else is judged against, so
they're worth one look, not just an automated filter.

### 1.2 Eval script — `eval_golden_set.py`

Standalone script at repo root, same pattern as `qa_audit.py` /
`retroactive_dq_audit.py`.

```
def run_eval(golden_set_path: Path = Path("evals/golden_set.json")) -> EvalReport:
    golden = json.loads(golden_set_path.read_text())

    results = []
    for case in golden["cases"]:
        transcript = {
            "call_id": case["call_id"],
            "call_date": case["call_date"],
            "transcript_text": case["transcript_text"],
        }
        try:
            actual = analyze_transcript(client, SYSTEM_PROMPT, transcript)
        except Exception as exc:
            results.append(CaseResult(case["call_id"], status="failed",
                                       reason=str(exc)))
            continue
        results.append(score_case(case, actual))  # per-field diff, see below

    return build_report(results)  # aggregate accuracy, per-field breakdown
```

No "transcript not found" branch — since the transcript is embedded in
`golden_set.json` itself (see 1.1), the only failure mode left is the
extraction call itself failing, which the `except` clause already covers.

`score_case()` — per-field comparison, not a single pass/fail:

- Categorical/boolean fields (`issue_1_category`, `fcr_indicator`,
  `escalation_required`, `customer_sentiment_start`,
  `customer_sentiment_end`, `all_issues_resolved`): exact match.
- `total_duration_seconds`: pass if within ±15% of expected (transcripts
  are real customer calls; the model's phase-duration inference has
  legitimate small variance even at 100% correctness, per the reasoning
  already documented in `docs/qa-data-quality-gate.md`'s overlay-fields
  section).
- `expected_qa_grade`: informational, not gating — a HIGH→MEDIUM/LOW
  regression on a previously-HIGH case is reported prominently in the
  summary but doesn't independently fail the run (the field-level accuracy
  already captures the substance of a regression).

**A failed case still counts in the denominator.** A case that errors out
due to a flaky provider is not silently excluded — that would let a bad
network day masquerade as "0% regression." `status="failed"` counts as 0%
accuracy for that case's fields.

**Report:** printed to console (per-field accuracy table, aggregate %,
any HIGH→lower grade regressions called out by name) and written to
`outputs/eval_report_<timestamp>.json`. Exit code 1 if aggregate
field-accuracy drops below `EVAL_PASS_THRESHOLD_PCT` (new config constant,
default 85%) — for `make eval-golden` to fail visibly when run manually or
on a schedule.

**Cost:** ~15 calls × ~$0.0076/call (current README figure) ≈ $0.11 per
run. **Never run automatically** — `make eval-golden` is a new, separate
Makefile target, not part of `make check` or CI. Running it always
requires explicit confirmation and a stated cost estimate, per standing
practice for real API spend.

### 1.3 Fast unit test — `tests/test_eval_golden_set.py`

Tests `score_case()` and `build_report()` directly with synthetic
case/actual dicts — no dataset loading, no API calls, no golden_set.json
dependency. Covers: exact-match pass/fail, duration tolerance boundary
(exactly ±15%), a failed case, aggregate accuracy math, and the HIGH→LOW
regression flag.

---

## 2. Drift check

### 2.1 `pipeline/drift.py` — new module

Follows the existing `governance.py` pattern (`QualityGate`, `BudgetGuard`)
— a small stateless class with a `check()` method, no I/O of its own (the
caller supplies history and current metrics; caller also owns writing the
result to `summary.json`/decision log/`AuditLog`).

```python
DRIFT_METRICS = ["fcr_rate_pct", "aht_minutes", "qa_avg_score", "data_quality_pass_rate_pct"]

@dataclass
class MetricDrift:
    metric: str
    current: float
    baseline_mean: float
    baseline_stdev: float
    pct_deviation: float
    z_score: float | None   # None when baseline_stdev == 0
    drifted: bool

@dataclass
class DriftReport:
    baseline_run_count: int
    sufficient_history: bool   # False when baseline_run_count < DRIFT_MIN_RUNS_FOR_BASELINE
    metrics: list[MetricDrift]
    any_drifted: bool

class DriftGuard:
    def check(self, current: dict, history: list[dict]) -> DriftReport:
        """
        `history` is prior runs only (caller passes MEMORY.get_run_history()
        BEFORE calling MEMORY.record_run() for the current run — see 2.2).
        A metric absent from `current` or from >20% of `history` entries is
        skipped, not treated as a 0 (avoids punishing schema evolution,
        e.g. data_quality_pass_rate_pct not existing in pre-4.5.0 runs).
        """
```

**Threshold rule per metric** (using the config constants from 2.2):
`drifted = abs(current - baseline_mean) > max(DRIFT_Z_THRESHOLD * baseline_stdev, DRIFT_PCT_THRESHOLD * abs(baseline_mean))`

`max()` means a deviation has to clear whichever of the two bounds is
*larger* — the stricter one wins, not the looser one:

- If a metric's historical variance is tiny (e.g. `qa_avg_score` sitting
  tightly at 88-90 for 10 runs straight), `2σ` is a very small number —
  without a floor, even a practically meaningless 1-point move would look
  like "many standard deviations" and false-trigger. The 10%-relative
  floor prevents that: the metric now needs an actual double-digit-percent
  move to flag, not just a move that's unusual *relative to unusually low
  noise*.
- If a metric is naturally noisy (e.g. `fcr_rate_pct` swinging ±8% run to
  run on small batch sizes), a flat 10% floor alone would flag normal
  variation constantly. The `2σ` term raises the bar to "unusual even
  given how noisy this metric normally is."

Net effect: a run must be a genuine outlier *and* a practically meaningful
move to flag — deliberately biased toward fewer false alarms given this
project has only ~20 historical runs to build a baseline from.

**Cold start:** `sufficient_history=False` when `baseline_run_count <
DRIFT_MIN_RUNS_FOR_BASELINE` (new config constant, default 5) —
`any_drifted` is always `False` in this case, reported as
"insufficient history for drift baseline" rather than silently skipped,
so the console banner is honest about *why* there's no verdict yet.

### 2.2 Wiring — `ExportAgent`

`pipeline/agents/export_agent.py` already calls `MEMORY.record_run(...)`
at the end of a successful export (and, per [4.6.0], embeds the run into
`VECTOR_STORE` there too). The drift check slots into the same place,
*before* `record_run()` is called (so `history` doesn't include the
current run comparing against itself):

```python
history = MEMORY.get_run_history(last_n=DRIFT_BASELINE_WINDOW)  # default 10
drift_report = DriftGuard().check(current=run_summary, history=history)
# ... write drift_report into summary.json, decision log, AUDIT_LOG ...
MEMORY.record_run(run_summary)  # unchanged, happens after
```

`memory.py::record_run()`'s `entry` dict gains one new key,
`data_quality_pass_rate_pct` (currently computed in `qa_report`/
`summary.json` but not persisted into `AgentMemory` — this is the one
schema change to an existing file). Old entries without this key are
handled by `DriftGuard`'s existing "skip metric if absent" rule, not a
migration.

**Console banner** (in `export_node`, alongside the existing QA/export
print block): prints the drift verdict per metric only when
`sufficient_history=True`; when `False`, prints the "insufficient
history" line instead so a fresh clone of the repo doesn't look broken.

**Config additions** (`pipeline/config.py`, alongside existing thresholds):

```python
DRIFT_MIN_RUNS_FOR_BASELINE = 5
DRIFT_BASELINE_WINDOW = 10       # how many prior runs form the baseline
DRIFT_Z_THRESHOLD = 2.0
DRIFT_PCT_THRESHOLD = 0.10
```

### 2.3 Fast unit test — `tests/test_drift.py`

Pure Python, deterministic, synthetic `history` lists — no API calls, no
real `AgentMemory` file I/O (construct `MetricDrift`/history dicts
directly). Covers: no drift (current within bounds), drift by z-score,
drift by %-floor when stdev≈0, insufficient-history path, a metric
missing from `current`, a metric missing from most of `history`.

---

## Testing summary

| Component | Test file | Real API calls? |
|---|---|---|
| `score_case()`/`build_report()` logic | `tests/test_eval_golden_set.py` | No |
| `eval_golden_set.py` end-to-end | Manual (`make eval-golden`) | Yes (~$0.11) |
| `DriftGuard.check()` | `tests/test_drift.py` | No |
| `ExportAgent` wiring (drift call site) | `tests/test_agents/test_export_agent.py` (extend existing) | No |

All new fast tests join the existing `pytest tests/ -m "not slow and not
integration"` suite and must keep `--cov-fail-under=85` green.

## Handoff

Once this ships (real drift/eval numbers exist, e.g. an actual
`eval_report_*.json` and at least one live `drift_report`), the portfolio
artifacts (interactive diagram, case-study HTML + Markdown) get their own
brainstorming session — the design decisions already gathered for that
(layered/expandable interactive diagram, dense diagram in the static case
studies, all three of recruiter/portfolio/GitHub as distribution channels,
"both HTML and Markdown" for the case study) carry forward, but the
specific quality/drift/eval narrative content waits until there's a real
number to cite instead of a projected one.
