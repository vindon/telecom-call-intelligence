"""
QualityAgent  —  Agent 3 of 6
--------------------------------
Inline QA scoring for every extracted result — runs inside the pipeline
immediately after ExtractionAgent, before aggregation.

Scoring model (100 pts per call):
  Completeness  30 — required fields are non-null / non-empty
  Enum validity 25 — string fields match their allowed value sets
  Consistency   25 — cross-field logical rules (FCR vs escalation, etc.)
  Plausibility  20 — numeric ranges and derived sanity checks

Grade bands:
  HIGH   ≥ 85   production-grade extraction
  MEDIUM 60–84  usable; minor gaps expected
  LOW    < 60   flagged for review; excluded from aggregation

Dataset verdict: PASS if ≥90% of calls score ≥60 (configurable).

Outputs injected into PipelineState:
  qa_report          — full per-call scores + dataset-level summary
  qa_passed_results  — HIGH + MEDIUM records forwarded to aggregation
"""

from qa_audit   import audit_record, build_report
from pipeline.logger import get_logger

log = get_logger(__name__)

PASS_THRESHOLD = 60


class QualityAgent:
    """Stateless agent — instantiate once and call run() per pipeline invocation."""

    name = "QualityAgent"

    def run(self, state: dict) -> dict:
        results = state["analysis_results"]

        if not results:
            log.warning("[%s] No results to score — skipping QA", self.name)
            return {
                **state,
                "qa_report":         {"dataset_verdict": "SKIP", "total_calls_audited": 0},
                "qa_passed_results": [],
            }

        log.info("[%s] Scoring %d extraction results", self.name, len(results))

        # Attach per-call QA score into the result dict itself
        scored_results: list[dict] = []
        for r in results:
            audit = audit_record(r)
            enriched = {
                **r,
                "_qa_score":      audit["total_score"],
                "_qa_grade":      audit["grade"],
                "_qa_n_issues":   audit["total_issues"],
                "_qa_dimensions": audit["dimension_scores"],
            }
            scored_results.append(enriched)

        # Build dataset-level report (uses qa_audit.build_report internals)
        report = build_report(results, source_file="inline_pipeline", pass_threshold=PASS_THRESHOLD)

        # Only forward HIGH / MEDIUM records to aggregation
        passed = [r for r in scored_results if r["_qa_grade"] != "LOW"]
        low_count = len(scored_results) - len(passed)

        verdict = report["dataset_verdict"]
        summary = report["summary"]

        log.info(
            "[%s] QA complete: avg=%.1f  pass_rate=%.1f%%  verdict=%s  "
            "HIGH=%d  MEDIUM=%d  LOW=%d (excluded)",
            self.name,
            summary["avg_score"],
            summary["pass_rate_pct"],
            verdict,
            summary["grade_HIGH"],
            summary["grade_MEDIUM"],
            summary["grade_LOW"],
        )

        if low_count:
            log.warning(
                "[%s] Excluded %d LOW-quality records from aggregation",
                self.name, low_count,
            )

        # Replace analysis_results with QA-enriched versions (keeping all for export)
        return {
            **state,
            "analysis_results": scored_results,   # all records, now have _qa_* fields
            "qa_report":        report,
            "qa_passed_results": passed,
        }
