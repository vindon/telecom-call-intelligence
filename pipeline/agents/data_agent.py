"""
DataIngestionAgent  —  Agent 1 of 6
--------------------------------------
Responsible for all data acquisition and quality gating before inference.

Responsibilities:
  • Stream transcripts from the HuggingFace talkmap/telecom-conversation-corpus
  • Apply offset-based batching for non-overlapping parallel batch runs
  • Enforce minimum quality thresholds (length, turn count, non-empty)
  • Emit validation_errors for skipped transcripts

Outputs injected into PipelineState:
  raw_transcripts       — all fetched transcript dicts
  validated_transcripts — quality-gated subset ready for extraction
  validation_errors     — list of rejection reasons
"""

from pipeline.hf_loader import load_telecom_transcripts
from pipeline.logger    import get_logger

log = get_logger(__name__)

MIN_TRANSCRIPT_CHARS = 150
MIN_TURN_COUNT       = 4


class DataIngestionAgent:
    """Stateless agent — instantiate once and call run() per pipeline invocation."""

    name = "DataIngestionAgent"

    def run(self, state: dict) -> dict:
        n      = state["n_calls"]
        seed   = state["seed"]
        offset = state.get("offset", 0)

        log.info("[%s] Fetching n=%d  seed=%d  offset=%d", self.name, n, seed, offset)

        raw = load_telecom_transcripts(n=n, seed=seed, offset=offset)
        log.info("[%s] Fetched %d transcripts", self.name, len(raw))

        valid:  list[dict] = []
        errors: list[str]  = []

        for t in raw:
            call_id = t.get("call_id", "UNKNOWN")

            if not t.get("transcript_text"):
                errors.append(f"{call_id}: empty transcript")
                continue

            if len(t["transcript_text"]) < MIN_TRANSCRIPT_CHARS:
                errors.append(
                    f"{call_id}: transcript too short ({len(t['transcript_text'])} chars)"
                )
                continue

            if t.get("turn_count", 0) < MIN_TURN_COUNT:
                errors.append(f"{call_id}: too few turns ({t.get('turn_count')})")
                continue

            valid.append(t)

        log.info(
            "[%s] Validation: %d valid, %d skipped",
            self.name, len(valid), len(errors),
        )

        return {
            **state,
            "raw_transcripts":       raw,
            "validated_transcripts": valid,
            "validation_errors":     errors,
        }
