# Drift Check + Eval Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two small, real quality-monitoring capabilities to the pipeline — a rolling KPI drift check and a golden-set extraction-accuracy eval harness — so the project's "drift detection" and "evals" claims are true, not narrated.

**Architecture:** `pipeline/drift.py`'s stateless `DriftGuard` compares each run's KPIs against a mean/stdev baseline built from `AgentMemory`'s existing run history, wired into `ExportAgent` right before it records the current run into that same history. `eval_golden_set.py` re-runs extraction on a frozen 15-case golden set (real transcripts + expected fields frozen from a past QA-verified run) and diffs the output, reusing `pipeline.analyzer.analyze_batch()` for the actual LLM calls rather than reimplementing batching/rate-limiting.

**Tech Stack:** Python 3.11, pytest, dataclasses, pandas (CSV rebuild), existing `pipeline.analyzer`/`pipeline.llm_clients`/`qa_audit` modules — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-25-drift-eval-design.md`

## Global Constraints

- Everything in `tests/` stays "zero API calls, < 7 seconds" (per `CLAUDE.md`) — real-API-call code (the eval's `run_eval()`) lives outside `tests/`, tested only via mocks.
- `--cov-fail-under=85` must stay green after every task (current: ~91%).
- `make check` (lint + type-check + test) must pass after every task.
- Never run `make eval-golden` or `eval_golden_set.py` against the real API without first telling the user the exact cost estimate and getting explicit confirmation (~$0.11 for the full 15-case set at current pricing) — this plan only builds the harness, it does not execute a real eval run.
- `DriftGuard`/`eval_golden_set.py` are detection/reporting only — neither may block export, halt the orchestrator, or otherwise change pipeline control flow.
- Follow `scripts/check_docs_sync.py`'s existing gate: any task that changes the test count must be reconciled in the final docs-sync task, not left stale.

---

### Task 1: `pipeline/drift.py` — DriftGuard

**Files:**
- Modify: `pipeline/config.py` (append new `── Drift detection ──` section)
- Create: `pipeline/drift.py`
- Test: `tests/test_drift.py`

**Interfaces:**
- Produces: `pipeline.drift.DriftGuard` (class, `.check(current: dict, history: list[dict]) -> DriftReport`), `pipeline.drift.DriftReport` (dataclass: `baseline_run_count: int`, `sufficient_history: bool`, `metrics: list[MetricDrift]`, property `any_drifted: bool`, method `to_dict() -> dict`), `pipeline.drift.MetricDrift` (dataclass: `metric: str`, `current: float`, `baseline_mean: float`, `baseline_stdev: float`, `pct_deviation: float`, `z_score: float | None`, `drifted: bool`), `pipeline.drift.DRIFT_GUARD` (module-level singleton instance).
- Consumes: nothing from other tasks (foundational).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_drift.py`:

```python
"""
Tests for pipeline/drift.py — DriftGuard cross-run KPI drift detection.
Pure Python, deterministic, no API calls, no AgentMemory file I/O.
"""

import pytest

from pipeline.drift import DriftGuard


def _history(n: int, **overrides) -> list[dict]:
    base = {
        "fcr_rate_pct": 70.0,
        "aht_minutes": 7.0,
        "qa_avg_score": 88.0,
        "data_quality_pass_rate_pct": 95.0,
    }
    base.update(overrides)
    return [dict(base) for _ in range(n)]


class TestInsufficientHistory:
    def test_below_minimum_reports_insufficient(self):
        report = DriftGuard().check(
            current={"fcr_rate_pct": 70.0}, history=_history(3)
        )
        assert report.sufficient_history is False
        assert report.baseline_run_count == 3
        assert report.metrics == []
        assert report.any_drifted is False


class TestStdevZeroBaseline:
    def test_small_move_within_pct_floor_is_not_drift(self):
        # Identical baseline (stdev=0); a move smaller than the 10% floor
        # must not fire just because it's "infinitely many standard
        # deviations" away from a zero-variance baseline.
        report = DriftGuard().check(
            current={"fcr_rate_pct": 72.0}, history=_history(10)
        )
        metric = next(m for m in report.metrics if m.metric == "fcr_rate_pct")
        assert metric.drifted is False
        assert metric.z_score is None
        assert metric.baseline_stdev == 0.0

    def test_large_move_beyond_pct_floor_is_drift(self):
        report = DriftGuard().check(
            current={"fcr_rate_pct": 90.0}, history=_history(10)
        )
        metric = next(m for m in report.metrics if m.metric == "fcr_rate_pct")
        assert metric.drifted is True
        assert metric.z_score is None


class TestNoisyBaseline:
    NOISY = [
        {"fcr_rate_pct": v, "aht_minutes": 7.0, "qa_avg_score": 88.0,
         "data_quality_pass_rate_pct": 95.0}
        for v in [60.0, 62.0, 64.0, 66.0, 68.0, 70.0, 72.0, 74.0, 76.0, 78.0]
    ]
    # mean=70.0, variance=34.0, stdev=5.8309518948453

    def test_move_exceeding_naive_pct_but_within_z_bound_is_not_drift(self):
        # deviation=9 -> pct_dev=12.9% (would fire on a naive 10% check
        # alone) but z=1.54 (<2) and combined threshold=max(2*5.83, 7.0)=11.66
        report = DriftGuard().check(
            current={"fcr_rate_pct": 79.0}, history=self.NOISY
        )
        metric = next(m for m in report.metrics if m.metric == "fcr_rate_pct")
        assert metric.drifted is False
        assert metric.z_score == pytest.approx(1.5435, rel=1e-3)

    def test_move_exceeding_z_bound_is_drift(self):
        # deviation=15 -> threshold=11.66 -> drifted
        report = DriftGuard().check(
            current={"fcr_rate_pct": 85.0}, history=self.NOISY
        )
        metric = next(m for m in report.metrics if m.metric == "fcr_rate_pct")
        assert metric.drifted is True
        assert metric.z_score == pytest.approx(2.5725, rel=1e-3)


class TestMissingMetrics:
    def test_metric_absent_from_current_is_excluded_not_flagged(self):
        current = {"fcr_rate_pct": 70.0, "aht_minutes": 7.0, "qa_avg_score": 88.0}
        report = DriftGuard().check(current=current, history=_history(10))
        names = {m.metric for m in report.metrics}
        assert names == {"fcr_rate_pct", "aht_minutes", "qa_avg_score"}

    def test_metric_missing_from_most_of_history_is_skipped(self):
        history = _history(9, **{})
        for h in history:
            del h["data_quality_pass_rate_pct"]
        history.append(
            {"fcr_rate_pct": 70.0, "aht_minutes": 7.0, "qa_avg_score": 88.0,
             "data_quality_pass_rate_pct": 95.0}
        )  # only 1/10 has it -> below the 80% presence floor
        current = {
            "fcr_rate_pct": 70.0, "aht_minutes": 7.0, "qa_avg_score": 88.0,
            "data_quality_pass_rate_pct": 95.0,
        }
        report = DriftGuard().check(current=current, history=history)
        names = {m.metric for m in report.metrics}
        assert "data_quality_pass_rate_pct" not in names
        assert names == {"fcr_rate_pct", "aht_minutes", "qa_avg_score"}


class TestReportSerialization:
    def test_to_dict_shape(self):
        report = DriftGuard().check(
            current={"fcr_rate_pct": 90.0}, history=_history(10)
        )
        d = report.to_dict()
        assert d["baseline_run_count"] == 10
        assert d["sufficient_history"] is True
        assert d["any_drifted"] is True
        assert d["metrics"][0]["metric"] == "fcr_rate_pct"
        assert d["metrics"][0]["drifted"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_drift.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.drift'`

- [ ] **Step 3: Add config constants**

In `pipeline/config.py`, append after the `── Security ──` section (end of file):

```python

# ── Drift detection ────────────────────────────────────────────────────
# Cross-run KPI drift check (pipeline/drift.py), wired into ExportAgent.
# Detection/reporting only — never blocks export or the orchestrator.
DRIFT_MIN_RUNS_FOR_BASELINE = 5  # need at least this many prior runs to compute a baseline
DRIFT_BASELINE_WINDOW = 10  # how many prior runs form the rolling baseline
DRIFT_Z_THRESHOLD = 2.0  # standard deviations from baseline mean
DRIFT_PCT_THRESHOLD = 0.10  # relative-deviation floor (10%) — see drift.py for why both exist
DRIFT_METRICS = ("fcr_rate_pct", "aht_minutes", "qa_avg_score", "data_quality_pass_rate_pct")
```

- [ ] **Step 4: Implement `pipeline/drift.py`**

```python
"""
pipeline/drift.py  —  Cross-Run KPI Drift Detection
------------------------------------------------------
Compares the current run's KPIs against a rolling baseline built from
AgentMemory's run history (pipeline/memory.py). Detection only — this
module never blocks, retries, or otherwise acts on a drifted run; the
caller (ExportAgent) decides what to do with the report (currently: log
it and surface it in summary.json/decision log, nothing more).

Threshold rule per metric:
    drifted = |current - baseline_mean| > max(DRIFT_Z_THRESHOLD * stdev,
                                               DRIFT_PCT_THRESHOLD * |mean|)

max() means a deviation must clear whichever bound is LARGER — a metric
with near-zero historical variance needs an actual double-digit-percent
move to flag (the z-score alone would over-trigger on tiny noise), and a
naturally noisy metric needs a move that's unusual even given its normal
noise (a flat percentage floor alone would flag routine variation). See
docs/superpowers/specs/2026-09-25-drift-eval-design.md for the full
rationale and worked examples.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pipeline.config import (
    DRIFT_METRICS,
    DRIFT_MIN_RUNS_FOR_BASELINE,
    DRIFT_PCT_THRESHOLD,
    DRIFT_Z_THRESHOLD,
)

# A metric is skipped (not treated as absent-equals-zero) if it's missing
# from more than this fraction of the baseline window — avoids punishing
# schema evolution (e.g. data_quality_pass_rate_pct not existing in runs
# recorded before it was added to AgentMemory).
_MIN_METRIC_PRESENCE_FRACTION = 0.8


@dataclass
class MetricDrift:
    metric: str
    current: float
    baseline_mean: float
    baseline_stdev: float
    pct_deviation: float
    z_score: float | None
    drifted: bool


@dataclass
class DriftReport:
    baseline_run_count: int
    sufficient_history: bool
    metrics: list[MetricDrift] = field(default_factory=list)

    @property
    def any_drifted(self) -> bool:
        return any(m.drifted for m in self.metrics)

    def to_dict(self) -> dict:
        return {
            "baseline_run_count": self.baseline_run_count,
            "sufficient_history": self.sufficient_history,
            "any_drifted": self.any_drifted,
            "metrics": [
                {
                    "metric": m.metric,
                    "current": m.current,
                    "baseline_mean": round(m.baseline_mean, 3),
                    "baseline_stdev": round(m.baseline_stdev, 3),
                    "pct_deviation": round(m.pct_deviation, 3),
                    "z_score": round(m.z_score, 3) if m.z_score is not None else None,
                    "drifted": m.drifted,
                }
                for m in self.metrics
            ],
        }


class DriftGuard:
    """Stateless — construct once (see DRIFT_GUARD below), call check() per run."""

    def check(self, current: dict, history: list[dict]) -> DriftReport:
        baseline_run_count = len(history)
        if baseline_run_count < DRIFT_MIN_RUNS_FOR_BASELINE:
            return DriftReport(
                baseline_run_count=baseline_run_count,
                sufficient_history=False,
            )

        min_present = max(2, int(_MIN_METRIC_PRESENCE_FRACTION * baseline_run_count))
        metrics = []
        for name in DRIFT_METRICS:
            if name not in current:
                continue
            values = [h[name] for h in history if name in h]
            if len(values) < min_present:
                continue
            metrics.append(self._check_metric(name, current[name], values))

        return DriftReport(
            baseline_run_count=baseline_run_count,
            sufficient_history=True,
            metrics=metrics,
        )

    @staticmethod
    def _check_metric(name: str, current_value: float, values: list[float]) -> MetricDrift:
        n = len(values)
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        stdev = variance**0.5

        deviation = abs(current_value - mean)
        pct_deviation = deviation / abs(mean) if mean else 0.0
        z_score = deviation / stdev if stdev > 0 else None

        threshold = max(DRIFT_Z_THRESHOLD * stdev, DRIFT_PCT_THRESHOLD * abs(mean))
        drifted = deviation > threshold

        return MetricDrift(
            metric=name,
            current=current_value,
            baseline_mean=mean,
            baseline_stdev=stdev,
            pct_deviation=pct_deviation,
            z_score=z_score,
            drifted=drifted,
        )


DRIFT_GUARD = DriftGuard()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_drift.py -v`
Expected: PASS — 9 tests

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check pipeline/drift.py tests/test_drift.py pipeline/config.py
.venv/bin/ruff format pipeline/drift.py tests/test_drift.py pipeline/config.py
git add pipeline/drift.py pipeline/config.py tests/test_drift.py
git commit -m "feat: add DriftGuard cross-run KPI drift detection"
```

---

### Task 2: `pipeline/memory.py` — persist `data_quality_pass_rate_pct`

**Files:**
- Modify: `pipeline/memory.py:36,110-148` (import `RUN_HISTORY_LIMIT`, extend `record_run()`)
- Test: `tests/test_memory.py` (extend `TestAgentMemoryRecordRun`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `AgentMemory.record_run()` now persists `data_quality_pass_rate_pct` into each `run_history` entry (defaults to `0` if the caller doesn't pass it — matches the existing pattern for every other field in this method).

- [ ] **Step 1: Write the failing test**

In `tests/test_memory.py`, add to `TestAgentMemoryRecordRun`:

```python
    def test_record_run_persists_data_quality_pass_rate(self, tmp_memory, sample_run_summary):
        tmp_memory.record_run({**sample_run_summary, "data_quality_pass_rate_pct": 92.5})
        history = tmp_memory.get_run_history(last_n=1)
        assert history[0]["data_quality_pass_rate_pct"] == 92.5

    def test_record_run_defaults_data_quality_pass_rate_when_absent(
        self, tmp_memory, sample_run_summary
    ):
        tmp_memory.record_run(sample_run_summary)  # fixture doesn't set this key
        history = tmp_memory.get_run_history(last_n=1)
        assert history[0]["data_quality_pass_rate_pct"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_memory.py -k data_quality_pass_rate -v`
Expected: FAIL — `KeyError: 'data_quality_pass_rate_pct'`

- [ ] **Step 3: Implement**

In `pipeline/memory.py`, change the import line:

```python
from pipeline.config import MEMORY_PATH, RUN_HISTORY_LIMIT
```

In `record_run()`, add one key to the `entry` dict (after `"qa_verdict"`):

```python
            "qa_verdict": run_summary.get("qa_verdict", "N/A"),
            "data_quality_pass_rate_pct": run_summary.get("data_quality_pass_rate_pct", 0),
```

And replace the hardcoded cap (drive-by fix — this magic number already duplicates the existing `RUN_HISTORY_LIMIT` config constant):

```python
        # Keep last RUN_HISTORY_LIMIT runs
        self._data["run_history"].append(entry)
        if len(self._data["run_history"]) > RUN_HISTORY_LIMIT:
            self._data["run_history"] = self._data["run_history"][-RUN_HISTORY_LIMIT:]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_memory.py -v`
Expected: PASS — all tests, including the pre-existing `test_run_history_capped_at_50` (unaffected — `RUN_HISTORY_LIMIT` is still `50`)

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check pipeline/memory.py tests/test_memory.py
.venv/bin/ruff format pipeline/memory.py tests/test_memory.py
git add pipeline/memory.py tests/test_memory.py
git commit -m "feat: persist data_quality_pass_rate_pct in AgentMemory run history"
```

---

### Task 3: Wire `DriftGuard` into `ExportAgent`

**Files:**
- Modify: `pipeline/agents/export_agent.py:22-29` (imports), `:64-115` (drift block + summary.json), `:160` (stale version fix), `:272` (return value)
- Test: `tests/test_agents/test_export_agent.py` (new `TestDriftCheck` class)

**Interfaces:**
- Consumes: `pipeline.drift.DRIFT_GUARD`, `DriftReport` (Task 1); `MEMORY.record_run()`'s new `data_quality_pass_rate_pct` support (Task 2).
- Produces: `ExportAgent.run()`'s return dict gains a `"drift_report": dict` key (the `DriftReport.to_dict()` output) — Task 4 consumes this.

- [ ] **Step 1: Write the failing tests**

In `tests/test_agents/test_export_agent.py`, add after the `TestEmergencyExport` class:

```python
class TestDriftCheck:
    def test_insufficient_history_reports_as_such(self, isolate, make_record):
        out = ExportAgent().run(_full_state(make_record))
        summary = json.loads((isolate / "summary.json").read_text())
        assert summary["drift_report"]["sufficient_history"] is False
        assert summary["drift_report"]["any_drifted"] is False
        assert out["drift_report"]["sufficient_history"] is False

    def test_drifted_metric_is_flagged_and_does_not_block_export(self, isolate, make_record):
        for i in range(5):
            exp_mod.MEMORY.record_run(
                {
                    "run_timestamp": f"seed-{i}",
                    "fcr_rate_pct": 75.0,
                    "avg_handle_time_minutes": 7.0,
                    "qa_avg_score": 90.0,
                    "data_quality_pass_rate_pct": 95.0,
                }
            )
        state = _full_state(make_record)
        state["qa_report"]["summary"]["data_quality_pass_rate_pct"] = 50.0
        out = ExportAgent().run(state)
        summary = json.loads((isolate / "summary.json").read_text())
        assert summary["drift_report"]["sufficient_history"] is True
        assert summary["drift_report"]["any_drifted"] is True
        drifted = [m["metric"] for m in summary["drift_report"]["metrics"] if m["drifted"]]
        assert "data_quality_pass_rate_pct" in drifted
        assert Path(out["export_paths"]["csv"]).exists()  # export still succeeded

    def test_baseline_excludes_the_current_run(self, isolate, make_record):
        # Regression guard: if the current run leaked into its own baseline,
        # a real drift would be diluted/masked by itself.
        for i in range(5):
            exp_mod.MEMORY.record_run(
                {
                    "run_timestamp": f"seed-{i}",
                    "fcr_rate_pct": 75.0,
                    "avg_handle_time_minutes": 7.0,
                    "qa_avg_score": 90.0,
                    "data_quality_pass_rate_pct": 95.0,
                }
            )
        state = _full_state(make_record)
        state["aggregated_metrics"]["kpis"]["fcr_rate_pct"] = 40.0
        out = ExportAgent().run(state)
        summary = json.loads((isolate / "summary.json").read_text())
        fcr = next(m for m in summary["drift_report"]["metrics"] if m["metric"] == "fcr_rate_pct")
        assert fcr["baseline_mean"] == 75.0
        assert fcr["drifted"] is True

    def test_drift_decision_logged(self, isolate, make_record):
        out = ExportAgent().run(_full_state(make_record))
        types = [r["decision_type"] for r in out["decision_log"]]
        assert "drift_check" in types

    def test_emergency_export_logs_skipped_drift_decision(self, isolate, make_record):
        state = _full_state(make_record)
        state["aggregated_metrics"] = {}
        state["agent_insights"] = {}
        out = ExportAgent().run(state)  # must not raise
        types = [r["decision_type"] for r in out["decision_log"]]
        assert "drift_check" in types
        assert out["drift_report"]["sufficient_history"] is False


class TestManifestVersion:
    def test_pipeline_version_matches_pyproject(self, isolate, make_record):
        import re

        pyproject = (Path(__file__).parent.parent.parent / "pyproject.toml").read_text()
        version = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE).group(1)
        out = ExportAgent().run(_full_state(make_record))
        manifest = json.loads(open(out["export_paths"]["manifest"]).read())
        assert manifest["pipeline_version"] == version
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_agents/test_export_agent.py -k "DriftCheck or ManifestVersion" -v`
Expected: FAIL — `KeyError: 'drift_report'` and a version-string mismatch (`"4.5.0"` vs current pyproject version)

- [ ] **Step 3: Implement**

In `pipeline/agents/export_agent.py`, extend the imports:

```python
from pipeline.config import (
    DRIFT_BASELINE_WINDOW,
    DRIFT_MIN_RUNS_FOR_BASELINE,
    OUTPUT_DIR,
    QUALITY_WARN_RATE,
    VECTOR_MEMORY_ENABLED,
)
from pipeline.decision_log import DecisionLogger, summarize_decisions
from pipeline.drift import DRIFT_GUARD, DriftReport
```

Insert the drift-check block right after `emergency_run = not metrics.get("kpis")` and before the existing `dl.log(decision_type="export_scope", ...)` call:

```python
        emergency_run = not metrics.get("kpis")

        # ── Drift check — compare this run's KPIs against the rolling
        # baseline BEFORE this run is recorded into that same history (the
        # MEMORY.record_run() call further below). Detection/reporting
        # only — never blocks export. See pipeline/drift.py.
        MEMORY.load()
        kpis = metrics.get("kpis", {})
        qa_summary_for_drift = qa_report.get("summary", {})
        if emergency_run:
            drift_report = DriftReport(baseline_run_count=0, sufficient_history=False)
            drift_decision = "Skipped — emergency export has no aggregated KPIs to compare"
            drift_reason = "Quality gate failure path: aggregated_metrics has no kpis"
        else:
            current_metrics = {
                "fcr_rate_pct": kpis.get("fcr_rate_pct", 0),
                "aht_minutes": kpis.get("avg_handle_time_minutes", 0),
                "qa_avg_score": qa_summary_for_drift.get("avg_score", 0),
                "data_quality_pass_rate_pct": qa_summary_for_drift.get(
                    "data_quality_pass_rate_pct", 100.0
                ),
            }
            history = MEMORY.get_run_history(last_n=DRIFT_BASELINE_WINDOW)
            drift_report = DRIFT_GUARD.check(current=current_metrics, history=history)
            if drift_report.sufficient_history:
                drift_decision = (
                    f"Drift check: {'DRIFTED' if drift_report.any_drifted else 'stable'} "
                    f"({drift_report.baseline_run_count} prior run(s) in baseline)"
                )
                n_drifted = sum(1 for m in drift_report.metrics if m.drifted)
                drift_reason = (
                    f"{n_drifted} of {len(drift_report.metrics)} tracked metric(s) "
                    "exceeded the drift threshold"
                )
            else:
                drift_decision = "Insufficient history for drift baseline"
                drift_reason = (
                    f"Only {drift_report.baseline_run_count} prior run(s) recorded — "
                    f"need {DRIFT_MIN_RUNS_FOR_BASELINE} to establish a baseline"
                )
        dl.log(
            decision_type="drift_check",
            decision=drift_decision,
            reason=drift_reason,
            evidence=drift_report.to_dict(),
            confidence="high",
            alternatives=[
                "Block export on drift (rejected: detection/reporting only, per design)"
            ],
        )

        dl.log(
            decision_type="export_scope",
```

(The `dl.log(decision_type="export_scope", ...)` call and everything below it through `decision_log = dl.finalize()` stays exactly as it is today — only the new block above is inserted before it.)

Inside the `if not emergency_run:` block (where `metrics["decision_summary"]` is set), add:

```python
            metrics["decision_summary"] = summarize_decisions(decision_log)
            metrics["drift_report"] = drift_report.to_dict()
```

Fix the stale hardcoded version (found during the 2026-09-25 engineering-standards audit — was already stale at `"4.5.0"` before this change):

```python
            "pipeline_version": "4.7.0",
```

Change the final `return` statement:

```python
        return {**state, "export_paths": export_paths, "decision_log": decision_log,
                "drift_report": drift_report.to_dict()}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_agents/test_export_agent.py -v`
Expected: PASS — all tests (existing + 6 new)

- [ ] **Step 5: Run the full fast suite to check for regressions**

Run: `.venv/bin/python -m pytest tests/ -m "not slow and not integration" -q`
Expected: PASS — all tests (count will be higher than 464; final count gets reconciled in Task 8)

- [ ] **Step 6: Commit**

```bash
.venv/bin/ruff check pipeline/agents/export_agent.py tests/test_agents/test_export_agent.py
.venv/bin/ruff format pipeline/agents/export_agent.py tests/test_agents/test_export_agent.py
git add pipeline/agents/export_agent.py tests/test_agents/test_export_agent.py
git commit -m "feat: wire DriftGuard into ExportAgent; fix stale pipeline_version"
```

---

### Task 4: Console banner in `graph.py`'s `export_node`

**Files:**
- Modify: `pipeline/graph.py:89-113` (add `drift_report` to `PipelineState`), `:353-365` (`export_node` banner)
- Test: `tests/test_graph.py` (extend `TestNodeWrappers`)

**Interfaces:**
- Consumes: `result["drift_report"]` dict shape from Task 3 (`DriftReport.to_dict()`'s keys: `sufficient_history`, `any_drifted`, `baseline_run_count`, `metrics`).
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing tests**

In `tests/test_graph.py`, add to `TestNodeWrappers`:

```python
    def test_export_node_prints_drift_banner_when_drifted(self, capsys):
        import pipeline.graph as graph_mod

        fake_result = {
            "export_paths": {"csv": "outputs/x.csv"},
            "decision_log": [],
            "drift_report": {
                "sufficient_history": True,
                "any_drifted": True,
                "baseline_run_count": 8,
                "metrics": [
                    {
                        "metric": "fcr_rate_pct",
                        "current": 40.0,
                        "baseline_mean": 75.0,
                        "drifted": True,
                    },
                ],
            },
        }
        with patch.object(graph_mod, "_export_agent") as mock_agent:
            mock_agent.run.return_value = fake_result
            graph_mod.export_node({"aggregated_metrics": {}})
        out = capsys.readouterr().out
        assert "DRIFTED" in out
        assert "fcr_rate_pct" in out

    def test_export_node_prints_insufficient_history(self, capsys):
        import pipeline.graph as graph_mod

        fake_result = {
            "export_paths": {"csv": "outputs/x.csv"},
            "decision_log": [],
            "drift_report": {
                "sufficient_history": False,
                "any_drifted": False,
                "baseline_run_count": 2,
                "metrics": [],
            },
        }
        with patch.object(graph_mod, "_export_agent") as mock_agent:
            mock_agent.run.return_value = fake_result
            graph_mod.export_node({"aggregated_metrics": {}})
        out = capsys.readouterr().out
        assert "insufficient history" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_graph.py -k drift_banner -v`
Expected: FAIL — `AssertionError` (banner text not printed yet)

- [ ] **Step 3: Implement**

In `pipeline/graph.py`, add `drift_report: dict` to `PipelineState` (after `decision_log: list`):

```python
    # ── Traceability ─────────────────────────────────────────────────
    decision_log: list  # DecisionRecord dicts — agent reasoning audit trail
    drift_report: dict  # DriftReport.to_dict() — see pipeline/drift.py
```

Update `export_node`:

```python
def export_node(state: PipelineState) -> dict:
    _banner(7, 7, "ExportAgent — CSV · JSON · QA Report · Insights · Manifest")
    result = _export_agent.run(dict(state))
    paths = result["export_paths"]
    n_decisions = len(result.get("decision_log", []))
    print(f"  ✓ CSV         : {paths.get('csv', '')}")
    print(f"  ✓ Summary     : {paths.get('summary', '')}  ← Streamlit dashboard")
    print(f"  ✓ Full JSON   : {paths.get('full_results', '')}")
    print(f"  ✓ QA Report   : {paths.get('qa_report', '')}")
    print(f"  ✓ Insights    : {paths.get('insights', '')}")
    print(f"  ✓ Decisions   : {paths.get('decisions', '')}  ({n_decisions} records)")
    print(f"  ✓ Manifest    : {paths.get('manifest', '')}")

    drift = result.get("drift_report", {})
    if drift.get("sufficient_history"):
        verdict = "⚠ DRIFTED" if drift.get("any_drifted") else "✓ stable"
        print(
            f"  Drift check   : {verdict}  "
            f"({drift.get('baseline_run_count', 0)} prior runs in baseline)"
        )
        for m in drift.get("metrics", []):
            if m.get("drifted"):
                print(f"    - {m['metric']}: {m['current']} vs baseline {m['baseline_mean']}")
    else:
        print(
            f"  Drift check   : insufficient history "
            f"({drift.get('baseline_run_count', 0)} prior run(s))"
        )

    return result
```

Also add `"drift_report"` to the `required` set in `TestPipelineState::test_state_has_all_required_keys` (in `tests/test_graph.py`) for completeness:

```python
            # Traceability
            "decision_log",
            "drift_report",
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_graph.py -v`
Expected: PASS — all tests

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check pipeline/graph.py tests/test_graph.py
.venv/bin/ruff format pipeline/graph.py tests/test_graph.py
git add pipeline/graph.py tests/test_graph.py
git commit -m "feat: print drift-check verdict in export_node console banner"
```

---

### Task 5: `eval_golden_set.py` — scoring logic

**Files:**
- Modify: `pipeline/config.py` (append `── Eval harness ──` section)
- Create: `eval_golden_set.py` (scoring logic only in this task — `run_eval()`'s real-API-call orchestration is Task 7)
- Test: `tests/test_eval_golden_set.py`

**Interfaces:**
- Consumes: `pipeline.analyzer._CRITICAL_FIELDS` (existing), `qa_audit.audit_record()` (existing, returns `{"grade": "HIGH"|"MEDIUM"|"LOW", ...}`).
- Produces: `eval_golden_set.FieldScore`, `eval_golden_set.CaseResult` (dataclass: `call_id: str`, `status: str`, `field_scores: list[FieldScore]`, `expected_qa_grade: str | None`, `actual_qa_grade: str | None`, `reason: str`, properties `accuracy_pct: float`, `regressed_from_high: bool`), `eval_golden_set.EvalReport` (dataclass: `cases: list[CaseResult]`, `aggregate_accuracy_pct: float`, `regressions: list[str]`, `passed: bool`, method `to_dict()`), `eval_golden_set.score_case(case: dict, actual: dict | None) -> CaseResult`, `eval_golden_set.build_eval_report(cases: list[CaseResult]) -> EvalReport`. Task 7 consumes all of these.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_eval_golden_set.py`:

```python
"""
Tests for eval_golden_set.py's scoring logic — score_case()/build_eval_report().
No dataset loading, no API calls, no golden_set.json dependency: all cases
are synthetic dicts constructed in-line.
"""

import pytest

from eval_golden_set import build_eval_report, score_case

# 6 of 7 expected fields matching, as a percentage — used by the two
# single-field-mismatch tests below (one categorical, one duration).
_SIX_OF_SEVEN_PCT = pytest.approx(100.0 * 6 / 7, rel=1e-6)


def _case(**expected_overrides) -> dict:
    expected = {
        "issue_1_category": "billing",
        "fcr_indicator": True,
        "escalation_required": False,
        "customer_sentiment_start": "negative",
        "customer_sentiment_end": "positive",
        "all_issues_resolved": True,
        "total_duration_seconds": 400,
    }
    expected.update(expected_overrides)
    return {"call_id": "c1", "expected": expected, "expected_qa_grade": "HIGH"}


class TestScoreCaseExactMatch:
    def test_all_fields_match_scores_100_pct(self):
        case = _case()
        actual = dict(case["expected"])
        result = score_case(case, actual)
        assert result.status == "scored"
        assert result.accuracy_pct == 100.0

    def test_one_categorical_mismatch_reduces_accuracy(self):
        case = _case()
        actual = dict(case["expected"])
        actual["issue_1_category"] = "technical"  # 1 of 7 fields wrong
        result = score_case(case, actual)
        assert result.accuracy_pct == _SIX_OF_SEVEN_PCT


class TestDurationTolerance:
    def test_within_15_pct_tolerance_passes(self):
        case = _case(total_duration_seconds=400)
        actual = dict(case["expected"])
        actual["total_duration_seconds"] = 460  # +15% exactly (boundary)
        result = score_case(case, actual)
        assert result.accuracy_pct == 100.0

    def test_beyond_15_pct_tolerance_fails(self):
        case = _case(total_duration_seconds=400)
        actual = dict(case["expected"])
        actual["total_duration_seconds"] = 461  # just over +15%
        result = score_case(case, actual)
        assert result.accuracy_pct == _SIX_OF_SEVEN_PCT


class TestFailedCase:
    def test_failed_extraction_scores_zero_not_excluded(self):
        case = _case()
        result = score_case(case, actual=None)
        assert result.status == "failed"
        assert result.accuracy_pct == 0.0


class TestQaGradeRegression:
    def test_regression_from_high_is_flagged(self):
        case = _case()
        actual = dict(case["expected"])
        result = score_case(case, actual)
        result.actual_qa_grade = "MEDIUM"  # simulate qa_audit grading a regression
        assert result.regressed_from_high is True

    def test_staying_high_is_not_a_regression(self):
        case = _case()
        actual = dict(case["expected"])
        result = score_case(case, actual)
        result.actual_qa_grade = "HIGH"
        assert result.regressed_from_high is False


class TestBuildEvalReport:
    def test_aggregate_accuracy_averages_across_cases(self):
        case_a = score_case(_case(), dict(_case()["expected"]))  # 100%
        case_b = score_case(_case(), actual=None)  # 0% (failed)
        report = build_eval_report([case_a, case_b])
        assert report.aggregate_accuracy_pct == 50.0

    def test_passed_true_above_threshold(self):
        case = score_case(_case(), dict(_case()["expected"]))
        report = build_eval_report([case])
        assert report.passed is True

    def test_passed_false_below_threshold(self):
        case = score_case(_case(), actual=None)
        report = build_eval_report([case])
        assert report.passed is False

    def test_regressions_lists_call_ids(self):
        case = score_case(_case(), dict(_case()["expected"]))
        case.actual_qa_grade = "LOW"
        report = build_eval_report([case])
        assert report.regressions == ["c1"]

    def test_to_dict_shape(self):
        case = score_case(_case(), dict(_case()["expected"]))
        report = build_eval_report([case])
        d = report.to_dict()
        assert "aggregate_accuracy_pct" in d
        assert d["cases"][0]["call_id"] == "c1"
        assert d["cases"][0]["fields"][0]["match"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_eval_golden_set.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval_golden_set'`

- [ ] **Step 3: Add config constants**

In `pipeline/config.py`, append after the `── Drift detection ──` section added in Task 1:

```python

# ── Eval harness (golden-set regression) ───────────────────────────────
# eval_golden_set.py — real-API-call regression check, run manually via
# `make eval-golden`, never in CI (see docs/superpowers/specs/
# 2026-09-25-drift-eval-design.md for why).
EVAL_PASS_THRESHOLD_PCT = 85.0  # minimum aggregate field-accuracy to pass
EVAL_DURATION_TOLERANCE_PCT = 0.15  # total_duration_seconds tolerance band
EVAL_DURATION_FIELD = "total_duration_seconds"
```

- [ ] **Step 4: Implement scoring logic in `eval_golden_set.py`**

```python
"""
eval_golden_set.py — Golden-Set Regression Eval for Extraction Quality
--------------------------------------------------------------------------
Re-runs extraction on a frozen set of real, previously-HIGH-QA-graded
transcripts (evals/golden_set.json) and diffs the fresh output against
the frozen expected values. Catches prompt/model/schema regressions that
the fast unit-test suite (tests/) cannot — those tests verify code
correctness, not model output quality.

NEVER run automatically: this makes real, billed LLM API calls (~$0.11
for the full golden set at current pricing). Run manually via
`make eval-golden`, always after confirming the cost with whoever's
paying for it.

Usage:
    .venv/bin/python eval_golden_set.py
    make eval-golden
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pipeline.analyzer import _CRITICAL_FIELDS as EXTRACTION_CRITICAL_FIELDS
from pipeline.config import (
    EVAL_DURATION_FIELD,
    EVAL_DURATION_TOLERANCE_PCT,
    EVAL_PASS_THRESHOLD_PCT,
)
from qa_audit import audit_record

GOLDEN_SET_PATH = Path("evals/golden_set.json")


@dataclass
class FieldScore:
    field: str
    expected: object
    actual: object
    match: bool


@dataclass
class CaseResult:
    call_id: str
    status: str  # "scored" | "failed"
    field_scores: list[FieldScore] = field(default_factory=list)
    expected_qa_grade: str | None = None
    actual_qa_grade: str | None = None
    reason: str = ""

    @property
    def accuracy_pct(self) -> float:
        if self.status == "failed" or not self.field_scores:
            return 0.0
        return 100.0 * sum(1 for f in self.field_scores if f.match) / len(self.field_scores)

    @property
    def regressed_from_high(self) -> bool:
        return (
            self.expected_qa_grade == "HIGH"
            and self.actual_qa_grade is not None
            and self.actual_qa_grade != "HIGH"
        )


@dataclass
class EvalReport:
    cases: list[CaseResult]
    aggregate_accuracy_pct: float
    regressions: list[str]
    passed: bool

    def to_dict(self) -> dict:
        return {
            "aggregate_accuracy_pct": round(self.aggregate_accuracy_pct, 2),
            "passed": self.passed,
            "regressions": self.regressions,
            "cases": [
                {
                    "call_id": c.call_id,
                    "status": c.status,
                    "accuracy_pct": round(c.accuracy_pct, 2),
                    "expected_qa_grade": c.expected_qa_grade,
                    "actual_qa_grade": c.actual_qa_grade,
                    "reason": c.reason,
                    "fields": [
                        {
                            "field": fs.field,
                            "expected": fs.expected,
                            "actual": fs.actual,
                            "match": fs.match,
                        }
                        for fs in c.field_scores
                    ],
                }
                for c in self.cases
            ],
        }


def _within_tolerance(expected, actual, tolerance_pct: float) -> bool:
    if actual is None or expected is None:
        return False
    if expected == 0:
        return actual == 0
    return abs(actual - expected) / abs(expected) <= tolerance_pct


def score_case(case: dict, actual: dict | None) -> CaseResult:
    """
    Compare one golden case's expected fields against a fresh extraction.
    `actual=None` means the extraction call failed for this case entirely
    (see run_eval() in Task 7) — scored as 0% across all fields, not
    silently excluded, so a flaky provider can't masquerade as "no
    regression found."
    """
    call_id = case["call_id"]
    if actual is None:
        return CaseResult(
            call_id=call_id,
            status="failed",
            expected_qa_grade=case.get("expected_qa_grade"),
            reason="Extraction call failed or returned no result",
        )

    scores = []
    for field_name, expected_value in case["expected"].items():
        actual_value = actual.get(field_name)
        if field_name == EVAL_DURATION_FIELD:
            match = _within_tolerance(expected_value, actual_value, EVAL_DURATION_TOLERANCE_PCT)
        else:
            match = actual_value == expected_value
        scores.append(
            FieldScore(field=field_name, expected=expected_value, actual=actual_value, match=match)
        )

    actual_qa_grade = audit_record({**actual, "call_id": call_id})["grade"]

    return CaseResult(
        call_id=call_id,
        status="scored",
        field_scores=scores,
        expected_qa_grade=case.get("expected_qa_grade"),
        actual_qa_grade=actual_qa_grade,
    )


def build_eval_report(cases: list[CaseResult]) -> EvalReport:
    aggregate = sum(c.accuracy_pct for c in cases) / len(cases) if cases else 0.0
    regressions = [c.call_id for c in cases if c.regressed_from_high]
    return EvalReport(
        cases=cases,
        aggregate_accuracy_pct=aggregate,
        regressions=regressions,
        passed=aggregate >= EVAL_PASS_THRESHOLD_PCT,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_eval_golden_set.py -v`
Expected: PASS — 11 tests

- [ ] **Step 6: Commit**

```bash
.venv/bin/ruff check eval_golden_set.py tests/test_eval_golden_set.py pipeline/config.py
.venv/bin/ruff format eval_golden_set.py tests/test_eval_golden_set.py pipeline/config.py
git add eval_golden_set.py tests/test_eval_golden_set.py pipeline/config.py
git commit -m "feat: add golden-set eval scoring logic (score_case/build_eval_report)"
```

---

### Task 6: `scripts/build_golden_set.py` — golden-set selection

**Files:**
- Create: `scripts/build_golden_set.py`
- Test: `tests/test_build_golden_set.py`

**Interfaces:**
- Consumes: `pipeline.analyzer._CRITICAL_FIELDS` (existing), `pipeline.hf_loader._build_transcripts` (existing — reused so the golden set's frozen transcript text matches exactly what the pipeline itself would build from the CSV, rather than a second, potentially-divergent reconstruction).
- Produces: `scripts/build_golden_set.select_golden_cases(records: list[dict], n: int = 15) -> list[dict]`, `scripts/build_golden_set.build_case(record: dict, transcript: dict) -> dict`. Not consumed by later tasks (this is a standalone tool); Task 7's `run_eval()` only reads the `evals/golden_set.json` file this script produces.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_build_golden_set.py`:

```python
"""
Tests for scripts/build_golden_set.py's selection logic. No CSV I/O, no
API calls — select_golden_cases() operates on plain dicts.
"""

from scripts.build_golden_set import build_case, select_golden_cases


def _record(call_id: str, category: str, qa_grade: str = "HIGH", dq_passed: bool = True) -> dict:
    return {
        "call_id": call_id,
        "issue_1_category": category,
        "fcr_indicator": True,
        "escalation_required": False,
        "customer_sentiment_start": "negative",
        "customer_sentiment_end": "positive",
        "all_issues_resolved": True,
        "total_duration_seconds": 400,
        "_qa_grade": qa_grade,
        "_dq_gate_passed": dq_passed,
    }


class TestSelectGoldenCases:
    def test_excludes_non_high_grade(self):
        records = [_record("c1", "billing", qa_grade="MEDIUM")]
        assert select_golden_cases(records, n=15) == []

    def test_excludes_failed_data_quality_gate(self):
        records = [_record("c1", "billing", dq_passed=False)]
        assert select_golden_cases(records, n=15) == []

    def test_includes_high_and_passed(self):
        records = [_record("c1", "billing")]
        selected = select_golden_cases(records, n=15)
        assert [r["call_id"] for r in selected] == ["c1"]

    def test_round_robins_across_categories(self):
        records = [
            _record("billing-1", "billing"),
            _record("billing-2", "billing"),
            _record("technical-1", "technical"),
        ]
        selected = select_golden_cases(records, n=2)
        categories = {r["issue_1_category"] for r in selected}
        # With n=2 and 2 distinct categories, round-robin must pick one
        # from each rather than two from "billing" (the larger bucket).
        assert categories == {"billing", "technical"}

    def test_null_category_treated_as_unknown_not_excluded(self):
        record = _record("c1", "billing")
        record["issue_1_category"] = None
        selected = select_golden_cases([record], n=15)
        assert len(selected) == 1

    def test_caps_at_n(self):
        records = [_record(f"c{i}", "billing") for i in range(20)]
        assert len(select_golden_cases(records, n=15)) == 15


class TestBuildCase:
    def test_case_shape(self):
        record = _record("c1", "billing")
        transcript = {"transcript_text": "hello", "call_date": "2026-01-01"}
        case = build_case(record, transcript)
        assert case["call_id"] == "c1"
        assert case["transcript_text"] == "hello"
        assert case["call_date"] == "2026-01-01"
        assert case["expected"]["issue_1_category"] == "billing"
        assert case["expected_qa_grade"] == "HIGH"
        assert "_qa_grade" not in case["expected"]  # only EXTRACTION_CRITICAL_FIELDS, no metadata leaks in
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_build_golden_set.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.build_golden_set'`

- [ ] **Step 3: Implement**

Create `scripts/__init__.py` (empty — makes `scripts` importable as a package for the test above):

```python
```

Create `scripts/build_golden_set.py`:

```python
"""
scripts/build_golden_set.py — one-time (or occasional) builder for
evals/golden_set.json.

Run manually when the golden set needs refreshing — e.g. after a
deliberate prompt/schema change where the old golden values are no
longer the right target. Never run automatically; this is a curation
tool, not part of any regular pipeline or CI step.

Usage:
    .venv/bin/python scripts/build_golden_set.py \\
        --source outputs/full_results_combined_20260809_175823.json \\
        --n 15
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from pipeline.analyzer import _CRITICAL_FIELDS as EXTRACTION_CRITICAL_FIELDS
from pipeline.config import LOCAL_CSV_PATH
from pipeline.hf_loader import _build_transcripts

OUTPUT_PATH = Path("evals/golden_set.json")


def select_golden_cases(records: list[dict], n: int = 15) -> list[dict]:
    """
    Pick up to `n` records that are HIGH-QA-graded and passed the Data
    Quality Gate, round-robin across distinct issue_1_category values so
    no single category dominates the set.

    `records` are full per-call dicts as written to
    outputs/full_results_*.json — each already carries `_qa_grade` and
    `_dq_gate_passed` (written by QualityAgent during the original run;
    see qa_audit.check_data_quality()).
    """
    eligible = [
        r for r in records if r.get("_qa_grade") == "HIGH" and r.get("_dq_gate_passed") is True
    ]

    by_category: dict[str, list[dict]] = {}
    for r in eligible:
        category = r.get("issue_1_category") or "unknown"
        by_category.setdefault(category, []).append(r)

    selected: list[dict] = []
    categories = list(by_category.keys())
    idx = 0
    while len(selected) < n and any(by_category.values()):
        cat = categories[idx % len(categories)]
        bucket = by_category[cat]
        if bucket:
            selected.append(bucket.pop(0))
        idx += 1

    return selected[:n]


def build_case(record: dict, transcript: dict) -> dict:
    """Convert one selected record + its rebuilt transcript into a golden_set.json case."""
    return {
        "call_id": record["call_id"],
        "transcript_text": transcript["transcript_text"],
        "call_date": transcript.get("call_date", ""),
        "expected": {f: record.get(f) for f in EXTRACTION_CRITICAL_FIELDS},
        "expected_qa_grade": record.get("_qa_grade", "HIGH"),
    }


def _load_transcripts_for_call_ids(call_ids: list[str]) -> dict[str, dict]:
    """
    Rebuild transcript_text for specific call_ids, using the exact same CSV
    parsing pipeline.hf_loader._load_from_csv uses — so the golden set's
    frozen transcript matches what the pipeline itself would produce, not a
    second, independently-written reconstruction that could subtly diverge.
    """
    df = pd.read_csv(
        LOCAL_CSV_PATH,
        dtype={"conversation_id": str, "speaker": str, "text": str},
    )
    df_sel = df[df["conversation_id"].isin(call_ids)].copy()
    df_sel["date_time"] = pd.to_datetime(df_sel["date_time"], format="mixed", errors="coerce")
    df_sel = df_sel.dropna(subset=["date_time"])
    df_sel = df_sel.sort_values(["conversation_id", "date_time"])
    transcripts = _build_transcripts(df_sel, call_ids)
    return {t["call_id"]: t for t in transcripts}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build evals/golden_set.json")
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="A past outputs/full_results*.json run to select HIGH-QA/DQ-passed cases from",
    )
    parser.add_argument("--n", type=int, default=15, help="Number of golden cases to select")
    parser.add_argument("--out", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    records = json.loads(args.source.read_text())
    selected = select_golden_cases(records, n=args.n)
    if len(selected) < args.n:
        print(
            f"⚠ Only found {len(selected)}/{args.n} eligible (HIGH-QA + DQ-gate-passed) "
            f"records in {args.source} — consider a larger/different --source"
        )

    call_ids = [r["call_id"] for r in selected]
    transcripts_by_id = _load_transcripts_for_call_ids(call_ids)

    cases = []
    for record in selected:
        transcript = transcripts_by_id.get(record["call_id"])
        if transcript is None:
            print(f"⚠ Skipping {record['call_id'][:12]} — transcript not found in {LOCAL_CSV_PATH}")
            continue
        cases.append(build_case(record, transcript))

    print(f"\nSelected {len(cases)} golden cases:")
    for c in cases:
        excerpt = c["transcript_text"][:80].replace("\n", " ")
        print(f"  {c['call_id'][:12]}  [{c['expected']['issue_1_category']}]  {excerpt}...")

    payload = {
        "frozen_from": str(args.source),
        "cases": cases,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2))
    print(f"\n✓ Wrote {len(cases)} cases → {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_build_golden_set.py -v`
Expected: PASS — 7 tests

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check scripts/build_golden_set.py tests/test_build_golden_set.py
.venv/bin/ruff format scripts/build_golden_set.py tests/test_build_golden_set.py
git add scripts/__init__.py scripts/build_golden_set.py tests/test_build_golden_set.py
git commit -m "feat: add scripts/build_golden_set.py for golden-set curation"
```

---

### Task 7: `eval_golden_set.py` — `run_eval()` end-to-end + `Makefile` targets

**Files:**
- Modify: `eval_golden_set.py` (append `run_eval()` + CLI)
- Modify: `Makefile` (add `eval-golden` target)
- Test: `tests/test_eval_golden_set.py` (extend, mocking `analyze_batch`)

**Interfaces:**
- Consumes: `pipeline.analyzer.analyze_batch(transcripts, inter_call_delay, checkpoint_key) -> list[dict]` (existing — each returned dict includes `call_id` since the LLM echoes it back per the extraction schema, confirmed in `prompts/system_prompt.txt`); `score_case`, `build_eval_report` (Task 5).
- Produces: `eval_golden_set.run_eval(golden_set_path: Path) -> EvalReport`; `make eval-golden` CLI entry point. Nothing downstream consumes this (terminal task for the eval harness).

- [ ] **Step 1: Write the failing test**

In `tests/test_eval_golden_set.py`, add:

```python
from unittest.mock import patch

from eval_golden_set import run_eval


class TestRunEval:
    def test_matches_results_back_by_call_id(self, tmp_path):
        golden_path = tmp_path / "golden_set.json"
        golden_path.write_text(
            json.dumps(
                {
                    "cases": [
                        {
                            "call_id": "c1",
                            "transcript_text": "hello",
                            "call_date": "2026-01-01",
                            "expected": {"issue_1_category": "billing"},
                            "expected_qa_grade": "HIGH",
                        },
                        {
                            "call_id": "c2",
                            "transcript_text": "hi",
                            "call_date": "2026-01-01",
                            "expected": {"issue_1_category": "technical"},
                            "expected_qa_grade": "HIGH",
                        },
                    ]
                }
            )
        )
        # analyze_batch returns only c1 — c2's call "failed" and was dropped,
        # exactly as pipeline.analyzer.analyze_batch already behaves for a
        # permanent per-call failure.
        with patch(
            "eval_golden_set.analyze_batch",
            return_value=[{"call_id": "c1", "issue_1_category": "billing"}],
        ):
            report = run_eval(golden_path)

        by_id = {c.call_id: c for c in report.cases}
        assert by_id["c1"].status == "scored"
        assert by_id["c1"].accuracy_pct == 100.0
        assert by_id["c2"].status == "failed"
```

Add the necessary `import json` at the top of `tests/test_eval_golden_set.py` if not already present (it is, from Task 5's `to_dict` test — confirm and skip if so).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_eval_golden_set.py -k test_matches_results_back_by_call_id -v`
Expected: FAIL — `ImportError: cannot import name 'run_eval'`

- [ ] **Step 3: Implement**

Append to `eval_golden_set.py` (after `build_eval_report`):

```python
from pipeline.analyzer import analyze_batch


def run_eval(golden_set_path: Path = GOLDEN_SET_PATH) -> EvalReport:
    golden = json.loads(golden_set_path.read_text())
    cases_data = golden["cases"]

    transcripts = [
        {
            "call_id": c["call_id"],
            "call_date": c["call_date"],
            "transcript_text": c["transcript_text"],
        }
        for c in cases_data
    ]
    actual_results = analyze_batch(transcripts, inter_call_delay=2.0)
    actual_by_id = {r["call_id"]: r for r in actual_results if r.get("call_id")}

    cases = [score_case(c, actual_by_id.get(c["call_id"])) for c in cases_data]
    return build_eval_report(cases)


def _print_report(report: EvalReport) -> None:
    print(f"\n{'Call ID':<14} {'Status':<8} {'Accuracy':>9}  QA grade (expected → actual)")
    print("-" * 60)
    for c in report.cases:
        grade_note = f"{c.expected_qa_grade} → {c.actual_qa_grade}" if c.status == "scored" else "-"
        print(f"{c.call_id[:12]:<14} {c.status:<8} {c.accuracy_pct:>8.1f}%  {grade_note}")

    print("-" * 60)
    print(f"Aggregate accuracy: {report.aggregate_accuracy_pct:.1f}%")
    print(f"Threshold:          {EVAL_PASS_THRESHOLD_PCT}%")
    print(f"Verdict:            {'PASS' if report.passed else 'FAIL'}")
    if report.regressions:
        print(f"HIGH→lower regressions: {', '.join(c[:12] for c in report.regressions)}")


def main() -> None:
    report = run_eval()
    _print_report(report)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path("outputs") / f"eval_report_{ts}.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(report.to_dict(), indent=2))
    print(f"\n✓ Report written → {out_path}")

    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
```

Move the `import sys` already at the top of the file's existing imports (Task 5 already added it) — no change needed there, just confirm it's present.

In `Makefile`, add after the `security-scan` target:

```makefile
# Real-API-call regression check against evals/golden_set.json — ~$0.11
# per run at current pricing. NEVER wired into CI or `make check`; run
# manually, and always confirm the cost with whoever's paying first.
eval-golden:
	$(PYTHON) eval_golden_set.py

# Rebuild evals/golden_set.json from a past run's verified-good output.
# Usage: make build-golden-set SOURCE=outputs/full_results_combined_20260809_175823.json
build-golden-set:
	$(PYTHON) scripts/build_golden_set.py --source $(SOURCE)
```

Add both to the `help` target's listing and the `.PHONY` line:

```makefile
.PHONY: help install install-dev lock test test-fast test-cov lint format \
        type-check check run run-batches dashboard demo clean clean-outputs \
        eval-golden build-golden-set
```

```
	@echo "  eval-golden     Run the golden-set extraction-accuracy eval (~\$$0.11, real API calls)"
	@echo "  build-golden-set  Rebuild evals/golden_set.json (SOURCE=<path>)"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_eval_golden_set.py -v`
Expected: PASS — 12 tests

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check eval_golden_set.py tests/test_eval_golden_set.py
.venv/bin/ruff format eval_golden_set.py tests/test_eval_golden_set.py
git add eval_golden_set.py tests/test_eval_golden_set.py Makefile
git commit -m "feat: add run_eval() end-to-end wiring and make eval-golden target"
```

---

### Task 8: Docs sync — CLAUDE.md, engineering-standards, CHANGELOG, version, test counts

**Files:**
- Modify: `CLAUDE.md` (key files list, development commands)
- Modify: `docs/engineering-standards.md` (drift/eval now real)
- Modify: `scripts/check_docs_sync.py` (catch the `pipeline_version` manifest literal too)
- Modify: `CHANGELOG.md` (new entry), `pyproject.toml` (version bump)
- Modify: `README.md`, `CONTRIBUTING.md` (test-count sync — exact number depends on final count from Steps 1-7)

**Interfaces:** None — this task only touches docs/config, no code interfaces.

- [ ] **Step 1: Get the final test count**

Run: `.venv/bin/python -m pytest tests/ -m "not slow and not integration" --collect-only -q`

Note the printed count (will be 464 + the new tests from Tasks 1-7: 9 + 2 + 6 + 1 + 2 + 11 + 7 + 1 = 39 new tests → expect 503, but **use whatever number the command actually prints**, not this arithmetic — a step or fixture count may differ slightly from this estimate).

- [ ] **Step 2: Extend `scripts/check_docs_sync.py` to catch the manifest version literal**

In `scripts/check_docs_sync.py`, add a new check function:

```python
def check_export_agent_version_sync(pyproject_version: str) -> list[str]:
    """pipeline/agents/export_agent.py hardcodes 'pipeline_version' into
    run_manifest_*.json — was already stale once (found during the
    2026-09-25 drift/eval audit) before check_docs_sync.py could catch it."""
    errors = []
    path = ROOT / "pipeline" / "agents" / "export_agent.py"
    text = path.read_text()
    m = re.search(r'"pipeline_version":\s*"([^"]+)"', text)
    if not m:
        return [f"{path}: could not find a `\"pipeline_version\": \"...\"` line"]
    if m.group(1) != pyproject_version:
        errors.append(
            f"pipeline/agents/export_agent.py: pipeline_version literal is "
            f"{m.group(1)!r}, but pyproject.toml is {pyproject_version!r}"
        )
    return errors
```

In `main()`, add the call:

```python
    errors += check_export_agent_version_sync(pyproject_version)
```

- [ ] **Step 3: Update `CLAUDE.md`**

Add to the "Key files" list (after `pipeline/circuit_breaker.py`'s line):

```
- `pipeline/drift.py` — `DriftGuard`, cross-run KPI drift detection against `AgentMemory`'s history; wired into `ExportAgent`, detection/reporting only
```

Add to "Development Commands":

```
make eval-golden     # golden-set extraction-accuracy eval (~$0.11, real API calls — never run without confirming cost first)
```

- [ ] **Step 4: Update `docs/engineering-standards.md`**

In the "Known gaps" section, remove the line about drift/evals not existing (it's no longer a gap — it shipped). Add a new row to whatever quality/testing table exists, noting `pipeline/drift.py` and `eval_golden_set.py` alongside their test files, matching the existing table format in that document.

- [ ] **Step 5: Bump version and add CHANGELOG entry**

In `pyproject.toml`, bump `version = "4.7.0"` → `version = "4.8.0"` (new feature addition, not a patch).

Add a new top entry to `CHANGELOG.md`:

```markdown
## [4.8.0] — 2026-09-25

### Added — Drift detection + golden-set eval harness

Closes a gap found during the 2026-09-25 engineering-standards/portfolio
audit: the project's documentation implied "drift detection" and "evals"
were enforced capabilities; neither existed. Full design:
`docs/superpowers/specs/2026-09-25-drift-eval-design.md`.

- **`pipeline/drift.py`** — `DriftGuard` compares each run's KPIs
  (`fcr_rate_pct`, `aht_minutes`, `qa_avg_score`, `data_quality_pass_rate_pct`)
  against a rolling mean/stdev baseline built from `AgentMemory`'s existing
  run history. A metric drifts only if it clears `max(2σ, 10% relative)` —
  deliberately biased toward few false alarms given ~20 historical runs.
  Wired into `ExportAgent`, before the current run is recorded into its own
  baseline. Detection/reporting only — never blocks export.
- **`eval_golden_set.py`** + **`evals/golden_set.json`** — a 15-case
  golden-set regression eval. Ground truth is frozen from a past run that
  scored HIGH QA + passed the Data Quality Gate (not hand-labeled), built
  via `scripts/build_golden_set.py`. Diffs a fresh extraction against the
  frozen expected values (exact match for categorical/boolean fields, ±15%
  tolerance for duration). `make eval-golden` — real API calls (~$0.11),
  never wired into CI.
- `pipeline/memory.py::record_run()` now persists `data_quality_pass_rate_pct`
  (previously computed but not carried into `AgentMemory`).
- Fixed a second, independent instance of the version-drift pattern this
  changelog already flagged twice before: `export_agent.py`'s hardcoded
  `"pipeline_version": "4.5.0"` manifest literal had gone stale after the
  4.7.0 bump. `scripts/check_docs_sync.py` now checks this literal too.

Net: +N tests (NNN → MMM) — *(fill in the exact before/after counts from
Step 1 before committing this entry)*.
```

**Before committing:** replace the two placeholder numbers in the "Net:" line with the real before (464) and after (from Step 1) counts — this is the one spot in this task where a placeholder is temporarily acceptable mid-task, but it must not survive to the commit.

- [ ] **Step 6: Sync test counts in README.md and CONTRIBUTING.md**

Using the count from Step 1, update every occurrence (mirroring the pattern already established for the 399→464 sync in the previous engineering-standards session):

```bash
# Replace <N> with the actual count from Step 1
sed -i '' "s/Tests-464%20passing/Tests-<N>%20passing/" README.md
sed -i '' "s/\*\*464 unit tests\*\*/**<N> unit tests**/" README.md
sed -i '' "s/464 tests · < 7 seconds/<N> tests · < 7 seconds/" README.md
sed -i '' "s/464 unit tests — no API calls required/<N> unit tests — no API calls required/" README.md
sed -i '' "s/464 unit tests (zero API calls/<N> unit tests (zero API calls/" README.md
sed -i '' "s/464 unit tests — should all pass/<N> unit tests — should all pass/" CONTRIBUTING.md
```

Also update the `v4.7` banners in `README.md`/`ARCHITECTURE.md` to `v4.8`:

```bash
sed -i '' 's/Multi-Agent Pipeline v4\.7/Multi-Agent Pipeline v4.8/' README.md ARCHITECTURE.md
sed -i '' 's/Technical Architecture v4\.7/Technical Architecture v4.8/' ARCHITECTURE.md
sed -i '' 's/complete ownership of a v4\.7 agentic AI system/complete ownership of a v4.8 agentic AI system/' README.md
```

**Also bump the `pipeline_version` literal Task 3 set** — Task 3 correctly set it to `"4.7.0"` (the actual version at that point in the plan), but Step 5 above just bumped `pyproject.toml` to `4.8.0`, and Step 2's new `check_export_agent_version_sync` check will fail on the mismatch if this isn't updated too:

```bash
sed -i '' 's/"pipeline_version": "4.7.0"/"pipeline_version": "4.8.0"/' pipeline/agents/export_agent.py
```

- [ ] **Step 7: Verify everything is consistent**

Run, in order:

```bash
.venv/bin/python scripts/check_docs_sync.py
.venv/bin/python -m pytest tests/ -m "not slow and not integration" --cov=pipeline --cov-report=term-missing --cov-fail-under=85 -q
.venv/bin/mypy pipeline/ --ignore-missing-imports
.venv/bin/ruff check pipeline/ tests/ api/ run_pipeline.py run_batches.py merge_outputs.py qa_audit.py dashboard/ scripts/ eval_golden_set.py
make check
```

Expected: all green — `check_docs_sync: OK`, coverage ≥85%, mypy clean, ruff clean, `make check` passes.

- [ ] **Step 8: Commit**

```bash
git add CLAUDE.md docs/engineering-standards.md scripts/check_docs_sync.py \
        CHANGELOG.md pyproject.toml README.md CONTRIBUTING.md ARCHITECTURE.md \
        pipeline/agents/export_agent.py
git commit -m "docs: sync version/test-count/docs for 4.8.0 drift+eval release"
```

---

## Self-Review Notes

**Spec coverage:** Every section of `docs/superpowers/specs/2026-09-25-drift-eval-design.md` maps to a task — §1 (eval harness) → Tasks 5-7, §2 (drift check) → Tasks 1-4, testing summary → each task's own test file, "Handoff" → out of scope for this plan (correctly excluded).

**Deviation from the spec, found during grounding (documented, not hidden):** the spec's §1.2 pseudocode showed a per-case `try/except` loop calling `analyze_transcript()` directly. While grounding this plan in the real code, `pipeline.analyzer.analyze_batch()` was found to already provide exactly this orchestration (client construction, rate limiting, per-call failure handling) — reusing it in Task 7 instead of reimplementing it is a straightforward win, not a scope change: the spec's intent ("diff frozen expected vs. fresh actual, count failures in the denominator") is preserved exactly, `analyze_batch`'s silent-drop-on-failure behavior naturally produces the "failed case" path Task 5 already scores as 0%.

**Type consistency check:** `DriftReport.to_dict()`'s keys (`sufficient_history`, `any_drifted`, `baseline_run_count`, `metrics`) are used identically in Task 3's export_agent.py, Task 4's graph.py banner, and Task 3's tests — confirmed consistent. `EvalReport`/`CaseResult`/`FieldScore` field names are used identically across Tasks 5 and 7. Renamed the eval script's aggregate function to `build_eval_report` (not `build_report`) specifically to avoid colliding with `qa_audit.build_report`, which Task 5 imports from indirectly via `audit_record`.

**No placeholders** except the two explicitly-flagged, explicitly-must-be-filled-before-commit numbers in Task 8 Step 5's CHANGELOG entry (the before/after test counts, which are only knowable once Tasks 1-7 are actually built) — this is a documented exception, not an oversight.
