"""
Tests for pipeline/governance.py — BudgetGuard, QualityGate, PIIScanner, AuditLog.
All tests are pure unit tests: no API calls, no filesystem side-effects (except AuditLog.export).
"""

import json

import pytest

from pipeline.governance import AuditLog, BudgetGuard, PIIScanner, QualityGate

# ── BudgetGuard ───────────────────────────────────────────────────────

class TestBudgetGuard:
    def test_under_budget_passes(self):
        guard = BudgetGuard(max_cost_usd=5.0)
        guard.check(1.0)  # must not raise

    def test_exactly_at_budget_passes(self):
        guard = BudgetGuard(max_cost_usd=5.0)
        guard.check(5.0)  # boundary — $5.00 is not over $5.00

    def test_over_budget_raises(self):
        guard = BudgetGuard(max_cost_usd=5.0)
        with pytest.raises(BudgetGuard.BudgetExceededError, match="exceeds budget"):
            guard.check(5.01)

    def test_error_message_contains_amounts(self):
        guard = BudgetGuard(max_cost_usd=1.0)
        with pytest.raises(BudgetGuard.BudgetExceededError) as exc_info:
            guard.check(2.50)
        assert "2.5" in str(exc_info.value) or "2.50" in str(exc_info.value)

    def test_estimate_remaining_calls_basic(self):
        guard = BudgetGuard(max_cost_usd=1.0)
        remaining = guard.estimate_remaining_calls(current_cost_usd=0.5, avg_cost_per_call=0.01)
        assert remaining == 50

    def test_estimate_remaining_calls_at_limit(self):
        guard = BudgetGuard(max_cost_usd=1.0)
        remaining = guard.estimate_remaining_calls(current_cost_usd=1.0, avg_cost_per_call=0.01)
        assert remaining == 0

    def test_estimate_remaining_calls_zero_avg_cost(self):
        guard = BudgetGuard(max_cost_usd=1.0)
        # Zero avg cost → can't estimate → returns sentinel value
        assert guard.estimate_remaining_calls(0.0, 0.0) == 9999

    def test_zero_budget_raises_immediately(self):
        guard = BudgetGuard(max_cost_usd=0.0)
        with pytest.raises(BudgetGuard.BudgetExceededError):
            guard.check(0.001)


# ── QualityGate ───────────────────────────────────────────────────────

class TestQualityGate:
    def _report(self, pass_rate_pct: float, verdict: str = "PASS", n: int = 20) -> dict:
        return {
            "dataset_verdict":     verdict,
            "total_calls_audited": n,
            "summary": {
                "pass_rate_pct": pass_rate_pct,
                "avg_score":     pass_rate_pct,  # simplified
            },
        }

    def test_pass_rate_well_above_threshold_passes(self):
        gate = QualityGate(min_pass_rate=0.40)
        gate.check(self._report(90.0))  # must not raise

    def test_pass_rate_at_threshold_passes(self):
        gate = QualityGate(min_pass_rate=0.40)
        gate.check(self._report(40.0))  # boundary — 40% is not below 40%

    def test_pass_rate_below_threshold_raises(self):
        gate = QualityGate(min_pass_rate=0.40)
        with pytest.raises(QualityGate.QualityGateError):
            gate.check(self._report(39.9, verdict="FAIL"))

    def test_catastrophic_failure_raises(self):
        gate = QualityGate(min_pass_rate=0.40)
        with pytest.raises(QualityGate.QualityGateError, match="below minimum"):
            gate.check(self._report(10.0, verdict="FAIL"))

    def test_empty_report_skipped(self):
        gate = QualityGate(min_pass_rate=0.40)
        gate.check({})  # must not raise — no data yet

    def test_skip_verdict_skipped(self):
        gate = QualityGate(min_pass_rate=0.40)
        gate.check({"dataset_verdict": "SKIP"})  # must not raise

    def test_custom_threshold(self):
        gate = QualityGate(min_pass_rate=0.80)
        with pytest.raises(QualityGate.QualityGateError):
            gate.check(self._report(75.0, verdict="FAIL"))


# ── PIIScanner ────────────────────────────────────────────────────────

class TestPIIScanner:
    @pytest.fixture(autouse=True)
    def scanner(self):
        self.scanner = PIIScanner()

    def test_detects_email(self):
        found = self.scanner.scan("Contact john.doe@example.com for support")
        assert "email" in found

    def test_detects_us_phone(self):
        found = self.scanner.scan("Call us at 555-123-4567")
        assert "phone_us" in found

    def test_detects_ssn(self):
        found = self.scanner.scan("My SSN is 123-45-6789")
        assert "ssn" in found

    def test_detects_credit_card(self):
        found = self.scanner.scan("Card ending in 4111 1111 1111 1111")
        assert "credit_card" in found

    def test_detects_account_number(self):
        found = self.scanner.scan("Account number: 123456789")
        assert "account_num" in found

    def test_clean_text_returns_empty(self):
        found = self.scanner.scan("Hello, how can I help you today with your service?")
        assert found == []

    def test_redact_replaces_email(self):
        text, found = self.scanner.redact("Email me at test@example.com please")
        assert "[REDACTED]" in text
        assert "test@example.com" not in text
        assert "email" in found

    def test_redact_multiple_pii_types(self):
        text, found = self.scanner.redact(
            "Email bad@test.com and call 555-123-4567"
        )
        assert text.count("[REDACTED]") == 2
        assert "email" in found
        assert "phone_us" in found

    def test_scan_transcript_redacts_pii_in_text(self):
        transcript = {
            "call_id":         "001",
            "transcript_text": "Customer said: my email is pii@test.com",
        }
        result = self.scanner.scan_transcript(transcript)
        assert "[REDACTED]" in result["transcript_text"]
        assert "_pii_redacted" in result
        assert "email" in result["_pii_redacted"]

    def test_scan_transcript_clean_is_unchanged(self):
        transcript = {
            "call_id":         "002",
            "transcript_text": "Agent: How can I help you today?",
        }
        result = self.scanner.scan_transcript(transcript)
        assert "_pii_redacted" not in result
        assert result["transcript_text"] == transcript["transcript_text"]

    def test_scan_transcript_preserves_other_fields(self):
        transcript = {
            "call_id":         "003",
            "transcript_text": "Call me at 555-000-1234",
            "n_turns":         4,
        }
        result = self.scanner.scan_transcript(transcript)
        assert result["call_id"] == "003"
        assert result["n_turns"] == 4


# ── AuditLog ─────────────────────────────────────────────────────────

class TestAuditLog:
    def test_initially_empty(self):
        audit = AuditLog()
        assert audit.summary()["total_events"] == 0

    def test_record_agent_start(self):
        audit = AuditLog()
        audit.record_agent_start("TestAgent", {"key": "value"})
        assert audit.summary()["total_events"] == 1
        assert audit.summary()["by_type"]["agent_start"] == 1

    def test_record_agent_end(self):
        audit = AuditLog()
        audit.record_agent_end("TestAgent", {"result": "ok"}, elapsed_s=1.5)
        assert audit.summary()["by_type"]["agent_end"] == 1

    def test_record_error_increments_error_count(self):
        audit = AuditLog()
        audit.record_error("TestAgent", "Something broke")
        assert audit.summary()["error_count"] == 1

    def test_record_pii_detection(self):
        audit = AuditLog()
        audit.record_pii("call-001", ["email", "phone_us"])
        assert audit.summary()["by_type"]["pii_detection"] == 1

    def test_record_governance_check(self):
        audit = AuditLog()
        audit.record_governance("budget_check", passed=True, details={"cost": 0.50})
        assert audit.summary()["by_type"]["governance_check"] == 1

    def test_record_tool_call(self):
        audit = AuditLog()
        audit.record_tool_call(
            tool="fetch_transcripts",
            agent="DataIngestionAgent",
            inputs=["n", "seed"],
            success=True,
            elapsed_s=0.5,
        )
        assert audit.summary()["by_type"]["tool_call"] == 1

    def test_multiple_events_counted(self):
        audit = AuditLog()
        audit.record_agent_start("A", {})
        audit.record_agent_start("B", {})
        audit.record_agent_end("A", {}, 1.0)
        audit.record_error("B", "fail")
        assert audit.summary()["total_events"] == 4
        assert audit.summary()["error_count"] == 1

    def test_export_writes_valid_json(self, tmp_path):
        audit = AuditLog()
        audit.record_agent_start("TestAgent", {"input": "data"})
        audit.record_agent_end("TestAgent", {"output": "data"}, elapsed_s=1.0)
        path = audit.export(output_dir=tmp_path)

        assert path.exists()
        data = json.loads(path.read_text())
        assert data["total_events"] == 2
        assert len(data["events"]) == 2
        assert data["events"][0]["event_type"] == "agent_start"

    def test_export_path_inside_output_dir(self, tmp_path):
        audit = AuditLog()
        path = audit.export(output_dir=tmp_path)
        assert path.parent == tmp_path
