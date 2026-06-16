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
    _category_resolution_breakdown,
    _issue_category_counts,
    _pct,
    _phase_pnl,
    _segment_masks,
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


@pytest.fixture
def segmentation_results(make_record):
    """
    5 calls covering every branch of _resolution_segments(), including
    overlap between the three independent flags:
      s1 — proactive=True + self_serve=True + agentic=True -> PREVENT wins
      s2 — self_serve=True only                            -> AUTOMATE/self-serve
      s3 — agentic=True only                               -> AUTOMATE/agentic
      s4 — self_serve=True + agentic=True (no proactive)   -> AUTOMATE/self-serve wins
      s5 — none of the three flags                         -> HUMAN_REQUIRED
    """
    return [
        make_record(call_id="s1", proactive_outreach_applicable=True,
                     could_be_self_served=True, agentic_ai_resolvable=True),
        make_record(call_id="s2", proactive_outreach_applicable=False,
                     could_be_self_served=True, agentic_ai_resolvable=False),
        make_record(call_id="s3", proactive_outreach_applicable=False,
                     could_be_self_served=False, agentic_ai_resolvable=True),
        make_record(call_id="s4", proactive_outreach_applicable=False,
                     could_be_self_served=True, agentic_ai_resolvable=True),
        make_record(call_id="s5", proactive_outreach_applicable=False,
                     could_be_self_served=False, agentic_ai_resolvable=False),
    ]


class TestAggregateMetrics:
    def test_empty_results_raises(self):
        with pytest.raises(ValueError, match="No results"):
            aggregate_metrics([])

    def test_top_level_structure(self, results):
        m = aggregate_metrics(results)
        assert set(m) == {"meta", "kpis", "phase_avg_seconds", "phase_drilldown",
                          "distributions", "cost_levers", "issue_breakdown", "token_usage"}
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


# ── Resolution segmentation (prevent / automate / human-required) ──────

class TestResolutionSegments:
    def test_segments_sum_to_100(self, segmentation_results):
        kpis = aggregate_metrics(segmentation_results)["kpis"]
        total = (
            kpis["prevent_pct"] + kpis["automate_pct"] + kpis["human_required_pct"]
        )
        assert total == 100.0

    def test_priority_ordering(self, segmentation_results):
        """s1 qualifies for both PREVENT and AUTOMATE — PREVENT wins."""
        kpis = aggregate_metrics(segmentation_results)["kpis"]
        # Only s1 is proactive -> 1/5 = 20%
        assert kpis["prevent_pct"] == 20.0
        # s2, s3, s4 -> 3/5 = 60% (s1 excluded despite also qualifying)
        assert kpis["automate_pct"] == 60.0
        # s5 only -> 1/5 = 20%
        assert kpis["human_required_pct"] == 20.0

    def test_automate_subsplit_self_serve_priority(self, segmentation_results):
        """s4 qualifies for both self-serve and agentic — self-serve wins."""
        kpis = aggregate_metrics(segmentation_results)["kpis"]
        # s2, s4 -> 2/5 = 40%
        assert kpis["automate_self_serve_pct"] == 40.0
        # s3 only -> 1/5 = 20%
        assert kpis["automate_agentic_pct"] == 20.0
        assert (
            kpis["automate_self_serve_pct"] + kpis["automate_agentic_pct"]
            == kpis["automate_pct"]
        )

    def test_cost_levers_derive_from_segments_not_marginals(self, segmentation_results):
        levers = aggregate_metrics(segmentation_results)["cost_levers"]
        baseline = levers["monthly_volume_estimate"] * COST_PER_CALL_USD
        # 40% self-serve * 0.85 + 20% agentic * 0.70 + 20% prevent * 0.60
        assert levers["self_serve_savings_usd"]     == round(baseline * 0.40 * 0.85)
        assert levers["agentic_ai_savings_usd"]      == round(baseline * 0.20 * 0.70)
        assert levers["proactive_care_savings_usd"]  == round(baseline * 0.20 * 0.60)
        assert levers["savings_pct_of_baseline"] == 60.0

    def test_all_human_required_when_no_flags_set(self, make_record):
        results = [make_record(
            call_id="h1",
            could_be_self_served=False,
            agentic_ai_resolvable=False,
            proactive_outreach_applicable=False,
        )]
        kpis = aggregate_metrics(results)["kpis"]
        assert kpis["human_required_pct"] == 100.0
        assert kpis["prevent_pct"] == 0.0
        assert kpis["automate_pct"] == 0.0


# ── Phase economics (Cost to Serve/Sell/Retain + Phase Drill-Down) ──────

class TestPhasePnl:
    def test_pure_serve_call(self):
        phase_avg = {
            "Welcome & Auth": 10, "Discovery": 20, "Diagnosis": 30, "Resolution": 40,
            "Hold": 0, "Upsell": 0, "Closing": 0,
        }
        pnl = _phase_pnl(phase_avg, baseline_monthly_cost=600_000)
        assert pnl["serve_time_pct"] == 100.0
        assert pnl["sell_time_pct"] == 0.0
        assert pnl["retain_time_pct"] == 0.0
        assert pnl["serve_cost_usd"] == 600_000
        assert pnl["sell_cost_usd"] == 0
        assert pnl["retain_cost_usd"] == 0

    def test_mixed_phases_split_correctly(self):
        # serve=80, sell=10, retain=10 (of 100 total)
        phase_avg = {
            "Welcome & Auth": 10, "Discovery": 20, "Diagnosis": 20, "Resolution": 30,
            "Hold": 5, "Closing": 5, "Upsell": 10,
        }
        pnl = _phase_pnl(phase_avg, baseline_monthly_cost=600_000)
        assert pnl["serve_time_pct"] == 80.0
        assert pnl["sell_time_pct"] == 10.0
        assert pnl["retain_time_pct"] == 10.0
        assert pnl["serve_cost_usd"] == 480_000
        assert pnl["sell_cost_usd"] == 60_000
        assert pnl["retain_cost_usd"] == 60_000

    def test_via_aggregate_metrics_sums_to_baseline(self, results):
        m = aggregate_metrics(results)
        cl = m["cost_levers"]
        total = cl["serve_cost_usd"] + cl["sell_cost_usd"] + cl["retain_cost_usd"]
        # Components rounded independently — allow ±2 of rounding drift
        assert abs(total - cl["baseline_monthly_cost_usd"]) <= 2


class TestPhaseDrilldown:
    @pytest.fixture
    def drilldown_results(self, make_record):
        return [
            make_record(call_id="d1", issue_1_category="billing",
                        phase_discovery_duration_seconds=100,
                        agent_disproportionate_time_phase="discovery"),
            make_record(call_id="d2", issue_1_category="billing",
                        phase_discovery_duration_seconds=50,
                        agent_disproportionate_time_phase="diagnosis"),
            make_record(call_id="d3", issue_1_category="technical",
                        phase_discovery_duration_seconds=200,
                        agent_disproportionate_time_phase="discovery"),
        ]

    def test_ranks_intents_by_avg_phase_duration(self, drilldown_results):
        rows = aggregate_metrics(drilldown_results)["phase_drilldown"]["Discovery"]
        # technical (200s, n=1) ranks above billing (avg 75s, n=2)
        assert rows[0]["intent"] == "technical"
        assert rows[0]["avg_seconds"] == 200.0
        assert rows[0]["calls"] == 1
        assert rows[1]["intent"] == "billing"
        assert rows[1]["avg_seconds"] == 75.0
        assert rows[1]["calls"] == 2

    def test_stall_pct_reflects_disproportionate_phase(self, drilldown_results):
        rows = aggregate_metrics(drilldown_results)["phase_drilldown"]["Discovery"]
        billing = next(r for r in rows if r["intent"] == "billing")
        technical = next(r for r in rows if r["intent"] == "technical")
        # 1 of 2 billing calls flagged "discovery" as the disproportionate phase
        assert billing["stall_pct"] == 50.0
        # the single technical call is flagged "discovery"
        assert technical["stall_pct"] == 100.0

    def test_all_drilldown_phases_present(self, results):
        dd = aggregate_metrics(results)["phase_drilldown"]
        assert set(dd) == {"Discovery", "Diagnosis", "Resolution", "Upsell"}

    def test_empty_results_returns_empty_lists(self, make_record):
        dd = aggregate_metrics([make_record(issue_1_category="null")])["phase_drilldown"]
        for phase_rows in dd.values():
            assert phase_rows == []


# ── Issue-tree breakdown (Section 6: category x segment x method) ──────

class TestSegmentMasks:
    def test_masks_partition_every_call_exactly_once(self, segmentation_results):
        df = pd.DataFrame(segmentation_results)
        masks = _segment_masks(df)
        combined = (
            masks["prevent"] | masks["automate_self_serve"]
            | masks["automate_agentic"] | masks["human"]
        )
        assert combined.all()
        assert sum(int(m.sum()) for m in masks.values()) == len(df)


@pytest.fixture
def breakdown_results(make_record):
    """
    20 calls across 3 issue categories, sized so percentages and $ amounts
    (baseline = 100_000 * $6.00 = 600_000) come out exact:

      billing (10):  4 prevent, 3 automate/self-serve, 2 automate/agentic, 1 human
      technical (6): 1 prevent, 2 automate/agentic, 3 human
      device (4):    4 automate/self-serve
    """
    flags = {
        "prevent": dict(proactive_outreach_applicable=True,
                        could_be_self_served=False, agentic_ai_resolvable=False),
        "automate_self_serve": dict(proactive_outreach_applicable=False,
                                     could_be_self_served=True, agentic_ai_resolvable=False),
        "automate_agentic": dict(proactive_outreach_applicable=False,
                                  could_be_self_served=False, agentic_ai_resolvable=True),
        "human": dict(proactive_outreach_applicable=False,
                      could_be_self_served=False, agentic_ai_resolvable=False),
    }

    def seg(category, n, segment, method):
        return [
            make_record(call_id=f"{category}-{segment}-{i}", issue_1_category=category,
                        issue_1_resolution_method=method, **flags[segment])
            for i in range(n)
        ]

    records = []
    records += seg("billing", 3, "prevent", "agent_action")
    records += seg("billing", 1, "prevent", "escalated")
    records += seg("billing", 3, "automate_self_serve", "self_serve_guidance")
    records += seg("billing", 2, "automate_agentic", "agent_action")
    records += seg("billing", 1, "human", "unresolved")

    records += seg("technical", 1, "prevent", "agent_action")
    records += seg("technical", 2, "automate_agentic", "agent_action")
    records += seg("technical", 2, "human", "escalated")
    records += seg("technical", 1, "human", "workaround")

    records += seg("device", 4, "automate_self_serve", "self_serve_guidance")

    return records


class TestCategoryResolutionBreakdown:
    def test_empty_without_issue_category(self, make_record):
        breakdown = aggregate_metrics([make_record(issue_1_category="null")])["issue_breakdown"]
        assert breakdown == {"categories": [], "build_queue": []}

    def test_categories_sorted_by_count_desc(self, breakdown_results):
        cats = aggregate_metrics(breakdown_results)["issue_breakdown"]["categories"]
        assert [c["category"] for c in cats] == ["billing", "technical", "device"]
        assert [c["count"] for c in cats] == [10, 6, 4]

    def test_category_pct_and_dollars(self, breakdown_results):
        cats = {c["category"]: c for c in aggregate_metrics(breakdown_results)["issue_breakdown"]["categories"]}
        assert cats["billing"]["pct"] == 50.0
        assert cats["billing"]["dollars"] == 300_000
        assert cats["technical"]["dollars"] == 180_000
        assert cats["device"]["dollars"] == 120_000

    def test_segment_counts_pcts_and_methods(self, breakdown_results):
        cats = aggregate_metrics(breakdown_results)["issue_breakdown"]["categories"]
        billing = next(c for c in cats if c["category"] == "billing")
        segs = billing["segments"]
        assert segs["prevent"]["count"] == 4
        assert segs["prevent"]["pct"] == 40.0
        assert segs["prevent"]["methods"] == {"agent_action": 3, "escalated": 1}
        assert segs["automate_self_serve"]["count"] == 3
        assert segs["automate_agentic"]["count"] == 2
        assert segs["human"]["count"] == 1

    def test_segment_absent_when_zero(self, breakdown_results):
        cats = aggregate_metrics(breakdown_results)["issue_breakdown"]["categories"]
        device = next(c for c in cats if c["category"] == "device")
        assert set(device["segments"]) == {"automate_self_serve"}

    def test_build_queue_top4_sorted_by_dollars(self, breakdown_results):
        queue = aggregate_metrics(breakdown_results)["issue_breakdown"]["build_queue"]
        assert len(queue) == 4
        dollars = [item["dollars"] for item in queue]
        assert dollars == sorted(dollars, reverse=True)
        assert dollars[0] == 150_000
        assert dollars[-1] == 60_000
        # technical/prevent ($30K) is the smallest opportunity — excluded from top 4
        assert not any(
            item["category"] == "technical" and item["segment"] == "prevent"
            for item in queue
        )

    def test_build_queue_automate_combines_self_serve_and_agentic(self, breakdown_results):
        queue = aggregate_metrics(breakdown_results)["issue_breakdown"]["build_queue"]
        billing_automate = next(
            item for item in queue if item["category"] == "billing" and item["segment"] == "automate"
        )
        assert billing_automate["count"] == 5
        assert billing_automate["self_serve_count"] == 3
        assert billing_automate["agentic_count"] == 2
        assert billing_automate["pct"] == 50.0
        assert billing_automate["dollars"] == 150_000
        assert billing_automate["methods"] == {"self_serve_guidance": 3, "agent_action": 2}

    def test_build_queue_prevent_item_shape(self, breakdown_results):
        queue = aggregate_metrics(breakdown_results)["issue_breakdown"]["build_queue"]
        billing_prevent = next(
            item for item in queue if item["category"] == "billing" and item["segment"] == "prevent"
        )
        assert billing_prevent["count"] == 4
        assert billing_prevent["category_count"] == 10
        assert billing_prevent["dollars"] == 120_000
        assert billing_prevent["methods"] == {"agent_action": 3, "escalated": 1}

    def test_direct_call_matches_aggregate_metrics(self, breakdown_results):
        df = pd.DataFrame(breakdown_results)
        direct = _category_resolution_breakdown(df, len(df), baseline_monthly_cost=600_000)
        via_aggregate = aggregate_metrics(breakdown_results)["issue_breakdown"]
        assert direct == via_aggregate
