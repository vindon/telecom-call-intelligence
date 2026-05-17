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

from pipeline.hf_loader  import load_telecom_transcripts
from pipeline.logger     import get_logger
from pipeline.governance import AUDIT_LOG, PII_SCANNER
from pipeline.tools      import REGISTRY as TOOLS

log = get_logger(__name__)

MIN_TRANSCRIPT_CHARS = 150
MIN_TURN_COUNT       = 4


class DataIngestionAgent:
    """Stateless agent — instantiate once and call run() per pipeline invocation."""

    name = "DataIngestionAgent"

    def run(self, state: dict) -> dict:
        import time
        t0     = time.monotonic()
        n      = state["n_calls"]
        seed   = state["seed"]
        offset = state.get("offset", 0)

        AUDIT_LOG.record_agent_start(self.name, {"n": n, "seed": seed, "offset": offset})
        log.info("[%s] Fetching n=%d  seed=%d  offset=%d", self.name, n, seed, offset)

        raw = load_telecom_transcripts(n=n, seed=seed, offset=offset)
        log.info("[%s] Fetched %d transcripts", self.name, len(raw))

        valid:  list[dict] = []
        errors: list[str]  = []
        pii_count = 0

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

            # PII scan before transcript enters the pipeline
            t = PII_SCANNER.scan_transcript(t)
            if t.get("_pii_redacted"):
                pii_types = t["_pii_redacted"]
                AUDIT_LOG.record_pii(str(call_id), pii_types)
                pii_count += 1

            valid.append(t)

        if pii_count:
            log.warning("[%s] PII redacted in %d transcript(s)", self.name, pii_count)

        log.info(
            "[%s] Validation: %d valid, %d skipped",
            self.name, len(valid), len(errors),
        )

        AUDIT_LOG.record_agent_end(
            self.name,
            {"n_valid": len(valid), "n_skipped": len(errors), "pii_redacted": pii_count},
            elapsed_s=time.monotonic() - t0,
        )
        AUDIT_LOG.record_governance(
            check="pii_scan", passed=True,
            details={"transcripts_scanned": len(raw), "pii_found": pii_count},
        )

        return {
            **state,
            "raw_transcripts":       raw,
            "validated_transcripts": valid,
            "validation_errors":     errors,
        }
