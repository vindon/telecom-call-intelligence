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

Data quality gate (separate from the 100-pt score — see qa_audit.check_data_quality):
  A record failing phase reconciliation, timestamp ground-truth, or transcript
  completeness is excluded from aggregation alongside LOW-grade records, since
  these are data-integrity facts, not quality nuances. The dataset-level
  data_quality_pass_rate_pct rolls up into qa_report/summary.json and drives
  a run-specific AHT disclaimer in the dashboard when it falls below
  QUALITY_WARN_RATE.

Outputs injected into PipelineState:
  qa_report          — full per-call scores + dataset-level summary (incl.
                        data_quality_pass_rate_pct)
  qa_passed_results  — HIGH + MEDIUM records that also passed the data
                        quality gate, forwarded to aggregation
"""

import time

from pipeline.config import QA_PASS_THRESHOLD as PASS_THRESHOLD
from pipeline.config import QUALITY_WARN_RATE
from pipeline.decision_log import DecisionLogger
from pipeline.governance import AUDIT_LOG, QUALITY_GATE
from pipeline.logger import get_logger
from qa_audit import audit_record, build_report, check_data_quality

log = get_logger(__name__)


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

        # Attach per-call QA score + data-quality gate result into the result dict itself
        scored_results: list[dict] = []
        n_dq_failed = 0
        # Tallied per failure_type so the dashboard/executive reporting can show
        # WHY calls were excluded, not just how many — see data_quality_failure_breakdown
        # in the summary below. A call failing multiple checks counts once per check.
        dq_failure_breakdown: dict[str, int] = {}
        for r in results:
            audit = audit_record(r)
            grade = audit["grade"]
            score = audit["total_score"]
            dq = check_data_quality(r)
            enriched = {
                **r,
                "_qa_score":       score,
                "_qa_grade":       grade,
                "_qa_n_issues":    audit["total_issues"],
                "_qa_dimensions":  audit["dimension_scores"],
                "_dq_gate_passed": dq["passed"],
                "_dq_failures":    dq["failures"],
            }
            scored_results.append(enriched)

            if not dq["passed"]:
                n_dq_failed += 1
                call_id = str(r.get("call_id", "?"))[:16]
                for failure_type in dq["failures"]:
                    dq_failure_breakdown[failure_type] = dq_failure_breakdown.get(failure_type, 0) + 1
                    check = dq["checks"][failure_type]
                    dl.log(
                        decision_type=(
                            "phase_reconciliation_failure" if failure_type == "phase_reconciliation" else
                            "timestamp_ground_truth_mismatch" if failure_type == "timestamp_ground_truth" else
                            "transcript_truncation_detected"
                        ),
                        decision=f"Data quality gate failed for {call_id}: {failure_type}",
                        reason=(
                            f"Deterministic {failure_type} check failed — record excluded from "
                            "aggregation to protect AHT/phase-economics accuracy"
                        ),
                        evidence={"call_id": call_id, **{k: v for k, v in check.items() if k != "reason"}},
                        call_id=call_id, confidence="high",
                        alternatives=["Include with data-quality flag (rejected: would corrupt AHT economics)"],
                    )

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

        # Data-quality pass rate rolls up alongside the QA pass rate — same
        # summary dict, so ExportAgent's existing qa_summary → summary.json
        # wiring carries it through to the dashboard without further changes.
        n = len(scored_results)
        dq_pass_rate = round((n - n_dq_failed) / n * 100, 1) if n else 100.0
        report["summary"]["data_quality_pass_rate_pct"] = dq_pass_rate
        report["summary"]["data_quality_n_failed"] = n_dq_failed
        report["summary"]["data_quality_failure_breakdown"] = dq_failure_breakdown

        # Only forward records that are both QA-passed (HIGH/MEDIUM) and
        # data-quality-gate-passed to aggregation.
        passed = [r for r in scored_results if r["_qa_grade"] != "LOW" and r["_dq_gate_passed"]]
        low_count = len(scored_results) - sum(1 for r in scored_results if r["_qa_grade"] != "LOW")

        verdict = report["dataset_verdict"]
        summary = report["summary"]

        log.info(
            "[%s] QA complete: avg=%.1f  pass_rate=%.1f%%  verdict=%s  "
            "HIGH=%d  MEDIUM=%d  LOW=%d (excluded)  data_quality_pass_rate=%.1f%% (%d failed)",
            self.name,
            summary["avg_score"],
            summary["pass_rate_pct"],
            verdict,
            summary["grade_HIGH"],
            summary["grade_MEDIUM"],
            summary["grade_LOW"],
            dq_pass_rate, n_dq_failed,
        )

        if low_count:
            log.warning(
                "[%s] Excluded %d LOW-quality records from aggregation",
                self.name, low_count,
            )
        if n_dq_failed:
            log.warning(
                "[%s] Excluded %d record(s) failing the data-quality gate (phase/timestamp/completeness)",
                self.name, n_dq_failed,
            )

        dl.log(
            decision_type="data_quality_gate_outcome",
            decision=f"Data quality pass rate: {dq_pass_rate}% ({n_dq_failed}/{n} failed)",
            reason=(
                f"{'Below' if dq_pass_rate < QUALITY_WARN_RATE * 100 else 'Above'} "
                f"QUALITY_WARN_RATE={QUALITY_WARN_RATE * 100:.0f}% — "
                "phase-reconciliation, timestamp ground-truth, and transcript-completeness "
                "checks combined; failing records excluded from aggregation"
            ),
            evidence={"pass_rate_pct": dq_pass_rate, "n_failed": n_dq_failed, "n_total": n},
            confidence="high",
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
                "avg_score":    summary.get("avg_score", 0),
                "verdict":      verdict,
                "n_passed":     len(passed),
                "n_low":        low_count,
                "n_dq_failed":  n_dq_failed,
                "gate_ok":      gate_passed,
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
