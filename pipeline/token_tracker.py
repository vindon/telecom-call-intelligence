"""
token_tracker.py
----------------
Token usage accounting and cost estimation.

Pricing is driven by EXTRACTION_MODEL in pipeline/config.py — change the
model there and the cost estimates update automatically.

Provider / pricing map (USD per million tokens, as of 2026-Q2):
  claude-haiku-*     : $0.80 in / $4.00 out  (Anthropic)
  gemini-2.5-flash-* : $0.10 in / $0.40 out  (Google AI Studio paid tier; free up to 500 RPD)
  gemini-2.0-flash-* : $0.10 in / $0.40 out  (Google AI Studio paid tier; free up to 1500 RPD)
  gemini-*           : $0.10 in / $0.40 out  (generic Gemini fallback pricing)

Usage:
  from pipeline.token_tracker import token_summary
  summary = token_summary(results)   # results = list[dict] from analyze_batch
"""

from pipeline.config import EXTRACTION_MODEL

# ── Provider / pricing resolution ────────────────────────────────────

_PRICING: dict[str, tuple[float, float, str, str]] = {
    # prefix → (input_per_mtok, output_per_mtok, provider_label, tier_note)
    "claude-haiku": (0.80, 4.00, "Anthropic (Claude)", "Paid tier pricing — no free tier for Claude Haiku."),
    "claude":       (0.80, 4.00, "Anthropic (Claude)", "Paid tier pricing."),
    "gemini-2.5":   (0.10, 0.40, "Google AI Studio",   "Free up to 500 req/day. Paid tier pricing shown."),
    "gemini-2.0":   (0.10, 0.40, "Google AI Studio",   "Free up to 1500 req/day. Paid tier pricing shown."),
    "gemini":       (0.10, 0.40, "Google AI Studio",   "Paid tier pricing shown."),
}


def _resolve_pricing(model: str) -> tuple[float, float, str, str]:
    for prefix, values in _PRICING.items():
        if model.startswith(prefix):
            return values
    return (0.10, 0.40, "Unknown provider", "Pricing unknown — defaulting to Gemini rates.")


PRICE_INPUT_PER_MTOK, PRICE_OUTPUT_PER_MTOK, PROVIDER, _TIER_NOTE = _resolve_pricing(EXTRACTION_MODEL)
MODEL = EXTRACTION_MODEL


def cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    """Compute USD cost for a single API call using the configured model's pricing."""
    return (
        prompt_tokens     / 1_000_000 * PRICE_INPUT_PER_MTOK  +
        completion_tokens / 1_000_000 * PRICE_OUTPUT_PER_MTOK
    )


def token_summary(results: list[dict]) -> dict:
    """
    Build a token-usage and cost summary from a list of per-call result dicts.

    Expects _prompt_tokens and _completion_tokens keys injected by analyzer.py.
    Missing values are treated as 0 (graceful degradation if API omits usage).

    Returns:
        dict ready to embed in summary.json / run_manifest.json
    """
    n = len(results)
    if n == 0:
        return {"error": "no results to summarise"}

    total_prompt     = sum(r.get("_prompt_tokens",     0) for r in results)
    total_completion = sum(r.get("_completion_tokens", 0) for r in results)
    total_tokens     = total_prompt + total_completion
    total_cost       = cost_usd(total_prompt, total_completion)
    missing          = sum(1 for r in results if "_prompt_tokens" not in r)
    calls_with_usage = n - missing

    return {
        "model":                          MODEL,
        "provider":                       PROVIDER,
        "calls_with_usage":               calls_with_usage,
        "calls_missing_usage":            missing,
        # ── Totals ──────────────────────────────────────────────────
        "total_prompt_tokens":            total_prompt,
        "total_completion_tokens":        total_completion,
        "total_tokens":                   total_tokens,
        # ── Per-call averages ────────────────────────────────────────
        "avg_prompt_tokens_per_call":     round(total_prompt     / calls_with_usage, 0) if calls_with_usage else 0,
        "avg_completion_tokens_per_call": round(total_completion / calls_with_usage, 0) if calls_with_usage else 0,
        "avg_total_tokens_per_call":      round(total_tokens     / calls_with_usage, 0) if calls_with_usage else 0,
        # ── Cost ────────────────────────────────────────────────────
        "total_cost_usd":                 round(total_cost, 4),
        "avg_cost_per_call_usd":          round(total_cost / calls_with_usage, 6) if calls_with_usage else 0,
        # ── Pricing metadata ─────────────────────────────────────────
        "price_input_per_mtok_usd":       PRICE_INPUT_PER_MTOK,
        "price_output_per_mtok_usd":      PRICE_OUTPUT_PER_MTOK,
        "pricing_note": (
            f"{MODEL} · {_TIER_NOTE} "
            f"At 100K calls/mo avg {round(total_tokens / calls_with_usage if calls_with_usage else 0):,} tokens/call, "
            f"monthly inference cost ≈ ${round(total_cost / max(calls_with_usage, 1) * 100_000, 2):,.2f} USD."
        ),
    }
