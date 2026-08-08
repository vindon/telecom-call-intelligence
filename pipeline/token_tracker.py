"""
token_tracker.py
----------------
Token usage accounting and cost estimation.

Pricing is driven by EXTRACTION_MODEL in pipeline/config.py — change the
model there and the cost estimates update automatically.

Provider / pricing map (USD per million tokens, verified against
platform.claude.com/docs/en/about-claude/pricing, 2026-08-08):
  claude-haiku-*     : $1.00 in / $5.00 out  (Anthropic)
  gemini-2.5-flash-* : $0.10 in / $0.40 out  (Google AI Studio paid tier; free up to 500 RPD)
  gemini-2.0-flash-* : $0.10 in / $0.40 out  (Google AI Studio paid tier; free up to 1500 RPD)
  gemini-*           : $0.10 in / $0.40 out  (generic Gemini fallback pricing)

Prompt caching (Claude only — see analyzer._call_claude, which caches the
system prompt with a 1-hour TTL):
  Cache write (1h)   : 2x the base input rate
  Cache read (hit)   : 0.1x the base input rate
Cache tokens are reported separately by the API (cache_creation_input_tokens /
cache_read_input_tokens) and must never be priced at the base input rate —
doing so both overstates BudgetGuard's spend estimate and understates the
savings caching is there to produce.

Usage:
  from pipeline.token_tracker import token_summary
  summary = token_summary(results)   # results = list[dict] from analyze_batch
"""

from pipeline.config import EXTRACTION_MODEL

# ── Provider / pricing resolution ────────────────────────────────────

_PRICING: dict[str, tuple[float, float, str, str]] = {
    # prefix → (input_per_mtok, output_per_mtok, provider_label, tier_note)
    "claude-haiku": (1.00, 5.00, "Anthropic (Claude)", "Paid tier pricing — no free tier for Claude Haiku."),
    "claude":       (1.00, 5.00, "Anthropic (Claude)", "Paid tier pricing."),
    "gemini-2.5":   (0.10, 0.40, "Google AI Studio",   "Free up to 500 req/day. Paid tier pricing shown."),
    "gemini-2.0":   (0.10, 0.40, "Google AI Studio",   "Free up to 1500 req/day. Paid tier pricing shown."),
    "gemini":       (0.10, 0.40, "Google AI Studio",   "Paid tier pricing shown."),
}

# Prompt-cache pricing multipliers, relative to PRICE_INPUT_PER_MTOK.
# analyzer._call_claude uses a 1-hour cache TTL (robust across a multi-minute
# batch run); read pricing is fixed regardless of which TTL wrote the cache.
CACHE_WRITE_MULTIPLIER_1H = 2.0
CACHE_WRITE_MULTIPLIER_5M = 1.25
CACHE_READ_MULTIPLIER     = 0.1


def _resolve_pricing(model: str) -> tuple[float, float, str, str]:
    for prefix, values in _PRICING.items():
        if model.startswith(prefix):
            return values
    return (0.10, 0.40, "Unknown provider", "Pricing unknown — defaulting to Gemini rates.")


PRICE_INPUT_PER_MTOK, PRICE_OUTPUT_PER_MTOK, PROVIDER, _TIER_NOTE = _resolve_pricing(EXTRACTION_MODEL)
MODEL = EXTRACTION_MODEL


def cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """
    Compute USD cost for a single API call using the configured model's pricing.

    prompt_tokens / completion_tokens: standard (non-cached) input/output tokens,
      billed at the full input/output rate.
    cache_creation_tokens: input tokens written to the prompt cache this call —
      billed at CACHE_WRITE_MULTIPLIER_1H x the input rate.
    cache_read_tokens: input tokens served from an existing cache hit —
      billed at CACHE_READ_MULTIPLIER (10%) of the input rate.

    Cache params default to 0, so existing callers passing only
    (prompt_tokens, completion_tokens) are unaffected.
    """
    return (
        prompt_tokens          / 1_000_000 * PRICE_INPUT_PER_MTOK +
        completion_tokens      / 1_000_000 * PRICE_OUTPUT_PER_MTOK +
        cache_creation_tokens  / 1_000_000 * PRICE_INPUT_PER_MTOK * CACHE_WRITE_MULTIPLIER_1H +
        cache_read_tokens      / 1_000_000 * PRICE_INPUT_PER_MTOK * CACHE_READ_MULTIPLIER
    )


def token_summary(results: list[dict]) -> dict:
    """
    Build a token-usage and cost summary from a list of per-call result dicts.

    Expects _prompt_tokens and _completion_tokens keys injected by analyzer.py,
    plus optional _cache_creation_tokens / _cache_read_tokens when prompt
    caching was active for that call. Missing values are treated as 0
    (graceful degradation if the API omits usage, or caching wasn't used).

    Returns:
        dict ready to embed in summary.json / run_manifest.json
    """
    n = len(results)
    if n == 0:
        return {"error": "no results to summarise"}

    total_prompt         = sum(r.get("_prompt_tokens",         0) for r in results)
    total_completion     = sum(r.get("_completion_tokens",     0) for r in results)
    total_cache_creation = sum(r.get("_cache_creation_tokens", 0) for r in results)
    total_cache_read     = sum(r.get("_cache_read_tokens",     0) for r in results)
    total_tokens         = total_prompt + total_completion + total_cache_creation + total_cache_read
    total_cost           = cost_usd(total_prompt, total_completion, total_cache_creation, total_cache_read)
    missing              = sum(1 for r in results if "_prompt_tokens" not in r)
    calls_with_usage     = n - missing

    # What those cache reads would have cost at the full input rate, minus what
    # they actually cost — the concrete dollar saving prompt caching produced.
    cache_read_savings_usd = round(
        total_cache_read / 1_000_000 * PRICE_INPUT_PER_MTOK * (1 - CACHE_READ_MULTIPLIER), 4
    )

    return {
        "model":                          MODEL,
        "provider":                       PROVIDER,
        "calls_with_usage":               calls_with_usage,
        "calls_missing_usage":            missing,
        # ── Totals ──────────────────────────────────────────────────
        "total_prompt_tokens":            total_prompt,
        "total_completion_tokens":        total_completion,
        "total_cache_creation_tokens":    total_cache_creation,
        "total_cache_read_tokens":        total_cache_read,
        "total_tokens":                   total_tokens,
        # ── Per-call averages ────────────────────────────────────────
        "avg_prompt_tokens_per_call":     round(total_prompt     / calls_with_usage, 0) if calls_with_usage else 0,
        "avg_completion_tokens_per_call": round(total_completion / calls_with_usage, 0) if calls_with_usage else 0,
        "avg_total_tokens_per_call":      round(total_tokens     / calls_with_usage, 0) if calls_with_usage else 0,
        # ── Cost ────────────────────────────────────────────────────
        "total_cost_usd":                 round(total_cost, 4),
        "avg_cost_per_call_usd":          round(total_cost / calls_with_usage, 6) if calls_with_usage else 0,
        "cache_read_savings_usd":         cache_read_savings_usd,
        # ── Pricing metadata ─────────────────────────────────────────
        "price_input_per_mtok_usd":       PRICE_INPUT_PER_MTOK,
        "price_output_per_mtok_usd":      PRICE_OUTPUT_PER_MTOK,
        "pricing_note": (
            f"{MODEL} · {_TIER_NOTE} "
            f"At 100K calls/mo avg {round(total_tokens / calls_with_usage if calls_with_usage else 0):,} tokens/call, "
            f"monthly inference cost ≈ ${round(total_cost / max(calls_with_usage, 1) * 100_000, 2):,.2f} USD."
        ),
    }
