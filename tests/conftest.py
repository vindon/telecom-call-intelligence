"""
Shared pytest fixtures for the Telecom Call Intelligence test suite.
"""

import os

import pytest

# Ensure GEMINI_API_KEY is set for import-time checks in pipeline modules.
# Tests that make real API calls are marked @pytest.mark.slow and skipped in CI.
os.environ.setdefault("GEMINI_API_KEY", "test-key-ci-dummy")


@pytest.fixture
def sample_transcript():
    return {
        "call_id": "test-call-001",
        "transcript_text": (
            "Agent: Thank you for calling TeleCo support, how can I help?\n"
            "Customer: Hi, I need help understanding my latest bill.\n"
            "Agent: Of course, I can pull up your account. What's your account number?\n"
            "Customer: It's 987654. The charge on May 1st doesn't make sense to me.\n"
            "Agent: I see it — that's an early-termination fee from your previous plan.\n"
            "Customer: Oh, I see. Thank you for explaining that.\n"
        ),
        "n_turns": 6,
        "conversation_id": "conv-test-001",
    }


@pytest.fixture
def sample_analysis_result():
    return {
        "call_id":              "test-call-001",
        "intent":               "billing_inquiry",
        "resolution_status":    "resolved",
        "first_call_resolution": True,
        "escalated":            False,
        "handle_time_seconds":  420,
        "issue_count":          1,
        "upsell_attempted":     False,
        "upsell_success":       False,
        "sentiment_start":      "negative",
        "sentiment_end":        "positive",
        "repeat_call_risk":     "low",
        "avoidable_call":       False,
        "agentic_ai_resolvable": True,
        "cost_driver":          "billing",
        "agent_professionalism": "high",
    }


@pytest.fixture
def sample_run_summary():
    return {
        "run_timestamp":           "20260518_120000",
        "offset":                  0,
        "seed":                    42,
        "n_calls":                 20,
        "n_analyzed":              18,
        "n_failed":                2,
        "fcr_rate_pct":            72.5,
        "avg_handle_time_minutes": 7.2,
        "qa_avg_score":            88.0,
        "qa_verdict":              "PASS",
        "total_tokens":            45000,
        "total_cost_usd":          0.0012,
        "model":                   "gemini-2.5-flash-lite",
        "insights_source":         "gemini_llm",
    }


@pytest.fixture
def sample_qa_report():
    return {
        "dataset_verdict":    "PASS",
        "total_calls_audited": 20,
        "summary": {
            "avg_score":      88.5,
            "pass_rate_pct":  95.0,
            "grade_HIGH":     14,
            "grade_MEDIUM":   5,
            "grade_LOW":      1,
        },
    }


@pytest.fixture
def tmp_memory(tmp_path):
    """An AgentMemory instance backed by a temp file — no side effects."""
    from pipeline.memory import AgentMemory
    return AgentMemory(path=tmp_path / "agent_memory.json")


@pytest.fixture
def make_record():
    """
    Factory for extraction records matching the real qa_audit schema
    (REQUIRED_FIELDS + ENUM_RULES). The default record scores HIGH;
    pass overrides to degrade specific dimensions.
    """
    def _make(**overrides) -> dict:
        record = {
            "call_id":                        "test-call-001",
            "total_duration_seconds":         420,
            "total_issues_count":             1,
            "issue_1_category":               "billing",
            "issue_1_description":            "Question about an early-termination fee",
            "issue_1_resolution_method":      "agent_action",
            "primary_issue_resolved":         True,
            "all_issues_resolved":            True,
            "fcr_indicator":                  True,
            "escalation_required":            False,
            "customer_sentiment_start":       "negative",
            "customer_sentiment_end":         "positive",
            "customer_sentiment_improved":    True,
            "agent_skill_rating":             "proficient",
            "primary_cost_driver":            "billing",
            "avoidable_call":                 False,
            "could_be_self_served":           False,
            "agentic_ai_resolvable":          True,
            "proactive_outreach_applicable":  False,
            "repeat_call_risk":               "low",
            "handle_time_efficiency":         "efficient",
            "call_summary":                   "Customer asked about a fee; agent explained it.",
            "upsell_attempted":               False,
            "upsell_outcome":                 "not_attempted",
            "hold_count":                     0,
            "agent_empathy_statements_count": 2,
            "phase_welcome_duration_seconds":    30,
            "phase_discovery_duration_seconds":  90,
            "phase_diagnosis_duration_seconds":  120,
            "phase_resolution_duration_seconds": 120,
            "phase_hold_total_seconds":          0,
            "phase_upsell_duration_seconds":     0,
            "phase_closing_duration_seconds":    60,
            "_prompt_tokens":                 2000,
            "_completion_tokens":             1500,
            "_total_tokens":                  3500,
        }
        record.update(overrides)
        return record
    return _make


@pytest.fixture
def make_transcript():
    """Factory for transcript dicts matching hf_loader's output schema."""
    def _make(call_id: str = "conv-001", **overrides) -> dict:
        transcript = {
            "call_id":         call_id,
            "call_date":       "2026-06-01",
            "transcript_text": (
                "[10:00:01] AGENT: Thank you for calling TeleCo support, how can I help you today?\n"
                "[10:00:09] CUSTOMER: Hi, I need help understanding a charge on my latest bill.\n"
                "[10:00:20] AGENT: Of course, I can pull up your account and walk through it.\n"
                "[10:00:31] CUSTOMER: The charge from May 1st does not make sense to me at all.\n"
                "[10:00:45] AGENT: I see it — that is an early-termination fee from your previous plan.\n"
                "[10:00:58] CUSTOMER: Oh, I understand now. Thank you for explaining that clearly.\n"
            ),
            "turn_count":      6,
            "agent_turns":     3,
            "customer_turns":  3,
            "raw_start":       "10:00:01",
            "raw_end":         "10:00:58",
        }
        transcript.update(overrides)
        return transcript
    return _make
