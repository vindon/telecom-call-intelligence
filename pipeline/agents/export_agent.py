"""
ExportAgent  —  Agent 6 of 6
-------------------------------
Persists all pipeline outputs to disk and produces the audit trail.

Outputs written:
  call_results_{ts}.csv        — per-call CSV for BI tools / data science
  summary.json                 — Streamlit dashboard source of truth
  full_results_{ts}.json       — complete per-call JSON with QA scores
  qa_report_{ts}.json          — standalone QA audit report
  insights_{ts}.json           — InsightsAgent recommendations
  run_manifest_{ts}.json       — immutable audit record for this execution

Outputs injected into PipelineState:
  export_paths  — dict mapping file type → absolute path string
"""

import json
import time
from datetime import datetime

import pandas as pd

from pipeline.config import OUTPUT_DIR, QUALITY_WARN_RATE, VECTOR_MEMORY_ENABLED
from pipeline.decision_log import DecisionLogger, summarize_decisions
from pipeline.governance import AUDIT_LOG
from pipeline.logger import get_logger
from pipeline.memory import MEMORY
from pipeline.vector_memory import VECTOR_STORE

log = get_logger(__name__)


class ExportAgent:
    """Stateless agent — instantiate once and call run() per pipeline invocation."""

    name = "ExportAgent"

    def run(self, state: dict) -> dict:
        t0 = time.monotonic()
        OUTPUT_DIR.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        AUDIT_LOG.record_agent_start(self.name, {"ts": ts})

        results      = state["analysis_results"]
        metrics      = dict(state.get("aggregated_metrics", {}))
        qa_report    = state.get("qa_report", {})
        insights     = state.get("agent_insights", {})
        usage        = state.get("token_usage", {})
        decision_log = state.get("decision_log", [])

        dl = DecisionLogger(self.name, state)

        # 1 ── Per-call CSV
        df       = pd.DataFrame(results)
        csv_path = OUTPUT_DIR / f"call_results_{ts}.csv"
        df.to_csv(csv_path, index=False)
        log.info("[%s] CSV: %d rows → %s", self.name, len(results), csv_path)

        # 2 ── Summary JSON (dashboard source of truth).
        # On the emergency path (quality gate failure) aggregated_metrics is
        # empty — overwriting summary.json then would blank the dashboard, so
        # the last good run's summary is preserved instead.
        emergency_run = not metrics.get("kpis")
        dl.log(
            decision_type="export_scope",
            decision=(
                "Emergency export: per-call artifacts only, summary.json preserved"
                if emergency_run else
                f"Full export: {len(results)} records + summary.json refreshed"
            ),
            reason=(
                "aggregated_metrics has no KPIs (quality gate failure path) — overwriting "
                "the dashboard source of truth with empty metrics would blank it"
                if emergency_run else
                "Normal pipeline completion — all artifacts written including dashboard summary"
            ),
            evidence={"emergency_run": emergency_run, "n_records": len(results),
                      "qa_verdict": qa_report.get("dataset_verdict", "N/A")},
            confidence="high",
            alternatives=(
                ["Overwrite summary.json with empty metrics (rejected: blanks dashboard)"]
                if emergency_run else
                ["Skip summary refresh (rejected: dashboard would show stale data)"]
            ),
        )
        decision_log = dl.finalize()  # include the export decision in all artifacts below

        summary_path = OUTPUT_DIR / "summary.json"
        if not emergency_run:
            metrics["token_usage"]       = usage
            metrics["qa_summary"]        = qa_report.get("summary", {})
            metrics["agent_insights"]    = insights
            metrics["decision_summary"]  = summarize_decisions(decision_log)

            # Run-specific AHT/phase-economics disclaimer — computed, not static,
            # so it lives in the actual report the business reads. Surfaced by
            # the dashboard whenever this run's data-quality pass rate is low
            # enough that phase-level cost allocation shouldn't be trusted as-is.
            dq_pass_rate = metrics["qa_summary"].get("data_quality_pass_rate_pct", 100.0)
            if dq_pass_rate < QUALITY_WARN_RATE * 100:
                n_failed = metrics["qa_summary"].get("data_quality_n_failed", 0)
                metrics["aht_disclaimer"] = (
                    f"Data quality gate passed only {dq_pass_rate}% of analyzed calls "
                    f"({n_failed} excluded for phase/timestamp/completeness failures) — "
                    "AHT and phase-level cost economics in this run are less reliable than "
                    "usual and should not drive staffing or cost decisions without review."
                )

            with open(summary_path, "w", encoding="utf-8") as fh:
                json.dump(metrics, fh, indent=2)
            log.info("[%s] Summary JSON: %s", self.name, summary_path)
        else:
            log.warning(
                "[%s] Emergency export (no aggregated metrics) — summary.json NOT overwritten",
                self.name,
            )

        # 3 ── Full results JSON (QA-enriched per-call records)
        full_path = OUTPUT_DIR / f"full_results_{ts}.json"
        with open(full_path, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)

        # 4 ── QA report JSON
        qa_path = OUTPUT_DIR / f"qa_report_{ts}.json"
        with open(qa_path, "w", encoding="utf-8") as fh:
            json.dump(qa_report, fh, indent=2)

        # 5 ── Insights JSON
        insights_path = OUTPUT_DIR / f"insights_{ts}.json"
        with open(insights_path, "w", encoding="utf-8") as fh:
            json.dump(insights, fh, indent=2)

        # 5b ── Decision log JSON (agent reasoning audit trail)
        decisions_path = OUTPUT_DIR / f"decisions_{ts}.json"
        with open(decisions_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "run_timestamp":    ts,
                    "total_decisions":  len(decision_log),
                    "summary":          summarize_decisions(decision_log),
                    "records":          decision_log,
                },
                fh, indent=2,
            )
        log.info("[%s] Decision log: %d records → %s", self.name, len(decision_log), decisions_path)

        # 6 ── Run manifest
        agents_executed = ["DataIngestionAgent", "ExtractionAgent", "QualityAgent"]
        if not emergency_run:
            agents_executed += ["AggregationAgent", "InsightsAgent", "ApprovalGate"]
        agents_executed.append("ExportAgent")

        manifest = {
            "run_timestamp":      ts,
            "pipeline_version":   "4.5.0",
            "agents_executed":    agents_executed,
            "offset":             state.get("offset", 0),
            "seed":               state.get("seed", 42),
            "n_requested":        state.get("n_calls", 0),
            "n_raw":              len(state.get("raw_transcripts", [])),
            "n_validated":        len(state.get("validated_transcripts", [])),
            "n_analyzed":         len(results),
            "n_qa_passed":        len(state.get("qa_passed_results", results)),
            "n_failed":           len(state.get("failed_call_ids", [])),
            "qa_verdict":         qa_report.get("dataset_verdict", "N/A"),
            "qa_avg_score":       qa_report.get("summary", {}).get("avg_score", 0),
            "data_quality_pass_rate_pct": qa_report.get("summary", {}).get("data_quality_pass_rate_pct", 100.0),
            "validation_errors":  state.get("validation_errors", []),
            "failed_call_ids":    state.get("failed_call_ids", []),
            "token_usage":        usage,
            "insights_source":    insights.get("source", "none"),
            "decision_log_count": len(decision_log),
            "output_files": {
                "csv":           str(csv_path),
                "summary_json":  str(summary_path),
                "full_json":     str(full_path),
                "qa_report":     str(qa_path),
                "insights":      str(insights_path),
                "decisions":     str(decisions_path),
            },
        }
        manifest_path = OUTPUT_DIR / f"run_manifest_{ts}.json"
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)

        # 7 ── Audit log
        audit_path = AUDIT_LOG.export(OUTPUT_DIR)

        export_paths = {
            "csv":          str(csv_path),
            "summary":      str(summary_path),
            "full_results": str(full_path),
            "qa_report":    str(qa_path),
            "insights":     str(insights_path),
            "decisions":    str(decisions_path),
            "manifest":     str(manifest_path),
            "audit_log":    str(audit_path),
        }

        # Update agent memory with this run's outcomes
        kpis = state.get("aggregated_metrics", {}).get("kpis", {})
        usage = state.get("token_usage", {})
        MEMORY.load()
        MEMORY.record_run({
            "run_timestamp":         ts,
            "offset":                state.get("offset", 0),
            "seed":                  state.get("seed", 42),
            "n_calls":               state.get("n_calls", 0),
            "n_analyzed":            len(results),
            "n_failed":              len(state.get("failed_call_ids", [])),
            "fcr_rate_pct":          kpis.get("fcr_rate_pct", 0),
            "avg_handle_time_minutes": kpis.get("avg_handle_time_minutes", 0),
            "qa_avg_score":          qa_report.get("summary", {}).get("avg_score", 0),
            "qa_verdict":            qa_report.get("dataset_verdict", "N/A"),
            "total_tokens":          usage.get("total_tokens", 0),
            "total_cost_usd":        usage.get("total_cost_usd", 0),
            "model":                 usage.get("model", "unknown"),
            "insights_source":       insights.get("source", "unknown"),
        })
        MEMORY.save()

        # Semantic vector memory — embeds this run's KPI profile so future
        # runs' InsightsAgent can retrieve it via VECTOR_STORE.query()/format_context()
        # (see pipeline/agents/insights_agent.py::_get_rich_context). Skipped on the
        # emergency path (no KPIs to embed) and never allowed to fail the export.
        if VECTOR_MEMORY_ENABLED and not emergency_run:
            try:
                kpi_text = (
                    f"FCR {kpis.get('fcr_rate_pct', 0)}% "
                    f"AHT {kpis.get('avg_handle_time_minutes', 0)} min "
                    f"escalation {kpis.get('escalation_rate_pct', 0)}% "
                    f"AI-resolvable {kpis.get('agentic_ai_resolvable_pct', 0)}%"
                )
                VECTOR_STORE.load()
                VECTOR_STORE.add_run(
                    run_id=ts,
                    kpi_text=kpi_text,
                    metadata={
                        "fcr_rate_pct":            kpis.get("fcr_rate_pct", 0),
                        "aht_minutes":             kpis.get("avg_handle_time_minutes", 0),
                        "qa_avg_score":            qa_report.get("summary", {}).get("avg_score", 0),
                        "total_cost_usd":          usage.get("total_cost_usd", 0),
                        "model":                   usage.get("model", "unknown"),
                    },
                )
                VECTOR_STORE.save()
            except Exception as exc:
                log.warning("[%s] Vector memory write failed (%s) — run not embedded", self.name, exc)

        AUDIT_LOG.record_agent_end(
            self.name, {"files_written": len(export_paths)},
            elapsed_s=time.monotonic() - t0,
        )
        log.info(
            "[%s] All outputs written to %s  |  Audit: %s events",
            self.name, OUTPUT_DIR.resolve(), AUDIT_LOG.summary()["total_events"],
        )
        return {**state, "export_paths": export_paths, "decision_log": decision_log}
