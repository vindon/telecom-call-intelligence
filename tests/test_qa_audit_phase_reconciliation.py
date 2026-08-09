"""
Tests for qa_audit.py's data-quality gate — phase reconciliation, timestamp
ground-truth, and transcript-completeness checks.

These are deterministic, non-LLM regression tests: the core assertion is
that the sum of phase-level durations must never exceed total_duration_seconds
by more than a small tolerance. No API calls, no mocks — pure functions over
plain dicts, matching CLAUDE.md's rule that governance-adjacent logic is
tested directly.
"""

from pipeline.config import (
    PHASE_RECONCILIATION_TOLERANCE_PCT,
    PHASE_RECONCILIATION_TOLERANCE_S,
    TIMESTAMP_GROUND_TRUTH_TOLERANCE_PCT,
    TIMESTAMP_GROUND_TRUTH_TOLERANCE_S,
)
from qa_audit import (
    check_data_quality,
    check_phase_reconciliation,
    check_timestamp_ground_truth,
    check_transcript_completeness,
)


class TestPhaseReconciliation:
    def test_reconciling_phases_pass(self, make_record):
        # make_record's default phases sum to exactly total_duration_seconds (420s).
        result = check_phase_reconciliation(make_record())
        assert result["passed"] is True
        assert result["delta_s"] <= 0

    def test_phase_sum_exceeding_tolerance_fails(self, make_record):
        record = make_record(phase_resolution_duration_seconds=120 + 200)  # +200s overcount
        result = check_phase_reconciliation(record)
        assert result["passed"] is False
        assert result["delta_s"] > result["tolerance_s"]
        assert result["phase_sum_s"] > result["total_duration_s"]

    def test_boundary_exactly_at_tolerance_passes(self, make_record):
        total = 420
        tolerance = max(PHASE_RECONCILIATION_TOLERANCE_S, PHASE_RECONCILIATION_TOLERANCE_PCT * total)
        record = make_record(phase_resolution_duration_seconds=120 + tolerance)
        result = check_phase_reconciliation(record)
        assert result["passed"] is True
        assert result["delta_s"] == round(tolerance, 1)

    def test_missing_phase_fields_treated_as_zero(self, make_record):
        record = make_record()
        for field in (
            "phase_welcome_duration_seconds", "phase_discovery_duration_seconds",
            "phase_diagnosis_duration_seconds", "phase_resolution_duration_seconds",
            "phase_hold_total_seconds", "phase_upsell_duration_seconds",
            "phase_closing_duration_seconds",
        ):
            record.pop(field, None)
        # Should not crash, and with everything missing, phase_sum=0 <= total.
        result = check_phase_reconciliation(record)
        assert result["passed"] is True
        assert result["phase_sum_s"] == 0.0

    def test_null_phase_values_treated_as_zero(self, make_record):
        record = make_record(phase_upsell_duration_seconds=None, phase_hold_total_seconds="null")
        result = check_phase_reconciliation(record)
        assert result["passed"] is True

    def test_missing_total_duration_does_not_fail_this_check(self, make_record):
        record = make_record()
        record.pop("total_duration_seconds", None)
        result = check_phase_reconciliation(record)
        assert result["passed"] is True
        assert result["total_duration_s"] is None

    def test_relationship_building_phase_is_included_in_sum(self, make_record):
        # Regression: qa_audit's phase_cols historically omitted this field.
        record = make_record(phase_relationship_building_duration_seconds=100)
        result = check_phase_reconciliation(record)
        assert result["passed"] is False
        assert result["phase_sum_s"] == 520.0


class TestTimestampGroundTruth:
    def test_matching_ground_truth_passes(self, make_record):
        record = make_record()
        record["_raw_duration_seconds"] = 420
        result = check_timestamp_ground_truth(record)
        assert result["passed"] is True

    def test_mismatched_ground_truth_fails(self, make_record):
        record = make_record()
        record["_raw_duration_seconds"] = 420 + 500  # LLM total wildly off from source timestamps
        result = check_timestamp_ground_truth(record)
        assert result["passed"] is False
        assert result["delta_s"] > result["tolerance_s"]

    def test_boundary_exactly_at_tolerance_passes(self, make_record):
        raw = 420
        tolerance = max(TIMESTAMP_GROUND_TRUTH_TOLERANCE_S, TIMESTAMP_GROUND_TRUTH_TOLERANCE_PCT * raw)
        record = make_record(total_duration_seconds=raw + tolerance)
        record["_raw_duration_seconds"] = raw
        result = check_timestamp_ground_truth(record)
        assert result["passed"] is True

    def test_missing_ground_truth_passes(self, make_record):
        # Enterprise sources that don't supply turn-level timestamps shouldn't fail this check.
        result = check_timestamp_ground_truth(make_record())
        assert result["passed"] is True
        assert result["raw_duration_s"] is None


class TestTranscriptCompleteness:
    def test_not_truncated_passes(self, make_record):
        result = check_transcript_completeness(make_record(transcript_truncated=False))
        assert result["passed"] is True
        assert result["truncated"] is False

    def test_truncated_fails_with_reason(self, make_record):
        record = make_record(
            transcript_truncated=True,
            truncation_reason="cuts off mid-sentence during diagnosis",
        )
        result = check_transcript_completeness(record)
        assert result["passed"] is False
        assert result["truncated"] is True
        assert result["reason"] == "cuts off mid-sentence during diagnosis"

    def test_absent_field_defaults_to_not_truncated(self, make_record):
        record = make_record()
        record.pop("transcript_truncated", None)
        result = check_transcript_completeness(record)
        assert result["passed"] is True


class TestCheckDataQuality:
    def test_clean_record_passes_all_checks(self, make_record):
        result = check_data_quality(make_record())
        assert result["passed"] is True
        assert result["failures"] == []

    def test_multiple_failures_all_reported(self, make_record):
        record = make_record(
            phase_resolution_duration_seconds=120 + 300,
            transcript_truncated=True,
            truncation_reason="ends abruptly, no goodbye",
        )
        record["_raw_duration_seconds"] = 420 + 1000
        result = check_data_quality(record)
        assert result["passed"] is False
        assert set(result["failures"]) == {
            "phase_reconciliation", "timestamp_ground_truth", "transcript_truncation",
        }
        assert set(result["checks"]) == {
            "phase_reconciliation", "timestamp_ground_truth", "transcript_truncation",
        }
