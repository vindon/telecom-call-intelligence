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

from pipeline.analyzer import analyze_batch
from pipeline.logger   import get_logger

log = get_logger(__name__)


class ExtractionAgent:
    """Stateless agent — instantiate once and call run() per pipeline invocation."""

    name = "ExtractionAgent"

    def run(self, state: dict) -> dict:
        transcripts   = state["validated_transcripts"]
        delay         = state.get("inter_call_delay", 2.0)
        checkpoint_key = state.get("checkpoint_key", "")

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

        log.info(
            "[%s] Extraction complete: %d OK  %d failed",
            self.name, len(results), len(failed),
        )

        return {
            **state,
            "analysis_results": results,
            "failed_call_ids":  failed,
        }
