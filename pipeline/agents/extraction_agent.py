"""
ExtractionAgent  —  Agent 2 of 6
-----------------------------------
Drives structured JSON extraction for every validated transcript using the
configured EXTRACTION_MODEL (Claude Haiku primary; Gemini fallback). This
agent is the primary LLM consumer in the pipeline.

Responsibilities
----------------
  • Manage the LLM API client and system prompt lifecycle
  • Submit each transcript with JSON output mode + Chain-of-Thought
  • Execute the ReAct control loop per transcript:
      Reason  : assess which critical fields are likely present
      Act     : call the LLM for full extraction
      Observe : score field coverage inline
      Reason  : decide if a targeted gap-fill retry is warranted
      Act     : call the LLM again for missing fields only (if score < threshold)
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
from typing import Any

import pipeline.analyzer as _analyzer_mod
from pipeline.analyzer import (
    analyze_batch,
    gap_fill_transcript,
    load_system_prompt,
    score_field_coverage,
)
from pipeline.config import EXTRACTION_API_TIMEOUT_S, REACT_MAX_ITERATIONS, REACT_QUALITY_THRESHOLD
from pipeline.decision_log import DecisionLogger
from pipeline.governance import AUDIT_LOG, BUDGET_GUARD
from pipeline.logger import get_logger
from pipeline.memory import MEMORY
from pipeline.security import INPUT_SANITIZER, SCOPE_GUARD
from pipeline.token_tracker import cost_usd as _cost_usd

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

        # Local logger keeps the agent stateless — no instance state may
        # persist across run() invocations on the shared singleton.
        dl = DecisionLogger(self.name, state)

        # ── Act: initial batch extraction ────────────────────────────
        results = analyze_batch(
            transcripts,
            inter_call_delay=delay,
            checkpoint_key=checkpoint_key,
        )

        # ── Observe + Reason + Act (ReAct gap-fill loop) ─────────────
        results, react_stats = self._react_loop(results, transcripts, dl)

        # Merge ground-truth timestamp + truncation heuristic from the source
        # transcript onto each result — QualityAgent's data-quality gate
        # (qa_audit.check_timestamp_ground_truth) needs these alongside the
        # LLM's own total_duration_seconds.
        transcript_map = {t["call_id"]: t for t in transcripts}
        for r in results:
            src = transcript_map.get(r.get("call_id"))
            if src is not None:
                r["_raw_duration_seconds"] = src.get("raw_duration_seconds")
                r["_heuristic_truncation_flag"] = src.get("_heuristic_truncation_flag", False)

        result_ids = {r.get("call_id") for r in results}
        failed = [t["call_id"] for t in transcripts if t["call_id"] not in result_ids]

        if failed:
            MEMORY.record_failures(failed, context=f"checkpoint={checkpoint_key}")

        # Budget check — use model-aware pricing from token_tracker (not hardcoded rate).
        # Cache tokens must be passed separately: pricing them at the full input
        # rate (like a naive prompt_tokens sum would) overstates spend against
        # BudgetGuard by ignoring the ~90% discount a cache hit actually gets.
        total_prompt         = sum(r.get("_prompt_tokens", 0) for r in results)
        total_out            = sum(r.get("_completion_tokens", 0) for r in results)
        total_cache_creation = sum(r.get("_cache_creation_tokens", 0) for r in results)
        total_cache_read     = sum(r.get("_cache_read_tokens", 0) for r in results)
        est_cost     = _cost_usd(total_prompt, total_out, total_cache_creation, total_cache_read)
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

        # Dataset-level summary decision
        dl.log(
            decision_type="react_gap_fill_outcome",
            decision=f"ReAct loop: {react_stats['n_gap_fills']} gap-fills, {react_stats['n_improved']} improved",
            reason=(
                f"Calls below REACT_QUALITY_THRESHOLD={REACT_QUALITY_THRESHOLD}% coverage "
                f"triggered targeted gap-fill retries; avg coverage before={react_stats['avg_coverage_before']}%"
            ),
            evidence=react_stats,
            confidence="high",
        )

        return {
            **state,
            "analysis_results": results,
            "failed_call_ids":  failed,
            "react_stats":      react_stats,
            "decision_log":     dl.finalize(),
        }

    def _react_loop(
        self,
        results: list[dict],
        transcripts: list[dict],
        dl: DecisionLogger,
    ) -> tuple[list[dict], dict]:
        """
        ReAct observe → reason → act loop.

        For each extracted result whose field-coverage score is below
        REACT_QUALITY_THRESHOLD, issue up to REACT_MAX_ITERATIONS targeted
        gap-fill calls to recover missing critical fields.

        Returns (improved_results, stats_dict).
        """
        client: Any
        try:
            from pipeline.analyzer import _USE_CLAUDE
            if _USE_CLAUDE:
                import anthropic
                api_key = os.environ.get("ANTHROPIC_API_KEY")
                if not api_key:
                    return results, {"n_improved": 0, "n_gap_fills": 0, "avg_coverage_before": 0}
                client = anthropic.Anthropic(api_key=api_key, timeout=EXTRACTION_API_TIMEOUT_S, max_retries=1)
            else:
                from google import genai
                from google.genai import types as genai_types
                api_key = os.environ.get("GEMINI_API_KEY")
                if not api_key:
                    return results, {"n_improved": 0, "n_gap_fills": 0, "avg_coverage_before": 0}
                client = genai.Client(
                    api_key=api_key,
                    http_options=genai_types.HttpOptions(timeout=EXTRACTION_API_TIMEOUT_S * 1000),
                )
            system_prompt = load_system_prompt()
        except Exception as exc:
            log.warning("[%s] ReAct loop unavailable: %s", self.name, exc)
            return results, {"n_improved": 0, "n_gap_fills": 0, "avg_coverage_before": 0}

        # Build a lookup so we can find the original transcript for each result
        transcript_map = {t["call_id"]: t for t in transcripts}

        improved_results: list[dict] = []
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
            dl.log(
                decision_type="react_trigger",
                decision=f"Gap-fill triggered for {call_id} (coverage={coverage}%)",
                reason=f"Field coverage {coverage}% < REACT_QUALITY_THRESHOLD={REACT_QUALITY_THRESHOLD}%; targeted retry will attempt to recover missing critical fields",
                evidence={"call_id": str(call_id)[:12], "coverage_pct": coverage, "threshold": REACT_QUALITY_THRESHOLD},
                call_id=str(call_id)[:12], confidence="high",
                alternatives=["Accept partial extraction (rejected: critical fields missing)"],
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
