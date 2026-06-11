"""
Tests for pipeline/agents/insights_agent.py — InsightsAgent.
All LLM calls are stubbed at the _llm_call boundary so the deliberation
routing (Analyze → Critique → Synthesize) and fallback chain run for real.
"""

import pytest

import pipeline.agents.insights_agent as ins_mod
from pipeline.agents.insights_agent import InsightsAgent, _rule_based_insights
from pipeline.memory import AgentMemory


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(ins_mod, "MEMORY", AgentMemory(path=tmp_path / "memory.json"))
    monkeypatch.setattr(ins_mod, "VECTOR_MEMORY_ENABLED", False)


KPIS = {
    "total_calls_analyzed":      20,
    "fcr_rate_pct":              62.0,
    "avg_handle_time_minutes":   9.4,
    "avoidable_call_rate_pct":   28.0,
    "agentic_ai_resolvable_pct": 41.0,
    "escalation_rate_pct":       18.0,
    "sentiment_improved_pct":    55.0,
}


def _state() -> dict:
    return {
        "aggregated_metrics": {
            "kpis": KPIS,
            "distributions": {"cost_driver": {"billing": 60.0, "technical": 40.0}},
            "cost_levers":   {"total_savings_opportunity_usd": 250_000},
        },
        "qa_report": {"dataset_verdict": "PASS", "summary": {"avg_score": 88.0}},
        "analysis_results": [],
    }


def _analyze_payload() -> dict:
    return {
        "_cot_reasoning":      "FCR is low; AHT is high.",
        "executive_summary":   "FCR of 62% is below benchmark.",
        "top_recommendations": [
            {"priority": i, "title": f"Rec {i}", "insight": "x", "estimated_impact": "y"}
            for i in range(1, 6)
        ],
        "quick_wins": ["a", "b", "c"],
        "risk_flags": ["r1", "r2"],
    }


def _stub_llm(monkeypatch, responses: list):
    """Stub _llm_call to pop canned responses in order (None = pass failed)."""
    queue = list(responses)
    calls = []

    def fake(self, prompt, temperature=0.3, usage_acc=None):
        calls.append(prompt)
        if usage_acc is not None:
            usage_acc.append({
                "provider": "stub", "model": "stub",
                "prompt_tokens": 100, "completion_tokens": 50,
            })
        return queue.pop(0) if queue else None

    monkeypatch.setattr(InsightsAgent, "_llm_call", fake)
    return calls


# ── Rule-based fallback ───────────────────────────────────────────────

class TestRuleBasedInsights:
    def test_threshold_driven_recommendations(self):
        out = _rule_based_insights(KPIS, {}, n_calls=20)
        titles = [r["title"] for r in out["top_recommendations"]]
        # Every KPI in the fixture breaches its threshold
        assert "Improve First Call Resolution" in titles
        assert "Reduce Avoidable Call Volume" in titles
        assert "Deploy Agentic AI for High-Volume Intents" in titles
        assert "Reduce Average Handle Time" in titles
        assert "Reduce Escalation Rate" in titles

    def test_healthy_kpis_padded_with_generic_recommendations(self):
        healthy = {"fcr_rate_pct": 85, "avg_handle_time_minutes": 5.0,
                   "avoidable_call_rate_pct": 5, "agentic_ai_resolvable_pct": 10,
                   "escalation_rate_pct": 5}
        out = _rule_based_insights(healthy, {}, n_calls=20)
        # The padding list holds 3 generic entries, so all-healthy KPIs yield
        # 3 recommendations — only the LLM paths guarantee exactly 5.
        recs = out["top_recommendations"]
        assert 3 <= len(recs) <= 5
        assert [r["priority"] for r in recs] == list(range(1, len(recs) + 1))

    def test_contract_fields(self):
        out = _rule_based_insights(KPIS, {}, n_calls=20)
        assert out["source"] == "rule_based_fallback"
        assert out["deliberation_passes"] == 0
        assert len(out["quick_wins"]) == 3
        assert len(out["risk_flags"]) == 2


# ── Deliberation routing ──────────────────────────────────────────────

class TestInsightsAgent:
    def test_full_deliberation_three_passes(self, monkeypatch):
        _stub_llm(monkeypatch, [
            _analyze_payload(),
            {"overall_quality": "adequate", "recommendation_grades": []},
            _analyze_payload(),
        ])
        out = InsightsAgent().run(_state())
        insights = out["agent_insights"]
        assert insights["source"] == "llm_deliberated"
        assert insights["deliberation_passes"] == 3
        assert insights["critique"] == "adequate"
        assert insights["token_usage"]["calls"] == 3
        assert insights["token_usage"]["total_prompt_tokens"] == 300

    def test_critique_failure_degrades_to_single_pass(self, monkeypatch):
        _stub_llm(monkeypatch, [_analyze_payload(), None])
        insights = InsightsAgent().run(_state())["agent_insights"]
        assert insights["source"] == "llm_single_pass"
        assert insights["deliberation_passes"] == 1

    def test_synthesis_failure_returns_post_critique_result(self, monkeypatch):
        _stub_llm(monkeypatch, [
            _analyze_payload(),
            {"overall_quality": "weak"},
            None,
        ])
        insights = InsightsAgent().run(_state())["agent_insights"]
        assert insights["source"] == "llm_single_pass"
        assert insights["deliberation_passes"] == 2

    def test_all_llm_failures_fall_back_to_rules(self, monkeypatch):
        _stub_llm(monkeypatch, [None, None])
        insights = InsightsAgent().run(_state())["agent_insights"]
        assert insights["source"] == "rule_based_fallback"
        assert insights["deliberation_passes"] == 0
        assert len(insights["top_recommendations"]) == 5

    def test_provider_decision_logged(self, monkeypatch):
        _stub_llm(monkeypatch, [
            _analyze_payload(),
            {"overall_quality": "strong"},
            _analyze_payload(),
        ])
        out = InsightsAgent().run(_state())
        provider = [d for d in out["decision_log"] if d["decision_type"] == "provider_selected"]
        assert len(provider) == 1
        deliberation = [
            d for d in out["decision_log"] if d["decision_type"] == "deliberation_outcome"
        ]
        assert len(deliberation) == 1

    def test_analyze_prompt_includes_kpis(self):
        agent = InsightsAgent()
        prompt = agent._build_analyze_prompt(
            KPIS, _state()["aggregated_metrics"], _state()["qa_report"],
            n_calls=20, historical_context="",
        )
        assert "62.0%" in prompt
        assert "$250,000" in prompt
        assert "billing" in prompt  # top cost driver resolved from distribution

    def test_analyze_prompt_safe_with_braces_in_history(self):
        # Memory text may contain braces — must not break str.format()
        agent = InsightsAgent()
        prompt = agent._build_analyze_prompt(
            KPIS, _state()["aggregated_metrics"], _state()["qa_report"],
            n_calls=20, historical_context='previous run {"fcr": 70}',
        )
        assert '{"fcr": 70}' in prompt
