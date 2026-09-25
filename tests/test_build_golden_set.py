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
        assert (
            "_qa_grade" not in case["expected"]
        )  # only EXTRACTION_CRITICAL_FIELDS, no metadata leaks in
