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
from pathlib  import Path

import pandas as pd

from pipeline.governance import AUDIT_LOG
from pipeline.logger     import get_logger
from pipeline.memory     import MEMORY

log = get_logger(__name__)

OUTPUT_DIR = Path("outputs")


class ExportAgent:
    """Stateless agent — instantiate once and call run() per pipeline invocation."""

    name = "ExportAgent"

    def run(self, state: dict) -> dict:
        t0 = time.monotonic()
        OUTPUT_DIR.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        AUDIT_LOG.record_agent_start(self.name, {"ts": ts})

        results   = state["analysis_results"]
        metrics   = dict(state["aggregated_metrics"])
        qa_report = state.get("qa_report", {})
        insights  = state.get("agent_insights", {})
        usage     = state.get("token_usage", {})

        # 1 ── Per-call CSV
        df       = pd.DataFrame(results)
        csv_path = OUTPUT_DIR / f"call_results_{ts}.csv"
        df.to_csv(csv_path, index=False)
        log.info("[%s] CSV: %d rows → %s", self.name, len(results), csv_path)

        # 2 ── Summary JSON (dashboard source of truth)
        metrics["token_usage"]    = usage
        metrics["qa_summary"]     = qa_report.get("summary", {})
        metrics["agent_insights"] = insights
        summary_path = OUTPUT_DIR / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as fh:
            json.dump(metrics, fh, indent=2)
        log.info("[%s] Summary JSON: %s", self.name, summary_path)

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

        # 6 ── Run manifest
        manifest = {
            "run_timestamp":      ts,
            "pipeline_version":   "2.0-multi-agent",
            "agents_executed": [
                "DataIngestionAgent",
                "ExtractionAgent",
                "QualityAgent",
                "AggregationAgent",
                "InsightsAgent",
                "ExportAgent",
            ],
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
            "validation_errors":  state.get("validation_errors", []),
            "failed_call_ids":    state.get("failed_call_ids", []),
            "token_usage":        usage,
            "insights_source":    insights.get("source", "none"),
            "output_files": {
                "csv":          str(csv_path),
                "summary_json": str(summary_path),
                "full_json":    str(full_path),
                "qa_report":    str(qa_path),
                "insights":     str(insights_path),
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

        AUDIT_LOG.record_agent_end(
            self.name, {"files_written": len(export_paths)},
            elapsed_s=time.monotonic() - t0,
        )
        log.info(
            "[%s] All outputs written to %s  |  Audit: %s events",
            self.name, OUTPUT_DIR.resolve(), AUDIT_LOG.summary()["total_events"],
        )
        return {**state, "export_paths": export_paths}
