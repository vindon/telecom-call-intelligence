"""
Tests for pipeline/memory.py — AgentMemory CRUD, persistence, and context generation.
All tests use tmp_path-backed instances — no side effects on outputs/agent_memory.json.
"""

import json

import pytest

from pipeline.memory import _SCHEMA_VERSION, AgentMemory


class TestAgentMemoryInit:
    def test_fresh_instance_has_zero_runs(self, tmp_path):
        mem = AgentMemory(path=tmp_path / "memory.json")
        assert mem.total_runs == 0

    def test_fresh_instance_cumulative_is_zero(self, tmp_path):
        mem = AgentMemory(path=tmp_path / "memory.json")
        c = mem.cumulative
        assert c["total_calls_analyzed"] == 0
        assert c["total_tokens"] == 0
        assert c["total_cost_usd"] == 0.0


class TestAgentMemoryLoad:
    def test_load_nonexistent_file_returns_self(self, tmp_path):
        mem = AgentMemory(path=tmp_path / "nonexistent.json")
        result = mem.load()
        assert result is mem
        assert mem.total_runs == 0

    def test_load_valid_file_restores_state(self, tmp_memory, sample_run_summary):
        tmp_memory.record_run(sample_run_summary)
        tmp_memory.save()

        mem2 = AgentMemory(path=tmp_memory.path)
        mem2.load()
        assert mem2.total_runs == 1

    def test_load_schema_mismatch_resets(self, tmp_path):
        bad_file = tmp_path / "memory.json"
        bad_file.write_text(json.dumps({"schema_version": "0.0", "total_runs": 99}))

        mem = AgentMemory(path=bad_file)
        mem.load()
        assert mem.total_runs == 0  # reset due to mismatch

    def test_load_corrupted_file_resets(self, tmp_path):
        bad_file = tmp_path / "memory.json"
        bad_file.write_text("not valid json {{{{")

        mem = AgentMemory(path=bad_file)
        mem.load()
        assert mem.total_runs == 0


class TestAgentMemoryRecordRun:
    def test_record_run_increments_total_runs(self, tmp_memory, sample_run_summary):
        tmp_memory.record_run(sample_run_summary)
        assert tmp_memory.total_runs == 1

    def test_record_multiple_runs(self, tmp_memory, sample_run_summary):
        for _ in range(5):
            tmp_memory.record_run(sample_run_summary)
        assert tmp_memory.total_runs == 5

    def test_cumulative_calls_accumulates(self, tmp_memory, sample_run_summary):
        tmp_memory.record_run(sample_run_summary)
        tmp_memory.record_run(sample_run_summary)
        expected = 2 * sample_run_summary["n_analyzed"]
        assert tmp_memory.cumulative["total_calls_analyzed"] == expected

    def test_cumulative_cost_accumulates(self, tmp_memory, sample_run_summary):
        tmp_memory.record_run(sample_run_summary)
        tmp_memory.record_run(sample_run_summary)
        expected = 2 * sample_run_summary["total_cost_usd"]
        assert abs(tmp_memory.cumulative["total_cost_usd"] - expected) < 1e-9

    def test_cumulative_tokens_accumulates(self, tmp_memory, sample_run_summary):
        tmp_memory.record_run(sample_run_summary)
        expected = sample_run_summary["total_tokens"]
        assert tmp_memory.cumulative["total_tokens"] == expected

    def test_run_history_capped_at_50(self, tmp_memory, sample_run_summary):
        for i in range(60):
            tmp_memory.record_run({**sample_run_summary, "offset": i * 20})
        assert len(tmp_memory._data["run_history"]) == 50

    def test_run_history_keeps_newest(self, tmp_memory, sample_run_summary):
        for i in range(55):
            tmp_memory.record_run({**sample_run_summary, "offset": i})
        # The oldest 5 are discarded; offset=5 should be the first remaining
        first_offset = tmp_memory._data["run_history"][0]["offset"]
        assert first_offset == 5


class TestAgentMemorySaveLoad:
    def test_save_creates_file(self, tmp_memory):
        tmp_memory.save()
        assert tmp_memory.path.exists()

    def test_save_load_roundtrip(self, tmp_memory, sample_run_summary):
        tmp_memory.record_run(sample_run_summary)
        tmp_memory.save()

        mem2 = AgentMemory(path=tmp_memory.path)
        mem2.load()
        assert mem2.total_runs == 1
        assert mem2.cumulative["total_calls_analyzed"] == sample_run_summary["n_analyzed"]

    def test_save_valid_json(self, tmp_memory, sample_run_summary):
        tmp_memory.record_run(sample_run_summary)
        tmp_memory.save()
        data = json.loads(tmp_memory.path.read_text())
        assert data["schema_version"] == _SCHEMA_VERSION
        assert data["total_runs"] == 1


class TestAgentMemoryRunHistory:
    def test_get_run_history_empty(self, tmp_memory):
        assert tmp_memory.get_run_history() == []

    def test_get_run_history_last_n(self, tmp_memory, sample_run_summary):
        for i in range(10):
            tmp_memory.record_run({**sample_run_summary, "offset": i * 20})
        history = tmp_memory.get_run_history(last_n=3)
        assert len(history) == 3
        # Last three offsets should be 140, 160, 180
        offsets = [r["offset"] for r in history]
        assert offsets == [140, 160, 180]

    def test_get_trend_summary_no_history(self, tmp_memory):
        trend = tmp_memory.get_trend_summary()
        assert "message" in trend

    def test_get_trend_summary_with_history(self, tmp_memory, sample_run_summary):
        tmp_memory.record_run(sample_run_summary)
        trend = tmp_memory.get_trend_summary()
        assert "avg_fcr_rate_pct" in trend
        assert trend["avg_fcr_rate_pct"] == sample_run_summary["fcr_rate_pct"]


class TestAgentMemoryQuotaAndFailures:
    def test_record_quota_event(self, tmp_memory):
        tmp_memory.record_quota_event("gemini-2.5-flash-lite", "Google AI Studio")
        events = tmp_memory._data["quota_events"]
        assert len(events) == 1
        assert events[0]["model"] == "gemini-2.5-flash-lite"
        assert events[0]["provider"] == "Google AI Studio"

    def test_quota_events_capped_at_10(self, tmp_memory):
        for _ in range(15):
            tmp_memory.record_quota_event("model", "provider")
        assert len(tmp_memory._data["quota_events"]) == 10

    def test_record_failures(self, tmp_memory):
        tmp_memory.record_failures(["call-001", "call-002"], context="batch 1")
        log = tmp_memory._data["failure_log"]
        assert len(log) == 1
        assert log[0]["count"] == 2
        assert log[0]["context"] == "batch 1"

    def test_record_failures_empty_list_is_noop(self, tmp_memory):
        tmp_memory.record_failures([], context="nothing")
        assert len(tmp_memory._data["failure_log"]) == 0

    def test_failure_log_capped_at_20(self, tmp_memory):
        for i in range(25):
            tmp_memory.record_failures(["call"], context=f"batch {i}")
        assert len(tmp_memory._data["failure_log"]) == 20


class TestAgentMemoryInsightsContext:
    def test_context_no_history_mentions_first_run(self, tmp_memory):
        ctx = tmp_memory.get_context_for_insights()
        assert "first run" in ctx.lower() or "no historical" in ctx.lower()

    def test_context_with_history_contains_kpis(self, tmp_memory, sample_run_summary):
        tmp_memory.record_run(sample_run_summary)
        ctx = tmp_memory.get_context_for_insights()
        assert "FCR" in ctx

    def test_context_with_quota_events_mentions_count(self, tmp_memory, sample_run_summary):
        tmp_memory.record_run(sample_run_summary)
        tmp_memory.record_quota_event("gemini-2.5-flash-lite", "Google AI Studio")
        ctx = tmp_memory.get_context_for_insights()
        assert "1" in ctx  # quota event count


class TestAgentMemoryModelPerf:
    def test_record_model_call_success(self, tmp_memory):
        tmp_memory.record_model_call("gemini-2.5-flash-lite", success=True, latency_s=2.0)
        stats = tmp_memory.get_model_stats("gemini-2.5-flash-lite")
        assert stats["total_calls"] == 1
        assert stats["success_rate_pct"] == 100.0

    def test_record_model_call_mixed(self, tmp_memory):
        tmp_memory.record_model_call("gemini-2.5-flash-lite", success=True, latency_s=2.0)
        tmp_memory.record_model_call("gemini-2.5-flash-lite", success=False, latency_s=1.0)
        stats = tmp_memory.get_model_stats("gemini-2.5-flash-lite")
        assert stats["success_rate_pct"] == 50.0
        assert stats["avg_latency_s"] == 1.5

    def test_get_model_stats_unknown_model(self, tmp_memory):
        stats = tmp_memory.get_model_stats("unknown-model")
        assert "message" in stats
