"""
Tests for pipeline/agents/quality_agent.py — QualityAgent.
Runs against the real qa_audit scoring engine and QualityGate — no mocks
(governance logic must be hit directly per CLAUDE.md).
"""

from pipeline.agents.quality_agent import QualityAgent
from qa_audit import audit_record


def _bad_record() -> dict:
    """A record engineered to fail every QA dimension → LOW grade."""
    return {
        "call_id":                  "bad-call",
        "total_duration_seconds":   5,           # implausibly short
        "total_issues_count":       9,           # outside [0, 5], no issue_1_description
        "fcr_indicator":            True,
        "escalation_required":      True,        # contradicts FCR
        "all_issues_resolved":      True,
        "repeat_call_risk":         "high",      # contradicts all_issues_resolved
        "could_be_self_served":     True,        # no channel given
        "upsell_attempted":         False,
        "upsell_outcome":           "accepted",  # contradicts upsell_attempted
        "customer_sentiment_start": "angry",     # invalid enum
        "agent_skill_rating":       "amazing",   # invalid enum
        "handle_time_efficiency":   "blazing",   # invalid enum
        "primary_cost_driver":      "vibes",     # invalid enum
    }


class TestGradeFixtures:
    """Sanity-check the fixtures against the real scoring engine."""

    def test_good_record_grades_high(self, make_record):
        assert audit_record(make_record())["grade"] == "HIGH"

    def test_bad_record_grades_low(self):
        assert audit_record(_bad_record())["grade"] == "LOW"


class TestQualityAgent:
    def test_empty_results_skips_qa(self):
        out = QualityAgent().run({"analysis_results": []})
        assert out["qa_report"]["dataset_verdict"] == "SKIP"
        assert out["qa_passed_results"] == []

    def test_results_enriched_with_qa_fields(self, make_record):
        out = QualityAgent().run({"analysis_results": [make_record()]})
        scored = out["analysis_results"][0]
        assert scored["_qa_grade"] == "HIGH"
        assert scored["_qa_score"] >= 85
        assert set(scored["_qa_dimensions"]) == {
            "completeness", "enum_validity", "consistency", "plausibility",
        }

    def test_low_records_excluded_from_passed(self, make_record):
        results = [make_record(call_id=f"good-{i}") for i in range(9)] + [_bad_record()]
        out = QualityAgent().run({"analysis_results": results})
        passed_ids = {r["call_id"] for r in out["qa_passed_results"]}
        assert "bad-call" not in passed_ids
        assert len(out["qa_passed_results"]) == 9
        exclusions = [d for d in out["decision_log"] if d["decision_type"] == "qa_exclusion"]
        assert len(exclusions) == 1

    def test_report_verdict_pass_for_clean_dataset(self, make_record):
        results = [make_record(call_id=f"c{i}") for i in range(5)]
        out = QualityAgent().run({"analysis_results": results})
        assert out["qa_report"]["dataset_verdict"] == "PASS"
        assert out["qa_report"]["summary"]["grade_HIGH"] == 5
        assert "_quality_gate_failed" not in out["qa_report"]

    def test_catastrophic_quality_sets_gate_flag_without_raising(self):
        # All-LOW dataset trips QualityGate; the agent must flag (not raise)
        # so the graph can route to emergency export.
        results = [dict(_bad_record(), call_id=f"bad-{i}") for i in range(5)]
        out = QualityAgent().run({"analysis_results": results})
        assert out["qa_report"]["dataset_verdict"] == "FAIL"
        assert out["qa_report"]["_quality_gate_failed"] is True
        assert out["qa_passed_results"] == []
