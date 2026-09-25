"""
eval_golden_set.py — Golden-Set Regression Eval for Extraction Quality
--------------------------------------------------------------------------
Re-runs extraction on a frozen set of real, previously-HIGH-QA-graded
transcripts (evals/golden_set.json) and diffs the fresh output against
the frozen expected values. Catches prompt/model/schema regressions that
the fast unit-test suite (tests/) cannot — those tests verify code
correctness, not model output quality.

NEVER run automatically: this makes real, billed LLM API calls (~$0.11
for the full golden set at current pricing). Run manually via
`make eval-golden`, always after confirming the cost with whoever's
paying for it.

Known limitation — first-pass extraction only: this eval calls
pipeline.analyzer.analyze_batch() directly, which performs first-pass
extraction only — it does not run ExtractionAgent's ReAct gap-fill loop.
The golden set's frozen `expected` values were captured from the full
pipeline (including gap-fill), so a golden case whose original extraction
needed gap-fill to reach its correct values may show a false regression
here. This is an accepted, documented limitation, not a bug — wiring in
the ReAct loop is a bigger change with its own design tradeoffs.

Usage:
    .venv/bin/python eval_golden_set.py
    make eval-golden
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pipeline.analyzer import analyze_batch
from pipeline.config import (
    EVAL_DURATION_FIELD,
    EVAL_DURATION_TOLERANCE_PCT,
    EVAL_PASS_THRESHOLD_PCT,
)
from qa_audit import audit_record

GOLDEN_SET_PATH = Path("evals/golden_set.json")


@dataclass
class FieldScore:
    field: str
    expected: object
    actual: object
    match: bool


@dataclass
class CaseResult:
    call_id: str
    status: str  # "scored" | "failed"
    field_scores: list[FieldScore] = field(default_factory=list)
    expected_qa_grade: str | None = None
    actual_qa_grade: str | None = None
    reason: str = ""

    @property
    def accuracy_pct(self) -> float:
        if self.status == "failed" or not self.field_scores:
            return 0.0
        return 100.0 * sum(1 for f in self.field_scores if f.match) / len(self.field_scores)

    @property
    def regressed_from_high(self) -> bool:
        return (
            self.expected_qa_grade == "HIGH"
            and self.actual_qa_grade is not None
            and self.actual_qa_grade != "HIGH"
        )


@dataclass
class EvalReport:
    cases: list[CaseResult]
    aggregate_accuracy_pct: float
    regressions: list[str]
    passed: bool

    def to_dict(self) -> dict:
        return {
            "aggregate_accuracy_pct": round(self.aggregate_accuracy_pct, 2),
            "passed": self.passed,
            "regressions": self.regressions,
            "cases": [
                {
                    "call_id": c.call_id,
                    "status": c.status,
                    "accuracy_pct": round(c.accuracy_pct, 2),
                    "expected_qa_grade": c.expected_qa_grade,
                    "actual_qa_grade": c.actual_qa_grade,
                    "reason": c.reason,
                    "fields": [
                        {
                            "field": fs.field,
                            "expected": fs.expected,
                            "actual": fs.actual,
                            "match": fs.match,
                        }
                        for fs in c.field_scores
                    ],
                }
                for c in self.cases
            ],
        }


def _within_tolerance(expected, actual, tolerance_pct: float) -> bool:
    if actual is None or expected is None:
        return False
    if expected == 0:
        return actual == 0
    return abs(actual - expected) / abs(expected) <= tolerance_pct


def score_case(case: dict, actual: dict | None) -> CaseResult:
    """
    Compare one golden case's expected fields against a fresh extraction.
    `actual=None` means the extraction call failed for this case entirely
    (see run_eval() in Task 7) — scored as 0% across all fields, not
    silently excluded, so a flaky provider can't masquerade as "no
    regression found."
    """
    call_id = case["call_id"]
    if actual is None:
        return CaseResult(
            call_id=call_id,
            status="failed",
            expected_qa_grade=case.get("expected_qa_grade"),
            reason="Extraction call failed or returned no result",
        )

    scores = []
    for field_name, expected_value in case["expected"].items():
        actual_value = actual.get(field_name)
        if field_name == EVAL_DURATION_FIELD:
            match = _within_tolerance(expected_value, actual_value, EVAL_DURATION_TOLERANCE_PCT)
        else:
            match = actual_value == expected_value
        scores.append(
            FieldScore(field=field_name, expected=expected_value, actual=actual_value, match=match)
        )

    actual_qa_grade = audit_record({**actual, "call_id": call_id})["grade"]

    return CaseResult(
        call_id=call_id,
        status="scored",
        field_scores=scores,
        expected_qa_grade=case.get("expected_qa_grade"),
        actual_qa_grade=actual_qa_grade,
    )


def build_eval_report(cases: list[CaseResult]) -> EvalReport:
    aggregate = sum(c.accuracy_pct for c in cases) / len(cases) if cases else 0.0
    regressions = [c.call_id for c in cases if c.regressed_from_high]
    return EvalReport(
        cases=cases,
        aggregate_accuracy_pct=aggregate,
        regressions=regressions,
        passed=aggregate >= EVAL_PASS_THRESHOLD_PCT,
    )


def run_eval(golden_set_path: Path = GOLDEN_SET_PATH) -> EvalReport:
    if not golden_set_path.exists():
        raise FileNotFoundError(
            f"{golden_set_path} not found — the golden set hasn't been generated yet. "
            "Run `make build-golden-set SOURCE=<path>` first (a one-time step; see "
            "docs/engineering-standards.md)."
        )
    golden = json.loads(golden_set_path.read_text())
    cases_data = golden["cases"]

    transcripts = [
        {
            "call_id": c["call_id"],
            "call_date": c["call_date"],
            "transcript_text": c["transcript_text"],
        }
        for c in cases_data
    ]
    actual_results = analyze_batch(transcripts, inter_call_delay=2.0)
    actual_by_id = {r["call_id"]: r for r in actual_results if r.get("call_id")}

    cases = [score_case(c, actual_by_id.get(c["call_id"])) for c in cases_data]
    return build_eval_report(cases)


def _print_report(report: EvalReport) -> None:
    print(f"\n{'Call ID':<14} {'Status':<8} {'Accuracy':>9}  QA grade (expected → actual)")
    print("-" * 60)
    for c in report.cases:
        grade_note = f"{c.expected_qa_grade} → {c.actual_qa_grade}" if c.status == "scored" else "-"
        print(f"{c.call_id[:12]:<14} {c.status:<8} {c.accuracy_pct:>8.1f}%  {grade_note}")

    print("-" * 60)
    print(f"Aggregate accuracy: {report.aggregate_accuracy_pct:.1f}%")
    print(f"Threshold:          {EVAL_PASS_THRESHOLD_PCT}%")
    print(f"Verdict:            {'PASS' if report.passed else 'FAIL'}")
    if report.regressions:
        print(f"HIGH→lower regressions: {', '.join(c[:12] for c in report.regressions)}")


def main() -> None:
    try:
        report = run_eval()
    except FileNotFoundError as exc:
        print(f"\n✗ {exc}\n")
        sys.exit(1)
    _print_report(report)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path("outputs") / f"eval_report_{ts}.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(report.to_dict(), indent=2))
    print(f"\n✓ Report written → {out_path}")

    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
