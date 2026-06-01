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
from pipeline.decision_log import DecisionLogger
from pipeline.logger import get_logger
from pipeline.token_tracker import token_summary

log = get_logger(__name__)


class AggregationAgent:
    """Stateless agent — instantiate once and call run() per pipeline invocation."""

    name = "AggregationAgent"

    def run(self, state: dict) -> dict:
        dl = DecisionLogger(self.name, state)

        # Prefer QA-filtered results; fall back to full set if QA was skipped
        qa_passed = state.get("qa_passed_results")
        results   = qa_passed or state["analysis_results"]
        used_qa_filtered = bool(qa_passed)

        if not results:
            raise RuntimeError(
                "[AggregationAgent] No results available for aggregation. "
                "Check ExtractionAgent and QualityAgent logs."
            )

        dl.log(
            decision_type="aggregation_scope",
            decision=f"Aggregating {len(results)} records (qa_filtered={used_qa_filtered})",
            reason=(
                f"Using QA-passed subset ({len(results)} records) — LOW-grade exclusions protect KPI accuracy"
                if used_qa_filtered else
                "QA step was skipped; aggregating full analysis_results set"
            ),
            evidence={
                "n_records": len(results),
                "qa_filtered": used_qa_filtered,
                "n_total_analyzed": len(state.get("analysis_results", [])),
            },
            confidence="high",
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

        # Log cost model selection decision
        dl.log(
            decision_type="cost_model_applied",
            decision=f"Cost model: {usage_summary.get('provider', 'unknown')} at ${usage_summary.get('price_input_per_mtok', 0):.2f}/${usage_summary.get('price_output_per_mtok', 0):.2f}/MTok",
            reason="Cost model resolved from EXTRACTION_MODEL prefix via token_tracker._resolve_pricing() — single config knob drives all provider pricing",
            evidence={
                "model": usage_summary.get("model", "unknown"),
                "provider": usage_summary.get("provider", "unknown"),
                "total_cost_usd": usage_summary.get("total_cost_usd", 0),
                "total_tokens": usage_summary.get("total_tokens", 0),
            },
            confidence="high",
        )

        return {
            **state,
            "aggregated_metrics": metrics,
            "token_usage":        usage_summary,
            "decision_log":       dl.finalize(),
        }
