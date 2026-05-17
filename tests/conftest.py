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
