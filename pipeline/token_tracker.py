"""
token_tracker.py
----------------
Token usage accounting and cost estimation for Groq API calls.

Pricing source: https://console.groq.com/docs/pricing
Model: llama-3.3-70b-versatile
Last verified: 2025-Q2 — re-check if running at scale.

Usage:
  from pipeline.token_tracker import token_summary
  summary = token_summary(results)   # results = list[dict] from analyze_batch
"""

# ── Pricing (USD per million tokens) ─────────────────────────────────
# llama-3.3-70b-versatile on Groq
PRICE_INPUT_PER_MTOK  = 0.59
PRICE_OUTPUT_PER_MTOK = 0.79
MODEL                 = "llama-3.3-70b-versatile"
PROVIDER              = "Groq"


def cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    """Compute USD cost for a single API call."""
    return (
        prompt_tokens    / 1_000_000 * PRICE_INPUT_PER_MTOK  +
        completion_tokens / 1_000_000 * PRICE_OUTPUT_PER_MTOK
    )


def token_summary(results: list[dict]) -> dict:
    """
    Build a token-usage and cost summary from a list of per-call result dicts.

    Expects _prompt_tokens and _completion_tokens keys injected by analyzer.py.
    Missing values are treated as 0 (graceful degradation if Groq omits usage).

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

    return {
        "model":                      MODEL,
        "provider":                   PROVIDER,
        "calls_with_usage":           n - missing,
        "calls_missing_usage":        missing,
        # ── Totals ──────────────────────────────────────────────────
        "total_prompt_tokens":        total_prompt,
        "total_completion_tokens":    total_completion,
        "total_tokens":               total_tokens,
        # ── Per-call averages ────────────────────────────────────────
        "avg_prompt_tokens_per_call":     round(total_prompt     / (n - missing), 0) if n > missing else 0,
        "avg_completion_tokens_per_call": round(total_completion / (n - missing), 0) if n > missing else 0,
        "avg_total_tokens_per_call":      round(total_tokens     / (n - missing), 0) if n > missing else 0,
        # ── Cost ────────────────────────────────────────────────────
        "total_cost_usd":             round(total_cost, 4),
        "avg_cost_per_call_usd":      round(total_cost / (n - missing), 6) if n > missing else 0,
        # ── Pricing metadata ─────────────────────────────────────────
        "price_input_per_mtok_usd":   PRICE_INPUT_PER_MTOK,
        "price_output_per_mtok_usd":  PRICE_OUTPUT_PER_MTOK,
        "pricing_note":               (
            f"Prices as of 2025-Q2. Verify at https://console.groq.com/docs/pricing. "
            f"At 100K calls/mo avg {round(total_tokens/(n-missing) if n>missing else 0):,} tokens/call, "
            f"monthly inference cost ≈ ${round(total_cost / max(n-missing,1) * 100_000, 2):,.2f} USD."
        ),
    }
