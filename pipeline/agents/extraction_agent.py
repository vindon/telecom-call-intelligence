"""
ExtractionAgent  —  Agent 2 of 6
-----------------------------------
Drives the Gemini 2.5 Flash Lite structured JSON extraction for every validated
transcript. This agent is the primary LLM consumer in the pipeline.

Responsibilities
----------------
  • Manage the Gemini API client and system prompt lifecycle
  • Submit each transcript to Gemini with native JSON mode + Chain-of-Thought
  • Execute the ReAct control loop per transcript:
      Reason  : assess which critical fields are likely present
      Act     : call Gemini for full extraction
      Observe : score field coverage inline
      Reason  : decide if a targeted gap-fill retry is warranted
      Act     : call Gemini again for missing fields only (if score < threshold)
      Observe : merge and record final coverage improvement
  • Handle 429 rate limits with exponential backoff
  • Checkpoint each successful result immediately (resume-safe)
  • Record failures in agent memory for pattern analysis

Outputs injected into PipelineState
------------------------------------
  analysis_results  — list of extracted JSON dicts (one per successful call)
  failed_call_ids   — call IDs that could not be extracted after all retries
  react_stats       — dict with coverage improvement telemetry
"""

import os
import time

import pipeline.analyzer as _analyzer_mod
from pipeline.analyzer import (
    analyze_batch,
    analyze_transcript,
    gap_fill_transcript,
    load_system_prompt,
    score_field_coverage,
)
from pipeline.config import REACT_MAX_ITERATIONS, REACT_QUALITY_THRESHOLD
from pipeline.governance import AUDIT_LOG, BUDGET_GUARD
from pipeline.logger import get_logger
from pipeline.memory import MEMORY
from pipeline.security import INPUT_SANITIZER, SCOPE_GUARD

log = get_logger(__name__)


class ExtractionAgent:
    """Stateless agent — instantiate once and call run() per pipeline invocation."""

    name = "ExtractionAgent"

    def run(self, state: dict) -> dict:
        t0             = time.monotonic()
        transcripts    = state["validated_transcripts"]
        delay          = state.get("inter_call_delay", 2.0)
        checkpoint_key = state.get("checkpoint_key", "")

        INPUT_SANITIZER.validate_state_schema(state, ["validated_transcripts"])
        SCOPE_GUARD.check(self.name, "score_extraction")  # documents authorized tool access

        AUDIT_LOG.record_agent_start(
            self.name,
            {"n_transcripts": len(transcripts), "checkpoint_key": checkpoint_key,
             "react_enabled": True, "react_threshold": REACT_QUALITY_THRESHOLD},
        )
        log.info(
            "[%s] Starting ReAct extraction: %d transcripts  checkpoint='%s'",
            self.name, len(transcripts), checkpoint_key or "none",
        )

        # ── Act: initial batch extraction ────────────────────────────
        results = analyze_batch(
            transcripts,
            inter_call_delay=delay,
            checkpoint_key=checkpoint_key,
        )

        # ── Observe + Reason + Act (ReAct gap-fill loop) ─────────────
        results, react_stats = self._react_loop(results, transcripts)

        result_ids = {r.get("call_id") for r in results}
        failed = [t["call_id"] for t in transcripts if t["call_id"] not in result_ids]

        if failed:
            MEMORY.record_failures(failed, context=f"checkpoint={checkpoint_key}")

        # Budget check
        total_tokens = sum(r.get("_total_tokens", 0) for r in results)
        est_cost = total_tokens / 1_000_000 * 0.10
        try:
            BUDGET_GUARD.check(est_cost, context=f"after {len(results)} calls (incl. ReAct retries)")
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
            "[%s] Extraction complete: %d OK  %d failed  react_improved=%d",
            self.name, len(results), len(failed), react_stats["n_improved"],
        )
        AUDIT_LOG.record_agent_end(
            self.name,
            {"n_ok": len(results), "n_failed": len(failed), "react_stats": react_stats},
            elapsed_s=time.monotonic() - t0,
        )

        return {
            **state,
            "analysis_results": results,
            "failed_call_ids":  failed,
            "react_stats":      react_stats,
        }

    def _react_loop(
        self,
        results: list[dict],
        transcripts: list[dict],
    ) -> tuple[list[dict], dict]:
        """
        ReAct observe → reason → act loop.

        For each extracted result whose field-coverage score is below
        REACT_QUALITY_THRESHOLD, issue up to REACT_MAX_ITERATIONS targeted
        gap-fill calls to recover missing critical fields.

        Returns (improved_results, stats_dict).
        """
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return results, {"n_improved": 0, "n_gap_fills": 0, "avg_coverage_before": 0}

        try:
            from google import genai
            client        = genai.Client(api_key=api_key)
            system_prompt = load_system_prompt()
        except Exception as exc:
            log.warning("[%s] ReAct loop unavailable: %s", self.name, exc)
            return results, {"n_improved": 0, "n_gap_fills": 0, "avg_coverage_before": 0}

        # Build a lookup so we can find the original transcript for each result
        transcript_map = {t["call_id"]: t for t in transcripts}

        improved_results = []
        n_improved  = 0
        n_gap_fills = 0
        coverage_before: list[int] = []

        for result in results:
            # Check module-level circuit breaker — quota already exhausted
            if _analyzer_mod._react_quota_exhausted:
                improved_results.extend(results[len(improved_results):])
                break
            call_id = result.get("call_id")

            # ── Observe: score current coverage ─────────────────────
            coverage = score_field_coverage(result)
            coverage_before.append(coverage)

            # ── Reason: decide whether a gap-fill is worth doing ─────
            if coverage >= REACT_QUALITY_THRESHOLD or call_id not in transcript_map:
                improved_results.append(result)
                continue

            log.info(
                "[ReAct] call %s: coverage=%d < threshold=%d — triggering gap-fill",
                str(call_id)[:12], coverage, REACT_QUALITY_THRESHOLD,
            )
            AUDIT_LOG.record_tool_call(
                tool="gap_fill", agent=self.name,
                inputs=["transcript", "first_pass_result"],
                success=True, elapsed_s=0,
            )

            # ── Act: gap-fill for up to REACT_MAX_ITERATIONS passes ──
            current = result
            for iteration in range(REACT_MAX_ITERATIONS):
                transcript = transcript_map[call_id]
                improved = gap_fill_transcript(client, system_prompt, transcript, current)
                n_gap_fills += 1

                new_coverage = score_field_coverage(improved)
                if new_coverage >= REACT_QUALITY_THRESHOLD:
                    log.info(
                        "[ReAct] call %s: coverage restored to %d (iter %d)",
                        str(call_id)[:12], new_coverage, iteration + 1,
                    )
                    current = improved
                    break
                current = improved

            if score_field_coverage(current) > coverage:
                n_improved += 1
            improved_results.append(current)

        avg_before = round(sum(coverage_before) / len(coverage_before)) if coverage_before else 0
        stats = {
            "n_improved":        n_improved,
            "n_gap_fills":       n_gap_fills,
            "avg_coverage_before": avg_before,
        }
        log.info("[ReAct] Loop complete: %d/%d calls gap-filled, %d improved",
                 n_gap_fills, len(results), n_improved)
        return improved_results, stats
