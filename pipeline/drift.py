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
