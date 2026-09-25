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
        report = DriftGuard().check(current={"fcr_rate_pct": 70.0}, history=_history(3))
        assert report.sufficient_history is False
        assert report.baseline_run_count == 3
        assert report.metrics == []
        assert report.any_drifted is False


class TestStdevZeroBaseline:
    def test_small_move_within_pct_floor_is_not_drift(self):
        # Identical baseline (stdev=0); a move smaller than the 10% floor
        # must not fire just because it's "infinitely many standard
        # deviations" away from a zero-variance baseline.
        report = DriftGuard().check(current={"fcr_rate_pct": 72.0}, history=_history(10))
        metric = next(m for m in report.metrics if m.metric == "fcr_rate_pct")
        assert metric.drifted is False
        assert metric.z_score is None
        assert metric.baseline_stdev == 0.0

    def test_large_move_beyond_pct_floor_is_drift(self):
        report = DriftGuard().check(current={"fcr_rate_pct": 90.0}, history=_history(10))
        metric = next(m for m in report.metrics if m.metric == "fcr_rate_pct")
        assert metric.drifted is True
        assert metric.z_score is None


class TestNoisyBaseline:
    NOISY = [
        {
            "fcr_rate_pct": v,
            "aht_minutes": 7.0,
            "qa_avg_score": 88.0,
            "data_quality_pass_rate_pct": 95.0,
        }
        for v in [60.0, 62.0, 64.0, 66.0, 68.0, 70.0, 72.0, 74.0, 76.0, 78.0, 80.0]
    ]
    # mean=70.0, variance=40.0, stdev=6.3245553203367585

    def test_move_exceeding_naive_pct_but_within_z_bound_is_not_drift(self):
        # deviation=9 -> pct_dev=12.9% (would fire on a naive 10% check
        # alone) but z=1.42 (<2) and combined threshold=max(2*6.32, 7.0)=12.65
        report = DriftGuard().check(current={"fcr_rate_pct": 79.0}, history=self.NOISY)
        metric = next(m for m in report.metrics if m.metric == "fcr_rate_pct")
        assert metric.drifted is False
        assert metric.z_score == pytest.approx(1.4230, rel=1e-3)

    def test_move_exceeding_z_bound_is_drift(self):
        # deviation=15 -> threshold=12.65 -> drifted
        report = DriftGuard().check(current={"fcr_rate_pct": 85.0}, history=self.NOISY)
        metric = next(m for m in report.metrics if m.metric == "fcr_rate_pct")
        assert metric.drifted is True
        assert metric.z_score == pytest.approx(2.3717, rel=1e-3)


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
            {
                "fcr_rate_pct": 70.0,
                "aht_minutes": 7.0,
                "qa_avg_score": 88.0,
                "data_quality_pass_rate_pct": 95.0,
            }
        )  # only 1/10 has it -> below the 80% presence floor
        current = {
            "fcr_rate_pct": 70.0,
            "aht_minutes": 7.0,
            "qa_avg_score": 88.0,
            "data_quality_pass_rate_pct": 95.0,
        }
        report = DriftGuard().check(current=current, history=history)
        names = {m.metric for m in report.metrics}
        assert "data_quality_pass_rate_pct" not in names
        assert names == {"fcr_rate_pct", "aht_minutes", "qa_avg_score"}


class TestReportSerialization:
    def test_to_dict_shape(self):
        report = DriftGuard().check(current={"fcr_rate_pct": 90.0}, history=_history(10))
        d = report.to_dict()
        assert d["baseline_run_count"] == 10
        assert d["sufficient_history"] is True
        assert d["any_drifted"] is True
        assert d["metrics"][0]["metric"] == "fcr_rate_pct"
        assert d["metrics"][0]["drifted"] is True
