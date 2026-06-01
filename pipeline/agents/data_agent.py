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

from pipeline.decision_log import DecisionLogger
from pipeline.governance import AUDIT_LOG, PII_SCANNER
from pipeline.hf_loader import load_telecom_transcripts
from pipeline.logger import get_logger
from pipeline.tools import REGISTRY as TOOLS

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

        dl    = DecisionLogger(self.name, state)
        valid:  list[dict] = []
        errors: list[str]  = []
        pii_count = 0

        for t in raw:
            call_id = t.get("call_id", "UNKNOWN")

            if not t.get("transcript_text"):
                errors.append(f"{call_id}: empty transcript")
                dl.log(
                    decision_type="transcript_skip",
                    decision=f"Skipped {call_id}: empty transcript",
                    reason="transcript_text field is absent or empty — no content to extract",
                    evidence={"call_id": str(call_id), "skip_reason": "empty"},
                    call_id=str(call_id), confidence="high",
                    alternatives=["Include with placeholder text (rejected: no signal)"],
                )
                continue

            if len(t["transcript_text"]) < MIN_TRANSCRIPT_CHARS:
                txt_len = len(t["transcript_text"])
                errors.append(f"{call_id}: transcript too short ({txt_len} chars)")
                dl.log(
                    decision_type="transcript_skip",
                    decision=f"Skipped {call_id}: too short ({txt_len} chars)",
                    reason=f"Transcript length {txt_len} < MIN_TRANSCRIPT_CHARS={MIN_TRANSCRIPT_CHARS}; too brief for reliable extraction",
                    evidence={"call_id": str(call_id), "chars": txt_len, "min_required": MIN_TRANSCRIPT_CHARS},
                    call_id=str(call_id), confidence="high",
                    alternatives=["Include with lower quality flag (rejected: extraction unreliable)"],
                )
                continue

            if t.get("turn_count", 0) < MIN_TURN_COUNT:
                turns = t.get("turn_count", 0)
                errors.append(f"{call_id}: too few turns ({turns})")
                dl.log(
                    decision_type="transcript_skip",
                    decision=f"Skipped {call_id}: too few turns ({turns})",
                    reason=f"turn_count {turns} < MIN_TURN_COUNT={MIN_TURN_COUNT}; not a valid multi-turn conversation",
                    evidence={"call_id": str(call_id), "turns": turns, "min_required": MIN_TURN_COUNT},
                    call_id=str(call_id), confidence="high",
                    alternatives=["Include single-turn transcripts (rejected: not customer care calls)"],
                )
                continue

            # PII scan before transcript enters the pipeline
            t = PII_SCANNER.scan_transcript(t)
            if t.get("_pii_redacted"):
                pii_types = t["_pii_redacted"]
                AUDIT_LOG.record_pii(str(call_id), pii_types)
                pii_count += 1
                dl.log(
                    decision_type="pii_redaction",
                    decision=f"PII redacted in {call_id}: {pii_types}",
                    reason="PIIScanner detected sensitive patterns; redacted before transcript reaches LLM",
                    evidence={"call_id": str(call_id), "pii_types": pii_types},
                    call_id=str(call_id), confidence="high",
                    alternatives=["Block transcript entirely (rejected: redaction preserves data)"],
                )

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
            "decision_log":          dl.finalize(),
        }
