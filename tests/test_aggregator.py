"""
Tests for pipeline/aggregator.py — KPI computation, distributions, and
cost-lever estimates from per-call extraction results.
All pure unit tests: no API calls, no filesystem access.
"""

import pandas as pd
import pytest

from pipeline.aggregator import (
    COST_PER_CALL_USD,
    _avg,
    _issue_category_counts,
    _pct,
    _val_pct,
    aggregate_metrics,
)
from pipeline.config import EXTRACTION_MODEL

# ── Helpers ───────────────────────────────────────────────────────────

class TestHelpers:
    def test_pct_basic(self):
        df = pd.DataFrame({"flag": [True, True, False, None]})
        assert _pct(df, "flag") == 50.0

    def test_pct_missing_column(self):
        assert _pct(pd.DataFrame({"x": [1]}), "absent") == 0.0

    def test_pct_empty_frame(self):
        assert _pct(pd.DataFrame(), "flag") == 0.0

    def test_avg_ignores_nulls(self):
        df = pd.DataFrame({"v": [10, 20, None]})
        assert _avg(df, "v") == 15.0

    def test_avg_missing_column(self):
        assert _avg(pd.DataFrame({"x": [1]}), "absent") == 0.0

    def test_val_pct_descending_percentages(self):
        df = pd.DataFrame({"c": ["a", "a", "a", "b"]})
        result = _val_pct(df, "c")
        assert result == {"a": 75.0, "b": 25.0}
        assert list(result.keys())[0] == "a"

    def test_issue_category_counts_spans_issue_slots(self):
        df = pd.DataFrame([
            {"issue_1_category": "billing", "issue_2_category": "technical"},
            {"issue_1_category": "billing", "issue_2_category": None},
            {"issue_1_category": "null"},  # string nulls must be ignored
        ])
        counts = _issue_category_counts(df)
        assert counts == {"billing": 2, "technical": 1}


# ── aggregate_metrics ─────────────────────────────────────────────────

@pytest.fixture
def results(make_record):
    return [
        make_record(call_id="c1", fcr_indicator=True, total_issues_count=2,
                    upsell_attempted=True, upsell_outcome="accepted"),
        make_record(call_id="c2", fcr_indicator=True,
                    upsell_attempted=True, upsell_outcome="declined"),
        make_record(call_id="c3", fcr_indicator=False, escalation_required=True),
        make_record(call_id="c4", fcr_indicator=False, avoidable_call=True,
                    could_be_self_served=True, self_serve_channel_applicable="app"),
    ]


class TestAggregateMetrics:
    def test_empty_results_raises(self):
        with pytest.raises(ValueError, match="No results"):
            aggregate_metrics([])

    def test_top_level_structure(self, results):
        m = aggregate_metrics(results)
        assert set(m) == {"meta", "kpis", "phase_avg_seconds", "distributions",
                          "cost_levers", "token_usage"}
        assert m["meta"]["total_calls_analyzed"] == 4
        assert m["meta"]["model"] == EXTRACTION_MODEL

    def test_rate_kpis(self, results):
        kpis = aggregate_metrics(results)["kpis"]
        assert kpis["fcr_rate_pct"] == 50.0
        assert kpis["escalation_rate_pct"] == 25.0
        assert kpis["avoidable_call_rate_pct"] == 25.0
        assert kpis["multi_issue_call_pct"] == 25.0  # only c1 has >1 issue

    def test_upsell_conversion_uses_attempted_denominator(self, results):
        kpis = aggregate_metrics(results)["kpis"]
        assert kpis["upsell_attempted_pct"] == 50.0
        # 1 accepted of 2 attempted — not of 4 total
        assert kpis["upsell_conversion_pct"] == 50.0

    def test_upsell_conversion_zero_when_never_attempted(self, make_record):
        m = aggregate_metrics([make_record(upsell_attempted=False)])
        assert m["kpis"]["upsell_conversion_pct"] == 0.0

    def test_handle_time_kpis(self, results):
        kpis = aggregate_metrics(results)["kpis"]
        assert kpis["avg_handle_time_seconds"] == 420.0
        assert kpis["avg_handle_time_minutes"] == 7.0

    def test_phase_averages_keyed_by_label(self, results):
        phases = aggregate_metrics(results)["phase_avg_seconds"]
        assert phases["Welcome & Auth"] == 30.0
        assert phases["Hold"] == 0.0
        assert len(phases) == 7

    def test_distributions(self, results):
        dist = aggregate_metrics(results)["distributions"]
        assert dist["issue_category"]["billing"] == 4
        assert dist["agent_skill"] == {"proficient": 100.0}
        assert dist["repeat_call_risk"] == {"low": 100.0}

    def test_cost_levers_arithmetic(self, results):
        levers = aggregate_metrics(results)["cost_levers"]
        baseline = levers["monthly_volume_estimate"] * COST_PER_CALL_USD
        assert levers["baseline_monthly_cost_usd"] == round(baseline)
        expected_total = (
            levers["self_serve_savings_usd"]
            + levers["agentic_ai_savings_usd"]
            + levers["proactive_care_savings_usd"]
        )
        # Components are rounded independently — allow ±2 of rounding drift
        assert abs(levers["total_savings_opportunity_usd"] - expected_total) <= 2
        assert 0 <= levers["savings_pct_of_baseline"] <= 100

    def test_token_usage_embedded(self, results):
        usage = aggregate_metrics(results)["token_usage"]
        assert usage["total_prompt_tokens"] == 4 * 2000
        assert usage["calls_with_usage"] == 4
