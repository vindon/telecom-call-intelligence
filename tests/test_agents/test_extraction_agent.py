"""
Tests for pipeline/agents/extraction_agent.py — ExtractionAgent.
analyze_batch and gap_fill_transcript are stubbed; the ReAct routing,
failure bookkeeping, and BudgetGuard enforcement are exercised for real.
"""

import pytest

import pipeline.agents.extraction_agent as ext_mod
import pipeline.analyzer as analyzer
from pipeline.agents.extraction_agent import ExtractionAgent
from pipeline.governance import BudgetGuard
from pipeline.memory import AgentMemory


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(ext_mod, "MEMORY", AgentMemory(path=tmp_path / "memory.json"))
    monkeypatch.setattr(analyzer, "_react_quota_exhausted", False)


def _state(transcripts: list[dict]) -> dict:
    return {"validated_transcripts": transcripts, "inter_call_delay": 0.0,
            "checkpoint_key": ""}


class TestExtractionAgent:
    def test_happy_path_outputs(self, monkeypatch, make_transcript, make_record):
        transcripts = [make_transcript("c1"), make_transcript("c2")]
        results = [make_record(call_id="c1"), make_record(call_id="c2")]
        monkeypatch.setattr(ext_mod, "analyze_batch", lambda t, **kw: results)
        # No API key → ReAct loop is a deterministic no-op
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        out = ExtractionAgent().run(_state(transcripts))
        assert len(out["analysis_results"]) == 2
        assert out["failed_call_ids"] == []
        assert out["react_stats"]["n_gap_fills"] == 0

    def test_failed_calls_recorded(self, monkeypatch, make_transcript, make_record):
        transcripts = [make_transcript("c1"), make_transcript("c2")]
        monkeypatch.setattr(
            ext_mod, "analyze_batch", lambda t, **kw: [make_record(call_id="c1")]
        )
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        out = ExtractionAgent().run(_state(transcripts))
        assert out["failed_call_ids"] == ["c2"]
        # Failure is persisted to agent memory for pattern analysis
        assert ext_mod.MEMORY._data["failure_log"][0]["failed_ids"] == ["c2"]

    def test_react_gap_fill_triggers_below_threshold(
        self, monkeypatch, make_transcript, make_record
    ):
        transcripts = [make_transcript("c1")]
        low_coverage = make_record(
            call_id="c1", fcr_indicator=None, escalation_required=None,
            customer_sentiment_start=None, customer_sentiment_end=None,
            all_issues_resolved=None,
        )
        repaired = make_record(call_id="c1")
        monkeypatch.setattr(ext_mod, "analyze_batch", lambda t, **kw: [low_coverage])
        monkeypatch.setattr(
            ext_mod, "gap_fill_transcript", lambda client, sp, t, fp: repaired
        )
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-dummy")

        out = ExtractionAgent().run(_state(transcripts))
        assert out["react_stats"]["n_gap_fills"] == 1
        assert out["react_stats"]["n_improved"] == 1
        assert out["analysis_results"][0]["fcr_indicator"] is True
        triggers = [d for d in out["decision_log"] if d["decision_type"] == "react_trigger"]
        assert len(triggers) == 1

    def test_react_skips_high_coverage_results(self, monkeypatch, make_transcript, make_record):
        transcripts = [make_transcript("c1")]
        monkeypatch.setattr(
            ext_mod, "analyze_batch", lambda t, **kw: [make_record(call_id="c1")]
        )

        def explode(*args, **kwargs):
            raise AssertionError("gap-fill must not run at 100% coverage")

        monkeypatch.setattr(ext_mod, "gap_fill_transcript", explode)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-dummy")

        out = ExtractionAgent().run(_state(transcripts))
        assert out["react_stats"]["n_gap_fills"] == 0

    def test_budget_exceeded_raises(self, monkeypatch, make_transcript, make_record):
        monkeypatch.setattr(
            ext_mod, "analyze_batch", lambda t, **kw: [make_record(call_id="c1")]
        )
        monkeypatch.setattr(ext_mod, "_cost_usd", lambda p, c, cc=0, cr=0: 999.0)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(BudgetGuard.BudgetExceededError):
            ExtractionAgent().run(_state([make_transcript("c1")]))

    def test_missing_state_key_rejected(self):
        with pytest.raises(Exception):
            ExtractionAgent().run({"inter_call_delay": 0.0})
