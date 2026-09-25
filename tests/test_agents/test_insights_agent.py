"""
Tests for pipeline/agents/insights_agent.py — InsightsAgent.
All LLM calls are stubbed at the _llm_call boundary so the deliberation
routing (Analyze → Critique → Synthesize) and fallback chain run for real.

TestNvidiaCall/TestClaudeCall/TestLlmCallFallback go one layer deeper and
stub the provider SDK clients themselves (get_nvidia_client/get_anthropic_
client), so the NVIDIA→Claude fallback logic and the circuit breaker are
exercised directly rather than assumed correct via the higher-level stub.
"""

from unittest.mock import MagicMock

import pytest

import pipeline.agents.insights_agent as ins_mod
from pipeline.agents.insights_agent import InsightsAgent, _rule_based_insights
from pipeline.circuit_breaker import CircuitBreaker
from pipeline.memory import AgentMemory


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(ins_mod, "MEMORY", AgentMemory(path=tmp_path / "memory.json"))
    monkeypatch.setattr(ins_mod, "VECTOR_MEMORY_ENABLED", False)
    # Fresh, untripped breaker per test — the module-level singleton would
    # otherwise leak a trip from one test into the next via its sentinel file.
    monkeypatch.setattr(ins_mod, "_nvidia_breaker", CircuitBreaker(tmp_path / "nvidia_down"))


KPIS = {
    "total_calls_analyzed": 20,
    "fcr_rate_pct": 62.0,
    "avg_handle_time_minutes": 9.4,
    "avoidable_call_rate_pct": 28.0,
    "agentic_ai_resolvable_pct": 41.0,
    "escalation_rate_pct": 18.0,
    "sentiment_improved_pct": 55.0,
}


def _state() -> dict:
    return {
        "aggregated_metrics": {
            "kpis": KPIS,
            "distributions": {"cost_driver": {"billing": 60.0, "technical": 40.0}},
            "cost_levers": {"total_savings_opportunity_usd": 250_000},
        },
        "qa_report": {"dataset_verdict": "PASS", "summary": {"avg_score": 88.0}},
        "analysis_results": [],
    }


def _analyze_payload() -> dict:
    return {
        "_cot_reasoning": "FCR is low; AHT is high.",
        "executive_summary": "FCR of 62% is below benchmark.",
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

    def fake(self, prompt, temperature=0.3, usage_acc=None, **_kwargs):
        calls.append(prompt)
        if usage_acc is not None:
            usage_acc.append(
                {
                    "provider": "stub",
                    "model": "stub",
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                }
            )
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
        healthy = {
            "fcr_rate_pct": 85,
            "avg_handle_time_minutes": 5.0,
            "avoidable_call_rate_pct": 5,
            "agentic_ai_resolvable_pct": 10,
            "escalation_rate_pct": 5,
        }
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
        _stub_llm(
            monkeypatch,
            [
                _analyze_payload(),
                {"overall_quality": "adequate", "recommendation_grades": []},
                _analyze_payload(),
            ],
        )
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
        _stub_llm(
            monkeypatch,
            [
                _analyze_payload(),
                {"overall_quality": "weak"},
                None,
            ],
        )
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
        _stub_llm(
            monkeypatch,
            [
                _analyze_payload(),
                {"overall_quality": "strong"},
                _analyze_payload(),
            ],
        )
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
            KPIS,
            _state()["aggregated_metrics"],
            _state()["qa_report"],
            n_calls=20,
            historical_context="",
        )
        assert "62.0%" in prompt
        assert "$250,000" in prompt
        assert "billing" in prompt  # top cost driver resolved from distribution

    def test_analyze_prompt_safe_with_braces_in_history(self):
        # Memory text may contain braces — must not break str.format()
        agent = InsightsAgent()
        prompt = agent._build_analyze_prompt(
            KPIS,
            _state()["aggregated_metrics"],
            _state()["qa_report"],
            n_calls=20,
            historical_context='previous run {"fcr": 70}',
        )
        assert '{"fcr": 70}' in prompt


# ── NVIDIA NIM call (provider seam) ─────────────────────────────────────


def _fake_nvidia_response(content: str, prompt_tokens=100, completion_tokens=50):
    return MagicMock(
        choices=[MagicMock(message=MagicMock(content=content))],
        usage=MagicMock(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


class TestNvidiaCall:
    def test_missing_api_key_returns_none_without_calling_client(self, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        mock_get_client = MagicMock()
        monkeypatch.setattr(ins_mod, "get_nvidia_client", mock_get_client)
        assert InsightsAgent()._nvidia_call("prompt") is None
        mock_get_client.assert_not_called()

    def test_tripped_breaker_skips_call(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
        ins_mod._nvidia_breaker.trip()
        mock_get_client = MagicMock()
        monkeypatch.setattr(ins_mod, "get_nvidia_client", mock_get_client)
        assert InsightsAgent()._nvidia_call("prompt") is None
        mock_get_client.assert_not_called()

    def test_success_parses_json_and_records_usage(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
        client = MagicMock()
        client.chat.completions.create.return_value = _fake_nvidia_response(
            '{"executive_summary": "ok"}'
        )
        monkeypatch.setattr(ins_mod, "get_nvidia_client", lambda timeout_s: client)
        usage_acc = []
        result = InsightsAgent()._nvidia_call("prompt", usage_acc=usage_acc)
        assert result["executive_summary"] == "ok"
        assert usage_acc == [
            {
                "provider": "nvidia_nim",
                "model": ins_mod.INSIGHTS_MODEL,
                "prompt_tokens": 100,
                "completion_tokens": 50,
            }
        ]

    def test_timeout_trips_breaker_and_returns_none(self, monkeypatch):
        import httpx
        import openai

        monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
        client = MagicMock()
        client.chat.completions.create.side_effect = openai.APITimeoutError(
            httpx.Request("POST", "https://nvidia.example/v1/chat")
        )
        monkeypatch.setattr(ins_mod, "get_nvidia_client", lambda timeout_s: client)
        assert InsightsAgent()._nvidia_call("prompt") is None
        assert ins_mod._nvidia_breaker.tripped is True

    def test_quota_exhausted_429_does_not_trip_breaker(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("429 rate limited")
        monkeypatch.setattr(ins_mod, "get_nvidia_client", lambda timeout_s: client)
        assert InsightsAgent()._nvidia_call("prompt") is None
        # A quota blip is transient, not "provider is down" — must not trip
        # the breaker and skip a provider that may work again next pass.
        assert ins_mod._nvidia_breaker.tripped is False


# ── Claude call (fallback provider) ──────────────────────────────────────


def _fake_claude_response(text: str, input_tokens=80, output_tokens=40):
    return MagicMock(
        content=[MagicMock(text=text)],
        usage=MagicMock(input_tokens=input_tokens, output_tokens=output_tokens),
    )


class TestClaudeCall:
    def test_missing_api_key_returns_none_without_calling_client(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        mock_get_client = MagicMock()
        monkeypatch.setattr(ins_mod, "get_anthropic_client", mock_get_client)
        assert InsightsAgent()._claude_call("prompt") is None
        mock_get_client.assert_not_called()

    def test_success_strips_markdown_fences_and_parses(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        client = MagicMock()
        client.messages.create.return_value = _fake_claude_response(
            '```json\n{"executive_summary": "ok"}\n```'
        )
        monkeypatch.setattr(ins_mod, "get_anthropic_client", lambda timeout_s: client)
        usage_acc = []
        result = InsightsAgent()._claude_call("prompt", usage_acc=usage_acc)
        assert result["executive_summary"] == "ok"
        assert usage_acc[0]["provider"] == "anthropic"

    def test_call_failure_returns_none(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        client = MagicMock()
        client.messages.create.side_effect = RuntimeError("connection reset")
        monkeypatch.setattr(ins_mod, "get_anthropic_client", lambda timeout_s: client)
        assert InsightsAgent()._claude_call("prompt") is None


# ── _llm_call: NVIDIA → Claude fallback wiring ───────────────────────────


class TestLlmCallFallback:
    def test_nvidia_success_skips_claude(self, monkeypatch):
        agent = InsightsAgent()
        monkeypatch.setattr(agent, "_nvidia_call", lambda *a, **k: {"source": "nvidia"})
        claude_call = MagicMock()
        monkeypatch.setattr(agent, "_claude_call", claude_call)
        result = agent._llm_call("prompt")
        assert result == {"source": "nvidia"}
        claude_call.assert_not_called()

    def test_nvidia_failure_falls_back_to_claude(self, monkeypatch):
        agent = InsightsAgent()
        monkeypatch.setattr(agent, "_nvidia_call", lambda *a, **k: None)
        monkeypatch.setattr(agent, "_claude_call", lambda *a, **k: {"source": "claude"})
        assert agent._llm_call("prompt") == {"source": "claude"}

    def test_both_providers_fail_returns_none(self, monkeypatch):
        agent = InsightsAgent()
        monkeypatch.setattr(agent, "_nvidia_call", lambda *a, **k: None)
        monkeypatch.setattr(agent, "_claude_call", lambda *a, **k: None)
        assert agent._llm_call("prompt") is None


# ── _get_rich_context: vector-memory augmentation ────────────────────────


class TestGetRichContext:
    def test_disabled_returns_flat_context_only(self, monkeypatch):
        monkeypatch.setattr(ins_mod, "VECTOR_MEMORY_ENABLED", False)
        ctx = InsightsAgent()._get_rich_context(KPIS, n_calls=20)
        assert ctx == ins_mod.MEMORY.get_context_for_insights()

    def test_enabled_empty_store_returns_flat_context_only(self, monkeypatch):
        monkeypatch.setattr(ins_mod, "VECTOR_MEMORY_ENABLED", True)
        mock_store = MagicMock(size=0)
        monkeypatch.setattr("pipeline.vector_memory.VECTOR_STORE", mock_store)
        ctx = InsightsAgent()._get_rich_context(KPIS, n_calls=20)
        assert ctx == ins_mod.MEMORY.get_context_for_insights()
        mock_store.format_context.assert_not_called()

    def test_enabled_nonempty_store_appends_vector_context(self, monkeypatch):
        monkeypatch.setattr(ins_mod, "VECTOR_MEMORY_ENABLED", True)
        mock_store = MagicMock(size=3)
        mock_store.format_context.return_value = "similar run: FCR 65%"
        monkeypatch.setattr("pipeline.vector_memory.VECTOR_STORE", mock_store)
        ctx = InsightsAgent()._get_rich_context(KPIS, n_calls=20)
        assert "similar run: FCR 65%" in ctx

    def test_vector_store_failure_falls_back_to_flat_context(self, monkeypatch):
        """Vector memory is enrichment, not a dependency — a broken vector
        store must never take down InsightsAgent's historical context."""
        monkeypatch.setattr(ins_mod, "VECTOR_MEMORY_ENABLED", True)
        mock_store = MagicMock(size=3)
        mock_store.format_context.side_effect = RuntimeError("index corrupt")
        monkeypatch.setattr("pipeline.vector_memory.VECTOR_STORE", mock_store)
        ctx = InsightsAgent()._get_rich_context(KPIS, n_calls=20)
        assert ctx == ins_mod.MEMORY.get_context_for_insights()
