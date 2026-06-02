"""
pipeline/governance.py  —  Agentic Governance Layer
------------------------------------------------------
Four guardrails that enforce safety, cost control, and data protection
across every pipeline run. All checks are stateless and called from
agent nodes before proceeding.

Components:
  BudgetGuard    — hard-stop if estimated API cost exceeds threshold
  QualityGate    — hard-stop if QA pass rate is catastrophically low
  PIIScanner     — detect and redact PII before transcript text reaches the LLM
  AuditLog       — structured, append-only record of every agent decision

Usage:
  from pipeline.governance import BUDGET_GUARD, QUALITY_GATE, PII_SCANNER, AUDIT_LOG
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.config import BUDGET_USD, MIN_PASS_RATE, QUALITY_WARN_RATE
from pipeline.logger import get_logger

log = get_logger(__name__)

OUTPUT_DIR = Path("outputs")


# ── 1. Budget Guard ───────────────────────────────────────────────────

class BudgetGuard:
    """
    Raises BudgetExceededError if cumulative inference cost exceeds max_cost_usd.

    Limit is driven by BUDGET_USD in pipeline/config.py — change it there and
    every run automatically inherits the new cap. Cost estimate uses the
    model-aware pricing from token_tracker.cost_usd(), so switching EXTRACTION_MODEL
    from Gemini to Claude (or back) gives accurate guard enforcement automatically.
    """

    class BudgetExceededError(RuntimeError):
        pass

    def __init__(self, max_cost_usd: float = 5.00):
        self.max_cost_usd = max_cost_usd

    def check(self, current_cost_usd: float, context: str = "") -> None:
        """
        Raise BudgetExceededError if over budget; otherwise log current spend.
        Call this after each ExtractionAgent batch completes.
        """
        pct = current_cost_usd / self.max_cost_usd * 100 if self.max_cost_usd > 0 else 0
        log.info(
            "[BudgetGuard] Cost: $%.4f / $%.2f (%.1f%%) %s",
            current_cost_usd, self.max_cost_usd, pct, context,
        )
        if current_cost_usd > self.max_cost_usd:
            raise self.BudgetExceededError(
                f"Pipeline stopped: cost ${current_cost_usd:.4f} exceeds budget "
                f"${self.max_cost_usd:.2f}. Adjust --budget or reduce batch size."
            )
        if pct >= 80:
            log.warning(
                "[BudgetGuard] Budget at %.1f%% — consider reducing batch size", pct
            )

    def estimate_remaining_calls(self, current_cost_usd: float, avg_cost_per_call: float) -> int:
        """How many more calls can we afford at the current per-call cost."""
        if avg_cost_per_call <= 0:
            return 9999
        remaining_budget = max(0, self.max_cost_usd - current_cost_usd)
        return int(remaining_budget / avg_cost_per_call)


# ── 2. Quality Gate ───────────────────────────────────────────────────

class QualityGate:
    """
    Raises QualityGateError if the extraction quality is catastrophically poor.

    Fires ONLY on critical failure (pass_rate < min_pass_rate) to protect
    aggregation and insights from garbage-in / garbage-out.

    Normal QA FAIL (pass_rate 50–89%) is non-blocking — LOW records are
    excluded from aggregation but the pipeline continues.
    """

    class QualityGateError(RuntimeError):
        pass

    def __init__(self, min_pass_rate: float = 0.40):
        self.min_pass_rate = min_pass_rate  # 40% default — catastrophic threshold

    def check(self, qa_report: dict) -> None:
        """
        Raise QualityGateError on catastrophic extraction failure.
        Called by quality_node after QualityAgent.run().
        """
        if not qa_report or qa_report.get("dataset_verdict") == "SKIP":
            return  # no results — handled upstream

        summary    = qa_report.get("summary", {})
        pass_rate  = summary.get("pass_rate_pct", 100) / 100  # convert pct → fraction
        n_audited  = qa_report.get("total_calls_audited", 0)
        avg_score  = summary.get("avg_score", 100)

        log.info(
            "[QualityGate] pass_rate=%.1f%%  avg_score=%.1f  n=%d  threshold=%.0f%%",
            pass_rate * 100, avg_score, n_audited, self.min_pass_rate * 100,
        )

        if pass_rate < QUALITY_WARN_RATE:
            log.warning(
                "[QualityGate] WARNING: pass_rate=%.1f%% is below quality warning threshold %.0f%% "
                "— aggregation will run on a degraded dataset. Check extraction model and prompt.",
                pass_rate * 100, QUALITY_WARN_RATE * 100,
            )

        if pass_rate < self.min_pass_rate:
            raise self.QualityGateError(
                f"Pipeline stopped: QA pass rate {pass_rate*100:.1f}% is below "
                f"minimum {self.min_pass_rate*100:.0f}%. "
                f"Avg score: {avg_score}/100 across {n_audited} calls. "
                "Check system prompt and model settings."
            )


# ── 3. PII Scanner ────────────────────────────────────────────────────

_PII_PATTERNS: dict[str, re.Pattern] = {
    "phone_us":    re.compile(r'\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
    "ssn":         re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
    "email":       re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'),
    "credit_card": re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
    "dob":         re.compile(
        r'\b(?:born|dob|date of birth)[:\s]+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
        re.IGNORECASE,
    ),
    "account_num": re.compile(r'\baccount\s*(?:number|#|no\.?)[:\s]*\d{6,12}\b', re.IGNORECASE),
}

_REDACTION_TOKEN = "[REDACTED]"


class PIIScanner:
    """
    Scans transcript text for PII before it is sent to the LLM.

    The telecom corpus is synthetic/anonymised, but this scanner guards
    against any real data that might accidentally appear in custom datasets.
    """

    def scan(self, text: str) -> list[str]:
        """Return list of PII type names found in text (empty = clean)."""
        found = []
        for pii_type, pattern in _PII_PATTERNS.items():
            if pattern.search(text):
                found.append(pii_type)
        return found

    def redact(self, text: str) -> tuple[str, list[str]]:
        """
        Replace PII patterns with [REDACTED].
        Returns (redacted_text, list_of_types_found).
        """
        found  = []
        result = text
        for pii_type, pattern in _PII_PATTERNS.items():
            new_text, n = re.subn(pattern, _REDACTION_TOKEN, result)
            if n > 0:
                found.append(pii_type)
                result = new_text
        return result, found

    def scan_transcript(self, transcript: dict) -> dict:
        """
        Scan a transcript dict. If PII is detected, redact it and log.
        Returns (possibly modified) transcript dict.
        """
        text = transcript.get("transcript_text", "")
        redacted_text, found = self.redact(text)

        if found:
            log.warning(
                "[PIIScanner] PII detected in call %s: %s — redacting",
                str(transcript.get("call_id", "?"))[:12],
                ", ".join(found),
            )
            return {**transcript, "transcript_text": redacted_text, "_pii_redacted": found}

        return transcript


# ── 4. Audit Log ──────────────────────────────────────────────────────

@dataclass
class AuditEntry:
    timestamp:  str
    event_type: str   # "agent_start" | "agent_end" | "tool_call" | "governance_check" | "error"
    agent:      str
    data:       dict  = field(default_factory=dict)


class AuditLog:
    """
    Structured, append-only record of every agent action in the pipeline.

    Written to outputs/audit_log_{ts}.json at pipeline end.
    Provides full decision trace for compliance, debugging, and review.
    """

    def __init__(self):
        self._entries: list[AuditEntry] = []
        self._ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    def record_agent_start(self, agent: str, inputs: dict) -> None:
        self._entries.append(AuditEntry(
            timestamp  = self._now(),
            event_type = "agent_start",
            agent      = agent,
            data       = {"input_keys": list(inputs.keys())},
        ))

    def record_agent_end(self, agent: str, outputs: dict, elapsed_s: float) -> None:
        self._entries.append(AuditEntry(
            timestamp  = self._now(),
            event_type = "agent_end",
            agent      = agent,
            data       = {
                "output_keys": list(outputs.keys()),
                "elapsed_s":   round(elapsed_s, 3),
            },
        ))

    def record_tool_call(
        self,
        tool:      str,
        agent:     str,
        inputs:    list[str],
        success:   bool,
        elapsed_s: float,
        error:     str = "",
    ) -> None:
        self._entries.append(AuditEntry(
            timestamp  = self._now(),
            event_type = "tool_call",
            agent      = agent,
            data       = {
                "tool":      tool,
                "input_keys": inputs,
                "success":   success,
                "elapsed_s": elapsed_s,
                "error":     error,
            },
        ))

    def record_governance(
        self,
        check:   str,
        passed:  bool,
        details: dict,
    ) -> None:
        self._entries.append(AuditEntry(
            timestamp  = self._now(),
            event_type = "governance_check",
            agent      = "Governance",
            data       = {"check": check, "passed": passed, **details},
        ))

    def record_pii(self, call_id: str, pii_types: list[str]) -> None:
        self._entries.append(AuditEntry(
            timestamp  = self._now(),
            event_type = "pii_detection",
            agent      = "PIIScanner",
            data       = {"call_id": call_id[:12], "pii_types": pii_types},
        ))

    def record_error(self, agent: str, error: str, context: dict = None) -> None:
        self._entries.append(AuditEntry(
            timestamp  = self._now(),
            event_type = "error",
            agent      = agent,
            data       = {"error": error[:500], "context": context or {}},
        ))

    def export(self, output_dir: Path = OUTPUT_DIR) -> Path:
        """Write the audit log to disk and return the path."""
        output_dir.mkdir(exist_ok=True)
        path = output_dir / f"audit_log_{self._ts}.json"
        payload = {
            "audit_log_version": "1.0",
            "generated_at":      self._now(),
            "total_events":      len(self._entries),
            "events": [
                {
                    "timestamp":  e.timestamp,
                    "event_type": e.event_type,
                    "agent":      e.agent,
                    "data":       e.data,
                }
                for e in self._entries
            ],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        log.info("[AuditLog] Written: %d events → %s", len(self._entries), path)
        return path

    def summary(self) -> dict:
        from collections import Counter
        types  = Counter(e.event_type for e in self._entries)
        agents = Counter(e.agent      for e in self._entries)
        errors = [e for e in self._entries if e.event_type == "error"]
        return {
            "total_events":   len(self._entries),
            "by_type":        dict(types),
            "by_agent":       dict(agents),
            "error_count":    len(errors),
        }


# ── Module-level singletons ───────────────────────────────────────────
# Both limits read from pipeline/config.py — change them there, not here.

BUDGET_GUARD  = BudgetGuard(max_cost_usd=BUDGET_USD)
QUALITY_GATE  = QualityGate(min_pass_rate=MIN_PASS_RATE)
PII_SCANNER   = PIIScanner()
AUDIT_LOG     = AuditLog()
