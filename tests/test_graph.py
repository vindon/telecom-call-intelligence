"""
Tests for pipeline/graph.py — LangGraph pipeline compilation and state schema.
No API calls are made; tests verify structural correctness only.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

# Ensure GEMINI_API_KEY is set before any pipeline import triggers the check
os.environ.setdefault("GEMINI_API_KEY", "test-key-ci-dummy")


class TestPipelineState:
    def test_state_has_all_required_keys(self):
        from pipeline.graph import PipelineState

        required = {
            # Configuration
            "n_calls",
            "seed",
            "offset",
            "inter_call_delay",
            "checkpoint_key",
            # Agent outputs
            "raw_transcripts",
            "validated_transcripts",
            "analysis_results",
            "qa_report",
            "qa_passed_results",
            "aggregated_metrics",
            "agent_insights",
            "export_paths",
            # Telemetry
            "validation_errors",
            "failed_call_ids",
            "token_usage",
            # Traceability
            "decision_log",
            "drift_report",
        }
        annotations = PipelineState.__annotations__
        missing = required - set(annotations.keys())
        assert not missing, f"PipelineState is missing keys: {missing}"

    def test_state_types_are_correct(self):
        from pipeline.graph import PipelineState

        a = PipelineState.__annotations__
        assert a["n_calls"] is int
        assert a["seed"] is int
        assert a["offset"] is int
        assert a["inter_call_delay"] is float
        assert a["checkpoint_key"] is str
        assert a["raw_transcripts"] is list
        assert a["analysis_results"] is list
        assert a["qa_report"] is dict
        assert a["aggregated_metrics"] is dict
        assert a["agent_insights"] is dict
        assert a["export_paths"] is dict


class TestBuildPipeline:
    def test_build_pipeline_returns_compiled_graph(self):
        from pipeline.graph import build_pipeline

        pipeline = build_pipeline()
        assert pipeline is not None

    def test_compiled_pipeline_is_invocable(self):
        from pipeline.graph import build_pipeline

        pipeline = build_pipeline()
        assert callable(getattr(pipeline, "invoke", None))

    def test_route_after_quality_normal_path(self):
        from pipeline.graph import _route_after_quality

        state = {"qa_report": {"_quality_gate_failed": False}}
        assert _route_after_quality(state) == "aggregate"

    def test_route_after_quality_gate_failure_path(self):
        from pipeline.graph import _route_after_quality

        state = {"qa_report": {"_quality_gate_failed": True}}
        assert _route_after_quality(state) == "export"

    def test_route_after_quality_missing_qa_report(self):
        from pipeline.graph import _route_after_quality

        state = {"qa_report": {}}
        assert _route_after_quality(state) == "aggregate"

    def test_route_after_quality_no_qa_key(self):
        from pipeline.graph import _route_after_quality

        state = {}
        assert _route_after_quality(state) == "aggregate"


# ── Node wrappers ───────────────────────────────────────────────────────
# Each node wrapper is a thin shim: dict(state) in, agent.run() out. The
# agent's own behavior is covered by tests/test_agents/*; these tests only
# verify the wrapper calls the right singleton and passes its result through
# unchanged (the printing is a side effect, not part of the contract).


class TestNodeWrappers:
    def test_ingest_node_delegates_to_data_agent(self):
        import pipeline.graph as graph_mod

        fake_result = {"validated_transcripts": [{"call_id": "c1"}], "validation_errors": []}
        with patch.object(graph_mod, "_data_agent") as mock_agent:
            mock_agent.run.return_value = fake_result
            result = graph_mod.ingest_node({"n_calls": 1})
        mock_agent.run.assert_called_once_with({"n_calls": 1})
        assert result is fake_result

    def test_extract_node_delegates_to_extraction_agent(self):
        import pipeline.graph as graph_mod

        fake_result = {"analysis_results": []}
        with patch.object(graph_mod, "_extraction_agent") as mock_agent:
            mock_agent.run.return_value = fake_result
            result = graph_mod.extract_node({"validated_transcripts": []})
        mock_agent.run.assert_called_once_with({"validated_transcripts": []})
        assert result is fake_result

    def test_quality_node_normal_verdict(self):
        import pipeline.graph as graph_mod

        fake_result = {
            "qa_report": {
                "dataset_verdict": "PASS",
                "summary": {"avg_score": 91.0, "grade_HIGH": 8, "grade_MEDIUM": 2, "grade_LOW": 0},
                "_quality_gate_failed": False,
            }
        }
        with patch.object(graph_mod, "_quality_agent") as mock_agent:
            mock_agent.run.return_value = fake_result
            result = graph_mod.quality_node({"analysis_results": []})
        assert result is fake_result

    def test_quality_node_gate_failure_prints_warning(self, capsys):
        import pipeline.graph as graph_mod

        fake_result = {"qa_report": {"dataset_verdict": "FAIL", "_quality_gate_failed": True}}
        with patch.object(graph_mod, "_quality_agent") as mock_agent:
            mock_agent.run.return_value = fake_result
            graph_mod.quality_node({"analysis_results": []})
        assert "Quality gate FAILED" in capsys.readouterr().out

    def test_aggregate_node_delegates_to_aggregation_agent(self):
        import pipeline.graph as graph_mod

        fake_result = {
            "aggregated_metrics": {
                "kpis": {
                    "total_calls_analyzed": 20,
                    "avg_handle_time_minutes": 7.1,
                    "fcr_rate_pct": 80.0,
                    "avoidable_call_rate_pct": 10.0,
                    "agentic_ai_resolvable_pct": 35.0,
                },
                "cost_levers": {"total_savings_opportunity_usd": 12000},
            },
            "token_usage": {"total_tokens": 5000, "total_cost_usd": 0.01},
        }
        with patch.object(graph_mod, "_aggregation_agent") as mock_agent:
            mock_agent.run.return_value = fake_result
            result = graph_mod.aggregate_node({"qa_passed_results": []})
        assert result is fake_result

    def test_insights_node_wraps_summary_and_recommendations(self, capsys):
        import pipeline.graph as graph_mod

        fake_result = {
            "agent_insights": {
                "source": "llm_deliberated",
                "executive_summary": "A " * 40,  # forces the word-wrap branch
                "top_recommendations": [
                    {"priority": 1, "title": "Reduce AHT"},
                    {"priority": 2, "title": "Improve FCR"},
                ],
            }
        }
        with patch.object(graph_mod, "_insights_agent") as mock_agent:
            mock_agent.run.return_value = fake_result
            result = graph_mod.insights_node({"aggregated_metrics": {}})
        out = capsys.readouterr().out
        assert "llm_deliberated" in out
        assert "Reduce AHT" in out
        assert result is fake_result

    def test_export_node_delegates_to_export_agent(self):
        import pipeline.graph as graph_mod

        fake_result = {
            "export_paths": {"csv": "outputs/x.csv"},
            "decision_log": [{"decision_type": "x"}],
        }
        with patch.object(graph_mod, "_export_agent") as mock_agent:
            mock_agent.run.return_value = fake_result
            result = graph_mod.export_node({"aggregated_metrics": {}})
        assert result is fake_result

    def test_export_node_prints_drift_banner_when_drifted(self, capsys):
        import pipeline.graph as graph_mod

        fake_result = {
            "export_paths": {"csv": "outputs/x.csv"},
            "decision_log": [],
            "drift_report": {
                "sufficient_history": True,
                "any_drifted": True,
                "baseline_run_count": 8,
                "metrics": [
                    {
                        "metric": "fcr_rate_pct",
                        "current": 40.0,
                        "baseline_mean": 75.0,
                        "drifted": True,
                    },
                ],
            },
        }
        with patch.object(graph_mod, "_export_agent") as mock_agent:
            mock_agent.run.return_value = fake_result
            graph_mod.export_node({"aggregated_metrics": {}})
        out = capsys.readouterr().out
        assert "DRIFTED" in out
        assert "fcr_rate_pct" in out

    def test_export_node_prints_insufficient_history(self, capsys):
        import pipeline.graph as graph_mod

        fake_result = {
            "export_paths": {"csv": "outputs/x.csv"},
            "decision_log": [],
            "drift_report": {
                "sufficient_history": False,
                "any_drifted": False,
                "baseline_run_count": 2,
                "metrics": [],
            },
        }
        with patch.object(graph_mod, "_export_agent") as mock_agent:
            mock_agent.run.return_value = fake_result
            graph_mod.export_node({"aggregated_metrics": {}})
        out = capsys.readouterr().out
        assert "insufficient history" in out


# ── Approval gate ────────────────────────────────────────────────────────


class TestApprovalGateNode:
    def test_disabled_auto_approves_without_prompting(self, monkeypatch, capsys):
        import pipeline.graph as graph_mod

        monkeypatch.setattr(graph_mod, "REQUIRE_HUMAN_APPROVAL", False)
        result = graph_mod.approval_gate_node({})
        assert result["approval_granted"] is True
        decisions = [d for d in result["decision_log"] if d["decision_type"] == "approval_decision"]
        assert len(decisions) == 1
        assert "prompt" not in capsys.readouterr().out.lower()

    def test_enabled_stdin_ready_approves(self, monkeypatch):
        import pipeline.graph as graph_mod

        monkeypatch.setattr(graph_mod, "REQUIRE_HUMAN_APPROVAL", True)
        monkeypatch.setattr(graph_mod, "APPROVAL_TIMEOUT_S", 5)
        with (
            patch("select.select", return_value=([MagicMock()], [], [])),
            patch("sys.stdin.readline", return_value="y\n"),
        ):
            result = graph_mod.approval_gate_node({"aggregated_metrics": {"kpis": {}}})
        assert result["approval_granted"] is True

    def test_enabled_timeout_auto_approves(self, monkeypatch):
        import pipeline.graph as graph_mod

        monkeypatch.setattr(graph_mod, "REQUIRE_HUMAN_APPROVAL", True)
        monkeypatch.setattr(graph_mod, "APPROVAL_TIMEOUT_S", 1)
        with patch("select.select", return_value=([], [], [])):
            result = graph_mod.approval_gate_node({"aggregated_metrics": {"kpis": {}}})
        assert result["approval_granted"] is True

    def test_enabled_explicit_rejection_raises(self, monkeypatch):
        import pipeline.graph as graph_mod

        monkeypatch.setattr(graph_mod, "REQUIRE_HUMAN_APPROVAL", True)
        monkeypatch.setattr(graph_mod, "APPROVAL_TIMEOUT_S", 5)
        with (
            patch("select.select", return_value=([MagicMock()], [], [])),
            patch("sys.stdin.readline", return_value="n\n"),
            pytest.raises(RuntimeError, match="rejected"),
        ):
            graph_mod.approval_gate_node({"aggregated_metrics": {"kpis": {}}})

    def test_non_interactive_environment_auto_approves(self, monkeypatch):
        """A subprocess with no attached stdin raises OSError/EOFError from
        select() or readline() — must fail open to auto-approve, not crash
        the pipeline (see orchestrator.py's subprocess model)."""
        import pipeline.graph as graph_mod

        monkeypatch.setattr(graph_mod, "REQUIRE_HUMAN_APPROVAL", True)
        monkeypatch.setattr(graph_mod, "APPROVAL_TIMEOUT_S", 5)
        with patch("select.select", side_effect=OSError("no stdin")):
            result = graph_mod.approval_gate_node({"aggregated_metrics": {"kpis": {}}})
        assert result["approval_granted"] is True

    def test_enabled_zero_timeout_uses_blocking_input(self, monkeypatch):
        import pipeline.graph as graph_mod

        monkeypatch.setattr(graph_mod, "REQUIRE_HUMAN_APPROVAL", True)
        monkeypatch.setattr(graph_mod, "APPROVAL_TIMEOUT_S", 0)
        with patch("builtins.input", return_value="y"):
            result = graph_mod.approval_gate_node({"aggregated_metrics": {"kpis": {}}})
        assert result["approval_granted"] is True


# ── LangSmith tracing configuration ──────────────────────────────────────


class TestConfigureTracing:
    def test_disabled_by_default(self, monkeypatch):
        import pipeline.graph as graph_mod

        monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
        graph_mod._configure_tracing()  # must not raise

    def test_enabled_without_api_key_warns_and_skips(self, monkeypatch):
        import pipeline.graph as graph_mod

        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
        monkeypatch.delenv("LANGCHAIN_PROJECT", raising=False)
        graph_mod._configure_tracing()
        assert "LANGCHAIN_PROJECT" not in os.environ

    def test_enabled_with_api_key_sets_project(self, monkeypatch):
        import pipeline.graph as graph_mod

        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "test-key")
        monkeypatch.delenv("LANGCHAIN_PROJECT", raising=False)
        graph_mod._configure_tracing()
        assert os.environ["LANGCHAIN_PROJECT"] == graph_mod.LANGSMITH_PROJECT


# ── build_pipeline() vector-memory load guard ────────────────────────────


class TestBuildPipelineVectorMemory:
    def test_vector_memory_load_failure_does_not_abort_build(self, monkeypatch):
        """VECTOR_STORE.load() failing (e.g. corrupt cache file) must be
        swallowed — vector memory is a nice-to-have for InsightsAgent context,
        never a reason the whole pipeline fails to build."""
        import pipeline.graph as graph_mod

        monkeypatch.setattr(graph_mod, "VECTOR_MEMORY_ENABLED", True)
        monkeypatch.setattr(graph_mod.MEMORY, "load", MagicMock())
        with patch("pipeline.vector_memory.VECTOR_STORE") as mock_store:
            mock_store.load.side_effect = RuntimeError("corrupt cache")
            pipeline = graph_mod.build_pipeline()  # must not raise
        assert pipeline is not None
