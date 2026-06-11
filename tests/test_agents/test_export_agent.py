"""
Tests for pipeline/agents/export_agent.py — ExportAgent.
All filesystem writes are redirected to a temp dir; verifies the full
artifact set, the emergency-export summary.json guard, and the manifest.
"""

import json
from pathlib import Path

import pytest

import pipeline.agents.export_agent as exp_mod
from pipeline.agents.export_agent import ExportAgent
from pipeline.memory import AgentMemory


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(exp_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(exp_mod, "MEMORY", AgentMemory(path=tmp_path / "memory.json"))
    return tmp_path


def _full_state(make_record) -> dict:
    results = [make_record(call_id="c1"), make_record(call_id="c2")]
    return {
        "n_calls": 2,
        "seed": 42,
        "offset": 0,
        "raw_transcripts":       [{}, {}],
        "validated_transcripts": [{}, {}],
        "analysis_results":      results,
        "qa_passed_results":     results,
        "failed_call_ids":       [],
        "validation_errors":     [],
        "aggregated_metrics": {
            "kpis": {"fcr_rate_pct": 75.0, "avg_handle_time_minutes": 7.0},
            "distributions": {},
        },
        "qa_report": {"dataset_verdict": "PASS", "summary": {"avg_score": 90.0}},
        "agent_insights": {"source": "llm_deliberated", "executive_summary": "ok"},
        "token_usage": {"total_tokens": 7000, "total_cost_usd": 0.01, "model": "test"},
        "decision_log": [],
    }


class TestFullExport:
    def test_all_artifacts_written(self, isolate, make_record):
        out = ExportAgent().run(_full_state(make_record))
        paths = out["export_paths"]
        assert set(paths) == {
            "csv", "summary", "full_results", "qa_report",
            "insights", "decisions", "manifest", "audit_log",
        }
        for label, path in paths.items():
            assert Path(path).exists(), label

    def test_summary_json_contains_dashboard_payload(self, isolate, make_record):
        ExportAgent().run(_full_state(make_record))
        summary = json.loads((isolate / "summary.json").read_text())
        assert summary["kpis"]["fcr_rate_pct"] == 75.0
        assert summary["agent_insights"]["source"] == "llm_deliberated"
        assert summary["token_usage"]["total_tokens"] == 7000
        assert "decision_summary" in summary

    def test_manifest_counts_and_agent_roster(self, isolate, make_record):
        out = ExportAgent().run(_full_state(make_record))
        manifest = json.loads(open(out["export_paths"]["manifest"]).read())
        assert manifest["n_analyzed"] == 2
        assert manifest["n_failed"] == 0
        assert manifest["qa_verdict"] == "PASS"
        assert "InsightsAgent" in manifest["agents_executed"]
        assert manifest["agents_executed"][-1] == "ExportAgent"

    def test_run_recorded_in_agent_memory(self, make_record):
        ExportAgent().run(_full_state(make_record))
        history = exp_mod.MEMORY.get_run_history(last_n=1)
        assert history[0]["n_analyzed"] == 2
        assert history[0]["fcr_rate_pct"] == 75.0

    def test_export_decision_included_in_artifacts(self, isolate, make_record):
        out = ExportAgent().run(_full_state(make_record))
        decisions = json.loads(open(out["export_paths"]["decisions"]).read())
        types = [r["decision_type"] for r in decisions["records"]]
        assert "export_scope" in types


class TestEmergencyExport:
    def test_summary_json_preserved_on_quality_gate_failure(self, isolate, make_record):
        # Regression: v4.1.0 fixed the emergency path clobbering summary.json
        last_good = {"kpis": {"fcr_rate_pct": 99.0}}
        (isolate / "summary.json").write_text(json.dumps(last_good))

        state = _full_state(make_record)
        state["aggregated_metrics"] = {}  # quality-gate failure path
        state["agent_insights"] = {}
        ExportAgent().run(state)

        assert json.loads((isolate / "summary.json").read_text()) == last_good

    def test_per_call_artifacts_still_written(self, isolate, make_record):
        state = _full_state(make_record)
        state["aggregated_metrics"] = {}
        out = ExportAgent().run(state)
        assert Path(out["export_paths"]["csv"]).exists()
        assert Path(out["export_paths"]["qa_report"]).exists()

    def test_manifest_excludes_downstream_agents(self, make_record):
        state = _full_state(make_record)
        state["aggregated_metrics"] = {}
        out = ExportAgent().run(state)
        manifest = json.loads(open(out["export_paths"]["manifest"]).read())
        assert "AggregationAgent" not in manifest["agents_executed"]
        assert "InsightsAgent" not in manifest["agents_executed"]
        assert "ExportAgent" in manifest["agents_executed"]
