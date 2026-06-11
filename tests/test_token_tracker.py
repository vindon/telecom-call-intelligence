"""
Tests for pipeline/token_tracker.py — pricing resolution, per-call cost,
and the token_summary() report embedded in summary.json.
All pure unit tests: no API calls, no filesystem access.
"""

from pipeline.config import EXTRACTION_MODEL
from pipeline.token_tracker import (
    MODEL,
    PRICE_INPUT_PER_MTOK,
    PRICE_OUTPUT_PER_MTOK,
    _resolve_pricing,
    cost_usd,
    token_summary,
)

# ── Pricing resolution ────────────────────────────────────────────────

class TestResolvePricing:
    def test_claude_haiku_prefix(self):
        in_rate, out_rate, provider, _ = _resolve_pricing("claude-haiku-4-5-20251001")
        assert (in_rate, out_rate) == (0.80, 4.00)
        assert "Anthropic" in provider

    def test_generic_claude_prefix(self):
        in_rate, out_rate, provider, _ = _resolve_pricing("claude-opus-4-8")
        assert (in_rate, out_rate) == (0.80, 4.00)
        assert "Anthropic" in provider

    def test_gemini_25_prefix(self):
        in_rate, out_rate, provider, _ = _resolve_pricing("gemini-2.5-flash-lite")
        assert (in_rate, out_rate) == (0.10, 0.40)
        assert "Google" in provider

    def test_unknown_model_falls_back_to_gemini_rates(self):
        in_rate, out_rate, provider, note = _resolve_pricing("gpt-4o")
        assert (in_rate, out_rate) == (0.10, 0.40)
        assert provider == "Unknown provider"
        assert "unknown" in note.lower()

    def test_module_constants_match_configured_model(self):
        assert MODEL == EXTRACTION_MODEL
        expected = _resolve_pricing(EXTRACTION_MODEL)
        assert (PRICE_INPUT_PER_MTOK, PRICE_OUTPUT_PER_MTOK) == expected[:2]


# ── cost_usd ──────────────────────────────────────────────────────────

class TestCostUsd:
    def test_one_million_tokens_each(self):
        assert cost_usd(1_000_000, 1_000_000) == PRICE_INPUT_PER_MTOK + PRICE_OUTPUT_PER_MTOK

    def test_zero_tokens_is_free(self):
        assert cost_usd(0, 0) == 0.0

    def test_output_tokens_cost_more_than_input(self):
        # Holds for every provider in the pricing map
        assert cost_usd(0, 10_000) > cost_usd(10_000, 0)


# ── token_summary ─────────────────────────────────────────────────────

class TestTokenSummary:
    def test_empty_results_returns_error(self):
        assert token_summary([]) == {"error": "no results to summarise"}

    def test_totals_and_averages(self):
        results = [
            {"_prompt_tokens": 1000, "_completion_tokens": 500},
            {"_prompt_tokens": 3000, "_completion_tokens": 1500},
        ]
        s = token_summary(results)
        assert s["total_prompt_tokens"] == 4000
        assert s["total_completion_tokens"] == 2000
        assert s["total_tokens"] == 6000
        assert s["calls_with_usage"] == 2
        assert s["calls_missing_usage"] == 0
        assert s["avg_prompt_tokens_per_call"] == 2000
        assert s["avg_total_tokens_per_call"] == 3000
        assert s["total_cost_usd"] == round(cost_usd(4000, 2000), 4)

    def test_missing_usage_excluded_from_averages(self):
        results = [
            {"_prompt_tokens": 1000, "_completion_tokens": 500},
            {"call_id": "no-usage-call"},  # API omitted usage metadata
        ]
        s = token_summary(results)
        assert s["calls_with_usage"] == 1
        assert s["calls_missing_usage"] == 1
        # Averages divide by calls_with_usage, not len(results)
        assert s["avg_prompt_tokens_per_call"] == 1000

    def test_all_missing_usage_degrades_gracefully(self):
        s = token_summary([{"call_id": "a"}, {"call_id": "b"}])
        assert s["calls_with_usage"] == 0
        assert s["avg_total_tokens_per_call"] == 0
        assert s["avg_cost_per_call_usd"] == 0
        assert s["total_cost_usd"] == 0.0

    def test_pricing_metadata_present(self):
        s = token_summary([{"_prompt_tokens": 100, "_completion_tokens": 50}])
        assert s["model"] == EXTRACTION_MODEL
        assert s["price_input_per_mtok_usd"] == PRICE_INPUT_PER_MTOK
        assert s["price_output_per_mtok_usd"] == PRICE_OUTPUT_PER_MTOK
        assert "monthly inference cost" in s["pricing_note"]
