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

import time

from pipeline.decision_log import DecisionLogger
from pipeline.governance import AUDIT_LOG, QUALITY_GATE
from pipeline.logger import get_logger
from qa_audit import audit_record, build_report

log = get_logger(__name__)

PASS_THRESHOLD = 60


class QualityAgent:
    """Stateless agent — instantiate once and call run() per pipeline invocation."""

    name = "QualityAgent"

    def run(self, state: dict) -> dict:
        t0      = time.monotonic()
        results = state["analysis_results"]

        AUDIT_LOG.record_agent_start(self.name, {"n_results": len(results)})

        if not results:
            log.warning("[%s] No results to score — skipping QA", self.name)
            return {
                **state,
                "qa_report":         {"dataset_verdict": "SKIP", "total_calls_audited": 0},
                "qa_passed_results": [],
            }

        log.info("[%s] Scoring %d extraction results", self.name, len(results))

        dl = DecisionLogger(self.name, state)

        # Attach per-call QA score into the result dict itself
        scored_results: list[dict] = []
        for r in results:
            audit = audit_record(r)
            grade = audit["grade"]
            score = audit["total_score"]
            enriched = {
                **r,
                "_qa_score":      score,
                "_qa_grade":      grade,
                "_qa_n_issues":   audit["total_issues"],
                "_qa_dimensions": audit["dimension_scores"],
            }
            scored_results.append(enriched)

            # Log LOW grades and borderline MEDIUM (60-65) decisions
            if grade == "LOW":
                dl.log(
                    decision_type="qa_exclusion",
                    decision=f"Excluded {r.get('call_id', '?')}: grade=LOW score={score}",
                    reason=f"QA score {score}/100 < PASS_THRESHOLD={PASS_THRESHOLD}; record excluded from aggregation to protect KPI accuracy",
                    evidence={"call_id": str(r.get("call_id", "?"))[:16], "qa_score": score, "threshold": PASS_THRESHOLD, "issues": audit["total_issues"]},
                    call_id=str(r.get("call_id", "?"))[:16], confidence="high",
                    alternatives=["Include with low-confidence flag (rejected: would skew KPIs)"],
                )
            elif grade == "MEDIUM" and score <= 65:
                dl.log(
                    decision_type="qa_grade_assignment",
                    decision=f"Borderline MEDIUM for {r.get('call_id', '?')}: score={score}",
                    reason=f"Score {score} is in borderline range 60-65; accepted as MEDIUM but flagged — {audit['total_issues']} issue(s) detected",
                    evidence={"call_id": str(r.get("call_id", "?"))[:16], "qa_score": score, "issues": audit["total_issues"]},
                    call_id=str(r.get("call_id", "?"))[:16], confidence="medium",
                    alternatives=["Exclude as LOW (rejected: score above threshold)", "Re-extract (rejected: cost vs marginal gain)"],
                )

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

        # Governance: quality gate check (catastrophic failure only)
        gate_passed = True
        try:
            QUALITY_GATE.check(report)
            AUDIT_LOG.record_governance(
                check="quality_gate", passed=True,
                details={
                    "pass_rate_pct": summary.get("pass_rate_pct", 0),
                    "avg_score":     summary.get("avg_score", 0),
                    "verdict":       verdict,
                },
            )
            dl.log(
                decision_type="quality_gate_outcome",
                decision=f"Quality gate PASSED: verdict={verdict}, avg={summary.get('avg_score', 0)}",
                reason=f"pass_rate={summary.get('pass_rate_pct', 0)}% meets QualityGate threshold; pipeline continues to aggregation",
                evidence={"verdict": verdict, "avg_score": summary.get("avg_score", 0), "pass_rate_pct": summary.get("pass_rate_pct", 0), "n_low": low_count},
                confidence="high",
            )
        except QUALITY_GATE.QualityGateError as exc:
            gate_passed = False
            AUDIT_LOG.record_governance(
                check="quality_gate", passed=False,
                details={"error": str(exc)[:200]},
            )
            AUDIT_LOG.record_error(self.name, str(exc))
            log.error("[%s] Quality gate FAILED: %s", self.name, exc)
            dl.log(
                decision_type="quality_gate_outcome",
                decision=f"Quality gate FAILED: {str(exc)[:120]}",
                reason=f"pass_rate={summary.get('pass_rate_pct', 0)}% fell below QualityGate minimum; routing to emergency export to prevent bad KPIs",
                evidence={"verdict": verdict, "avg_score": summary.get("avg_score", 0), "pass_rate_pct": summary.get("pass_rate_pct", 0), "error": str(exc)[:120]},
                confidence="high",
                alternatives=["Continue to aggregation with warning (rejected: would produce misleading KPIs)"],
            )
            # Don't raise — set a flag so graph can route to emergency export
            report["_quality_gate_failed"] = True

        AUDIT_LOG.record_agent_end(
            self.name,
            {
                "avg_score": summary.get("avg_score", 0),
                "verdict":   verdict,
                "n_passed":  len(passed),
                "n_low":     low_count,
                "gate_ok":   gate_passed,
            },
            elapsed_s=time.monotonic() - t0,
        )

        return {
            **state,
            "analysis_results":  scored_results,
            "qa_report":         report,
            "qa_passed_results": passed,
            "decision_log":      dl.finalize(),
        }
