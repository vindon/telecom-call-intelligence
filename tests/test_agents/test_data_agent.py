"""
Tests for pipeline/agents/data_agent.py — DataIngestionAgent.
The HuggingFace/CSV loader is stubbed; validation, PII gating, and the
decision-log contract run against the real governance singletons.
"""

import pytest

import pipeline.agents.data_agent as data_agent_mod
from pipeline.agents.data_agent import DataIngestionAgent
from pipeline.config import MIN_TRANSCRIPT_CHARS, MIN_TURN_COUNT


@pytest.fixture
def run_agent(monkeypatch, make_transcript):
    """Run DataIngestionAgent against a stubbed transcript loader."""
    def _run(transcripts: list[dict]) -> dict:
        monkeypatch.setattr(
            data_agent_mod, "load_telecom_transcripts",
            lambda n, seed, offset: transcripts,
        )
        state = {"n_calls": len(transcripts), "seed": 42, "offset": 0}
        return DataIngestionAgent().run(state)
    return _run


class TestDataIngestionAgent:
    def test_valid_transcripts_pass_through(self, run_agent, make_transcript):
        out = run_agent([make_transcript("c1"), make_transcript("c2")])
        assert len(out["validated_transcripts"]) == 2
        assert out["validation_errors"] == []
        assert len(out["raw_transcripts"]) == 2

    def test_empty_transcript_rejected(self, run_agent, make_transcript):
        out = run_agent([make_transcript("c1", transcript_text="")])
        assert out["validated_transcripts"] == []
        assert "empty transcript" in out["validation_errors"][0]

    def test_short_transcript_rejected(self, run_agent, make_transcript):
        short = "A: hi\nC: bye"
        assert len(short) < MIN_TRANSCRIPT_CHARS
        out = run_agent([make_transcript("c1", transcript_text=short)])
        assert out["validated_transcripts"] == []
        assert "too short" in out["validation_errors"][0]

    def test_low_turn_count_rejected(self, run_agent, make_transcript):
        out = run_agent([make_transcript("c1", turn_count=MIN_TURN_COUNT - 1)])
        assert out["validated_transcripts"] == []
        assert "too few turns" in out["validation_errors"][0]

    def test_mixed_batch_partitions_correctly(self, run_agent, make_transcript):
        out = run_agent([
            make_transcript("good"),
            make_transcript("bad-empty", transcript_text=""),
            make_transcript("bad-turns", turn_count=2),
        ])
        assert [t["call_id"] for t in out["validated_transcripts"]] == ["good"]
        assert len(out["validation_errors"]) == 2

    def test_pii_redacted_before_pipeline_entry(self, run_agent, make_transcript):
        leaky = make_transcript("c1")
        leaky["transcript_text"] += "\n[10:01:10] CUSTOMER: Reach me at vinoth.test@example.com."
        out = run_agent([leaky])
        valid = out["validated_transcripts"][0]
        assert "vinoth.test@example.com" not in valid["transcript_text"]
        assert "email" in valid["_pii_redacted"]

    def test_skip_decisions_are_logged(self, run_agent, make_transcript):
        out = run_agent([make_transcript("c1", transcript_text="")])
        skips = [d for d in out["decision_log"] if d["decision_type"] == "transcript_skip"]
        assert len(skips) == 1
        assert skips[0]["agent"] == "DataIngestionAgent"

    def test_state_is_not_mutated(self, monkeypatch, make_transcript):
        monkeypatch.setattr(
            data_agent_mod, "load_telecom_transcripts",
            lambda n, seed, offset: [make_transcript()],
        )
        state = {"n_calls": 1, "seed": 42, "offset": 0}
        out = DataIngestionAgent().run(state)
        assert out is not state
        assert "validated_transcripts" not in state
