"""
pipeline/decision_log.py  —  Agent Decision Traceability Layer
---------------------------------------------------------------
Every autonomous decision made by a pipeline agent is recorded here with:
  - WHAT was decided
  - WHY (reasoning / evidence that drove it)
  - WHICH alternatives were considered
  - HOW confident the agent was

This complements the AuditLog (telemetry / events) with semantic reasoning
records that let operators retrace, audit, and challenge agent behaviour.

Usage
-----
  from pipeline.decision_log import DecisionLogger

  # In an agent's run() method:
  logger = DecisionLogger(agent_name="QualityAgent", state=state)
  logger.log(
      decision_type="qa_exclusion",
      decision="Excluded call C123 from aggregation",
      reason="QA score 42/100 is below the 60-pt PASS_THRESHOLD",
      evidence={"call_id": "C123", "qa_score": 42, "threshold": 60},
      call_id="C123",
      confidence="high",
      alternatives=["Include with warning flag", "Re-extract and re-score"],
  )
  return {**state, "decision_log": logger.finalize()}

The decision_log key in PipelineState is a plain list of dicts so it
serialises directly to JSON without any import dependencies.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pipeline.logger import get_logger

log = get_logger(__name__)

# Maximum characters for the reason field — keeps records compact in JSON exports
_MAX_REASON_CHARS = 500

# Keys that must never appear in evidence dicts — enforces the CLAUDE.md contract
# that transcript text and customer PII are never stored in decision records.
_FORBIDDEN_EVIDENCE_KEYS: frozenset[str] = frozenset({
    "transcript_text", "transcript", "text", "customer_name", "customer_id",
    "agent_name", "phone", "email", "ssn", "account_number", "address",
    "raw_transcript", "call_text", "conversation",
})


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _short_id() -> str:
    return str(uuid.uuid4())[:8]


# ── DecisionRecord ────────────────────────────────────────────────────

class DecisionRecord:
    """
    One immutable decision taken by an agent.

    Serialises to a plain dict so it can travel through PipelineState
    (a TypedDict backed by a plain dict) and be written to JSON without
    any special encoder.
    """

    __slots__ = (
        "record_id", "agent", "decision_type", "timestamp",
        "decision", "reason", "evidence", "call_id",
        "confidence", "alternatives",
    )

    def __init__(
        self,
        agent:         str,
        decision_type: str,
        decision:      str,
        reason:        str,
        evidence:      dict[str, Any] | None = None,
        call_id:       str | None = None,
        confidence:    str | None = None,
        alternatives:  list[str] | None = None,
    ) -> None:
        self.record_id     = _short_id()
        self.agent         = agent
        self.decision_type = decision_type
        self.timestamp     = _utc_now()
        self.decision      = decision
        self.reason        = reason[:_MAX_REASON_CHARS]
        self.evidence      = evidence or {}
        self.call_id       = call_id
        self.confidence    = confidence
        self.alternatives  = alternatives or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id":     self.record_id,
            "agent":         self.agent,
            "decision_type": self.decision_type,
            "timestamp":     self.timestamp,
            "decision":      self.decision,
            "reason":        self.reason,
            "evidence":      self.evidence,
            "call_id":       self.call_id,
            "confidence":    self.confidence,
            "alternatives":  self.alternatives,
        }


# ── DecisionLogger ────────────────────────────────────────────────────

class DecisionLogger:
    """
    Scoped to one agent invocation.

    Reads existing decisions from state (if any), appends new ones,
    and returns the updated list via finalize().

    Thread safety: single-threaded pipelines only (LangGraph default).
    """

    def __init__(self, agent_name: str, state: dict) -> None:
        self._agent  = agent_name
        self._records: list[dict] = list(state.get("decision_log", []))
        self._new: list[DecisionRecord] = []

    @staticmethod
    def _validate_evidence(evidence: dict[str, Any] | None) -> None:
        """Raise ValueError if evidence contains forbidden keys (transcript text or PII)."""
        if not evidence:
            return
        violations = _FORBIDDEN_EVIDENCE_KEYS & evidence.keys()
        if violations:
            raise ValueError(
                f"DecisionLogger.log() evidence contains forbidden key(s): {sorted(violations)}. "
                "Transcript text and customer PII must not be stored in decision records."
            )

    def log(
        self,
        decision_type: str,
        decision:      str,
        reason:        str,
        evidence:      dict[str, Any] | None = None,
        call_id:       str | None = None,
        confidence:    str | None = None,
        alternatives:  list[str] | None = None,
    ) -> None:
        """Record one decision."""
        self._validate_evidence(evidence)
        rec = DecisionRecord(
            agent=self._agent,
            decision_type=decision_type,
            decision=decision,
            reason=reason,
            evidence=evidence,
            call_id=call_id,
            confidence=confidence,
            alternatives=alternatives,
        )
        self._new.append(rec)
        log.debug(
            "[DecisionLog] %s | %s | %s (call=%s)",
            self._agent, decision_type, decision[:60], call_id or "-",
        )

    def finalize(self) -> list[dict]:
        """Return the full accumulated decision log (existing + new) as plain dicts."""
        return self._records + [r.to_dict() for r in self._new]

    @property
    def new_count(self) -> int:
        return len(self._new)


# ── Standalone helper ─────────────────────────────────────────────────

def summarize_decisions(decision_log: list[dict]) -> dict[str, Any]:
    """
    Build a compact summary of a decision log for inclusion in summary.json
    and the dashboard.

    Returns a dict with:
      total_decisions      — int
      by_agent             — {agent: count}
      by_type              — {decision_type: count}
      notable_decisions    — list of high-impact records (exclusions, gate fails, etc.)
    """
    if not decision_log:
        return {
            "total_decisions":   0,
            "by_agent":          {},
            "by_type":           {},
            "notable_decisions": [],
        }

    by_agent: dict[str, int] = {}
    by_type:  dict[str, int] = {}
    notable:  list[dict]     = []

    _notable_types = frozenset({
        "qa_exclusion", "quality_gate_outcome", "routing_decision",
        "approval_decision", "provider_selected", "react_trigger",
        "transcript_skip",
    })

    for rec in decision_log:
        agent = rec.get("agent", "unknown")
        dtype = rec.get("decision_type", "unknown")
        by_agent[agent] = by_agent.get(agent, 0) + 1
        by_type[dtype]  = by_type.get(dtype, 0) + 1
        if dtype in _notable_types:
            notable.append({
                "record_id":     rec.get("record_id"),
                "agent":         agent,
                "decision_type": dtype,
                "decision":      rec.get("decision", ""),
                "call_id":       rec.get("call_id"),
                "confidence":    rec.get("confidence"),
            })

    return {
        "total_decisions":   len(decision_log),
        "by_agent":          by_agent,
        "by_type":           by_type,
        "notable_decisions": notable[:20],  # cap at 20 for readability
    }
