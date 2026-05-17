"""
AggregationAgent  —  Agent 4 of 6
------------------------------------
Computes all executive KPIs, distributions, and cost-lever estimates
from the QA-passed extraction results.

Receives qa_passed_results from QualityAgent (LOW-grade records excluded).
Falls back to the full analysis_results if QA was skipped.

Outputs injected into PipelineState:
  aggregated_metrics — full KPI dict (see aggregator.py for schema)
  token_usage        — inference cost summary
"""

from pipeline.aggregator import aggregate_metrics
from pipeline.logger import get_logger
from pipeline.token_tracker import token_summary

log = get_logger(__name__)


class AggregationAgent:
    """Stateless agent — instantiate once and call run() per pipeline invocation."""

    name = "AggregationAgent"

    def run(self, state: dict) -> dict:
        # Prefer QA-filtered results; fall back to full set if QA was skipped
        results = state.get("qa_passed_results") or state["analysis_results"]

        if not results:
            raise RuntimeError(
                "[AggregationAgent] No results available for aggregation. "
                "Check ExtractionAgent and QualityAgent logs."
            )

        log.info("[%s] Aggregating %d results", self.name, len(results))

        metrics       = aggregate_metrics(results)
        usage_summary = token_summary(results)

        kpis = metrics["kpis"]
        log.info(
            "[%s] KPIs: FCR=%.1f%%  AHT=%.1f min  avoidable=%.1f%%  "
            "AI_resolvable=%.1f%%  tokens=%d  cost=$%.4f",
            self.name,
            kpis["fcr_rate_pct"],
            kpis["avg_handle_time_minutes"],
            kpis["avoidable_call_rate_pct"],
            kpis["agentic_ai_resolvable_pct"],
            usage_summary.get("total_tokens", 0),
            usage_summary.get("total_cost_usd", 0),
        )

        return {
            **state,
            "aggregated_metrics": metrics,
            "token_usage":        usage_summary,
        }
