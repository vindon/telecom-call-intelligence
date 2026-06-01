"""
tests/test_decision_log.py  —  Decision Traceability Layer Tests
-----------------------------------------------------------------
Tests for pipeline/decision_log.py.

All tests are pure Python — no API calls, no filesystem writes.
Expected: all tests pass in < 1 second.
"""

import pytest

from pipeline.decision_log import (
    DecisionLogger,
    DecisionRecord,
    summarize_decisions,
)


# ── DecisionRecord ────────────────────────────────────────────────────

class TestDecisionRecord:
    def test_required_fields_present(self):
        rec = DecisionRecord(
            agent="TestAgent",
            decision_type="test_type",
            decision="Did the thing",
            reason="Because the score was low",
        )
        assert rec.agent         == "TestAgent"
        assert rec.decision_type == "test_type"
        assert rec.decision      == "Did the thing"
        assert rec.reason        == "Because the score was low"

    def test_record_id_is_8_chars(self):
        rec = DecisionRecord("A", "t", "d", "r")
        assert len(rec.record_id) == 8

    def test_timestamp_is_utc_iso(self):
        rec = DecisionRecord("A", "t", "d", "r")
        assert "T" in rec.timestamp
        assert rec.timestamp.endswith("Z")

    def test_defaults_are_safe(self):
        rec = DecisionRecord("A", "t", "d", "r")
        assert rec.evidence     == {}
        assert rec.call_id      is None
        assert rec.confidence   is None
        assert rec.alternatives == []

    def test_reason_truncated_at_500(self):
        long_reason = "x" * 600
        rec = DecisionRecord("A", "t", "d", long_reason)
        assert len(rec.reason) == 500

    def test_to_dict_has_all_keys(self):
        rec = DecisionRecord(
            agent="QualityAgent",
            decision_type="qa_exclusion",
            decision="Excluded call C001",
            reason="Score 42 < 60",
            evidence={"score": 42},
            call_id="C001",
            confidence="high",
            alternatives=["Include with flag"],
        )
        d = rec.to_dict()
        for key in ("record_id", "agent", "decision_type", "timestamp",
                    "decision", "reason", "evidence", "call_id",
                    "confidence", "alternatives"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_evidence_is_dict(self):
        rec = DecisionRecord("A", "t", "d", "r", evidence={"score": 42})
        assert rec.to_dict()["evidence"] == {"score": 42}

    def test_two_records_have_different_ids(self):
        r1 = DecisionRecord("A", "t", "d", "r")
        r2 = DecisionRecord("A", "t", "d", "r")
        assert r1.record_id != r2.record_id


# ── DecisionLogger ────────────────────────────────────────────────────

class TestDecisionLogger:
    def _empty_state(self) -> dict:
        return {}

    def _state_with_existing(self, n: int = 2) -> dict:
        existing = [
            DecisionRecord("PriorAgent", "prior_type", f"Decision {i}", "Prior reason").to_dict()
            for i in range(n)
        ]
        return {"decision_log": existing}

    def test_starts_empty_from_empty_state(self):
        dl = DecisionLogger("TestAgent", self._empty_state())
        result = dl.finalize()
        assert result == []

    def test_preserves_existing_decisions(self):
        dl = DecisionLogger("TestAgent", self._state_with_existing(3))
        result = dl.finalize()
        assert len(result) == 3

    def test_log_appends_new_record(self):
        dl = DecisionLogger("TestAgent", self._empty_state())
        dl.log("test_type", "Did X", "Because Y")
        result = dl.finalize()
        assert len(result) == 1
        assert result[0]["agent"]         == "TestAgent"
        assert result[0]["decision_type"] == "test_type"
        assert result[0]["decision"]      == "Did X"

    def test_multiple_logs_accumulate(self):
        dl = DecisionLogger("QualityAgent", self._empty_state())
        dl.log("qa_exclusion", "Excluded A", "Score 40")
        dl.log("qa_exclusion", "Excluded B", "Score 55")
        assert len(dl.finalize()) == 2

    def test_existing_plus_new(self):
        dl = DecisionLogger("TestAgent", self._state_with_existing(2))
        dl.log("new_type", "New decision", "New reason")
        result = dl.finalize()
        assert len(result) == 3
        # New record is last
        assert result[-1]["decision_type"] == "new_type"

    def test_new_count_property(self):
        dl = DecisionLogger("TestAgent", self._empty_state())
        assert dl.new_count == 0
        dl.log("t", "d", "r")
        dl.log("t", "d", "r")
        assert dl.new_count == 2

    def test_finalize_returns_plain_dicts(self):
        dl = DecisionLogger("TestAgent", self._empty_state())
        dl.log("t", "d", "r")
        result = dl.finalize()
        assert isinstance(result[0], dict)

    def test_finalize_is_idempotent(self):
        dl = DecisionLogger("TestAgent", self._empty_state())
        dl.log("t", "d", "r")
        r1 = dl.finalize()
        r2 = dl.finalize()
        assert r1 == r2

    def test_log_with_all_optional_fields(self):
        dl = DecisionLogger("InsightsAgent", self._empty_state())
        dl.log(
            decision_type="provider_selected",
            decision="NVIDIA NIM selected",
            reason="NVIDIA_API_KEY present and call succeeded",
            evidence={"source": "llm_deliberated", "passes": 3},
            call_id=None,
            confidence="high",
            alternatives=["Claude fallback", "Rule-based"],
        )
        rec = dl.finalize()[0]
        assert rec["confidence"]   == "high"
        assert rec["alternatives"] == ["Claude fallback", "Rule-based"]
        assert rec["evidence"]["passes"] == 3


# ── summarize_decisions ───────────────────────────────────────────────

class TestSummarizeDecisions:
    def _make_log(self, specs: list[tuple[str, str]]) -> list[dict]:
        records = []
        for agent, dtype in specs:
            r = DecisionRecord(agent, dtype, f"{agent} did {dtype}", "test reason")
            records.append(r.to_dict())
        return records

    def test_empty_log(self):
        summary = summarize_decisions([])
        assert summary["total_decisions"]   == 0
        assert summary["by_agent"]          == {}
        assert summary["by_type"]           == {}
        assert summary["notable_decisions"] == []

    def test_total_count(self):
        log = self._make_log([
            ("DataIngestionAgent", "transcript_skip"),
            ("QualityAgent", "qa_exclusion"),
            ("InsightsAgent", "provider_selected"),
        ])
        summary = summarize_decisions(log)
        assert summary["total_decisions"] == 3

    def test_by_agent_counts(self):
        log = self._make_log([
            ("QualityAgent", "qa_exclusion"),
            ("QualityAgent", "quality_gate_outcome"),
            ("InsightsAgent", "provider_selected"),
        ])
        summary = summarize_decisions(log)
        assert summary["by_agent"]["QualityAgent"]   == 2
        assert summary["by_agent"]["InsightsAgent"]  == 1

    def test_by_type_counts(self):
        log = self._make_log([
            ("DataIngestionAgent", "transcript_skip"),
            ("DataIngestionAgent", "transcript_skip"),
            ("QualityAgent", "qa_exclusion"),
        ])
        summary = summarize_decisions(log)
        assert summary["by_type"]["transcript_skip"] == 2
        assert summary["by_type"]["qa_exclusion"]    == 1

    def test_notable_decisions_includes_exclusions(self):
        log = self._make_log([
            ("QualityAgent",      "qa_exclusion"),
            ("GraphRouter",       "routing_decision"),
            ("AggregationAgent",  "aggregation_scope"),  # not notable
        ])
        summary = summarize_decisions(log)
        notable_types = {n["decision_type"] for n in summary["notable_decisions"]}
        assert "qa_exclusion"     in notable_types
        assert "routing_decision" in notable_types
        assert "aggregation_scope" not in notable_types

    def test_notable_decisions_capped_at_20(self):
        log = self._make_log([
            ("DataIngestionAgent", "transcript_skip")
            for _ in range(30)
        ])
        summary = summarize_decisions(log)
        assert len(summary["notable_decisions"]) <= 20

    def test_notable_decision_fields(self):
        rec = DecisionRecord(
            "InsightsAgent", "provider_selected",
            "NVIDIA selected", "API key present",
            confidence="high",
        )
        summary = summarize_decisions([rec.to_dict()])
        notable = summary["notable_decisions"][0]
        assert "record_id"     in notable
        assert "agent"         in notable
        assert "decision_type" in notable
        assert "decision"      in notable
        assert "confidence"    in notable
