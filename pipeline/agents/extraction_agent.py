"""
ExtractionAgent  —  Agent 2 of 6
-----------------------------------
Drives the Gemini 2.5 Flash Lite structured JSON extraction for every validated
transcript. This agent is the primary LLM consumer in the pipeline.

Responsibilities:
  • Manage the Gemini API client and system prompt lifecycle
  • Submit each transcript to Gemini with native JSON mode
  • Handle 429 rate limits with exponential backoff
  • Append successful results to the per-batch checkpoint file
  • Resume cleanly from a partial checkpoint after an interrupted run
  • Inject token-usage fields (_prompt_tokens, _completion_tokens, _total_tokens)
    and turn-count metadata into every result dict

Outputs injected into PipelineState:
  analysis_results  — list of extracted JSON dicts (one per successful call)
  failed_call_ids   — call IDs that could not be extracted after all retries
"""

import time

from pipeline.analyzer   import analyze_batch
from pipeline.governance import AUDIT_LOG, BUDGET_GUARD
from pipeline.logger     import get_logger
from pipeline.memory     import MEMORY

log = get_logger(__name__)


class ExtractionAgent:
    """Stateless agent — instantiate once and call run() per pipeline invocation."""

    name = "ExtractionAgent"

    def run(self, state: dict) -> dict:
        t0             = time.monotonic()
        transcripts    = state["validated_transcripts"]
        delay          = state.get("inter_call_delay", 2.0)
        checkpoint_key = state.get("checkpoint_key", "")

        AUDIT_LOG.record_agent_start(
            self.name,
            {"n_transcripts": len(transcripts), "checkpoint_key": checkpoint_key},
        )
        log.info(
            "[%s] Starting extraction: %d transcripts  checkpoint='%s'",
            self.name, len(transcripts), checkpoint_key or "none",
        )

        results = analyze_batch(
            transcripts,
            inter_call_delay=delay,
            checkpoint_key=checkpoint_key,
        )

        result_ids = {r.get("call_id") for r in results}
        failed = [
            t["call_id"]
            for t in transcripts
            if t["call_id"] not in result_ids
        ]

        # Record failures in agent memory for pattern analysis
        if failed:
            MEMORY.record_failures(failed, context=f"checkpoint={checkpoint_key}")

        # Budget check — uses token usage already injected into results
        total_tokens = sum(r.get("_total_tokens", 0) for r in results)
        # Approx cost: $0.10/MTok input + $0.40/MTok output (gemini-2.5-flash-lite)
        est_cost = total_tokens / 1_000_000 * 0.10
        try:
            BUDGET_GUARD.check(est_cost, context=f"after {len(results)} calls")
            AUDIT_LOG.record_governance(
                check="budget", passed=True,
                details={"est_cost_usd": round(est_cost, 4), "limit_usd": BUDGET_GUARD.max_cost_usd},
            )
        except BUDGET_GUARD.BudgetExceededError as exc:
            AUDIT_LOG.record_governance(
                check="budget", passed=False,
                details={"est_cost_usd": round(est_cost, 4), "limit_usd": BUDGET_GUARD.max_cost_usd},
            )
            AUDIT_LOG.record_error(self.name, str(exc))
            raise

        log.info(
            "[%s] Extraction complete: %d OK  %d failed",
            self.name, len(results), len(failed),
        )
        AUDIT_LOG.record_agent_end(
            self.name,
            {"n_ok": len(results), "n_failed": len(failed)},
            elapsed_s=time.monotonic() - t0,
        )

        return {
            **state,
            "analysis_results": results,
            "failed_call_ids":  failed,
        }
