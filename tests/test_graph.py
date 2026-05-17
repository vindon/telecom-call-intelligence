"""
Tests for pipeline/graph.py — LangGraph pipeline compilation and state schema.
No API calls are made; tests verify structural correctness only.
"""

import os

import pytest

# Ensure GEMINI_API_KEY is set before any pipeline import triggers the check
os.environ.setdefault("GEMINI_API_KEY", "test-key-ci-dummy")


class TestPipelineState:
    def test_state_has_all_required_keys(self):
        from pipeline.graph import PipelineState
        required = {
            # Configuration
            "n_calls", "seed", "offset", "inter_call_delay", "checkpoint_key",
            # Agent outputs
            "raw_transcripts", "validated_transcripts", "analysis_results",
            "qa_report", "qa_passed_results", "aggregated_metrics",
            "agent_insights", "export_paths",
            # Telemetry
            "validation_errors", "failed_call_ids", "token_usage",
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
