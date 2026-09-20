# Decision traceability — DecisionLogger

Every agent must instrument decisions with `DecisionLogger`. This is the traceability contract — not optional.

```python
from pipeline.decision_log import DecisionLogger

def run(self, state: dict) -> dict:
    dl = DecisionLogger(self.name, state)
    dl.log(
        decision_type="my_decision_type",
        decision="what was decided",
        reason="why — max 500 chars",
        evidence={"score": 87, "threshold": 60},   # no PII, no transcript text
        call_id="optional",
        confidence=0.9,
        alternatives=["option_b"],
    )
    return {**state, "decision_log": dl.finalize()}
```

## Named decision types

`transcript_skip`, `pii_redaction`, `react_trigger`, `react_gap_fill_outcome`, `qa_exclusion`, `qa_grade_assignment`, `quality_gate_outcome`, `aggregation_scope`, `cost_model_applied`, `provider_selected`, `deliberation_outcome`, `routing_decision`, `approval_decision`, `export_scope`, `data_quality_gate_outcome`, `phase_reconciliation_failure`, `timestamp_ground_truth_mismatch`, `transcript_truncation_detected`.
