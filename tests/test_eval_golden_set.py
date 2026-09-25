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
