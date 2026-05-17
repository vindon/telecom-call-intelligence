"""
token_tracker.py
----------------
Token usage accounting and cost estimation for Google AI Studio (Gemini) API calls.

Pricing source: https://ai.google.dev/pricing
Model: gemini-2.5-flash-lite
Last verified: 2026-Q2 — re-check if running at scale.

Free tier note:
  Gemini 2.5 Flash Lite is free up to 500 req/day via Google AI Studio.
  The pricing below applies to the paid (Google Cloud Vertex AI) tier.
  At 100 calls/run, cost on the paid tier is ~$0.04 — effectively negligible.

Usage:
  from pipeline.token_tracker import token_summary
  summary = token_summary(results)   # results = list[dict] from analyze_batch
"""

# ── Pricing (USD per million tokens) ─────────────────────────────────
# gemini-2.0-flash on Google AI Studio / Vertex AI
PRICE_INPUT_PER_MTOK  = 0.10
PRICE_OUTPUT_PER_MTOK = 0.40
MODEL                 = "gemini-2.5-flash-lite"
PROVIDER              = "Google AI Studio"


def cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    """Compute USD cost for a single API call (paid tier pricing)."""
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
        # ── Cost (paid tier) ─────────────────────────────────────────
        "total_cost_usd":                 round(total_cost, 4),
        "avg_cost_per_call_usd":          round(total_cost / calls_with_usage, 6) if calls_with_usage else 0,
        # ── Pricing metadata ─────────────────────────────────────────
        "price_input_per_mtok_usd":       PRICE_INPUT_PER_MTOK,
        "price_output_per_mtok_usd":      PRICE_OUTPUT_PER_MTOK,
        "free_tier_note":                 "Free up to 500 req/day via Google AI Studio. Paid tier pricing shown above.",
        "pricing_note": (
            f"Gemini 2.5 Flash Lite paid tier pricing as of 2026-Q2. "
            f"At 100K calls/mo avg {round(total_tokens / calls_with_usage if calls_with_usage else 0):,} tokens/call, "
            f"monthly inference cost ≈ ${round(total_cost / max(calls_with_usage, 1) * 100_000, 2):,.2f} USD."
        ),
    }
