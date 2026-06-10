"""
pipeline/memory.py  —  Agent Memory System
-------------------------------------------
Persistent cross-run memory for the multi-agent pipeline. Agents read
and write to this shared memory store so that each pipeline run can
learn from previous ones.

Memory layers:
  1. Run history     — FCR, AHT, QA score, cost per run (trend tracking)
  2. Failure log     — Which call types / intents fail extraction most often
  3. Model perf      — Latency and success rate per model variant
  4. Quota events    — When quota was exhausted (informs retry scheduling)

All data is persisted to outputs/agent_memory.json — a single JSON file
that agents can read at startup and update at completion.

Usage:
  memory = AgentMemory()
  memory.load()

  # At pipeline start (InsightsAgent reads this for context)
  history = memory.get_run_history(last_n=5)

  # At pipeline end (ExportAgent writes this)
  memory.record_run(run_data)
  memory.save()
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.logger import get_logger

log = get_logger(__name__)

MEMORY_PATH = Path("outputs/agent_memory.json")

_SCHEMA_VERSION = "1.0"


class AgentMemory:
    """
    Persistent cross-run memory store.

    Thread-safety: single-process writes only (one pipeline at a time).
    For concurrent pipelines, use a database backend instead.
    """

    def __init__(self, path: Path = MEMORY_PATH):
        self.path = path
        self._data: dict[str, Any] = self._empty()

    # ── Initialisation ────────────────────────────────────────────────

    def _empty(self) -> dict:
        return {
            "schema_version":  _SCHEMA_VERSION,
            "created_at":      datetime.now(UTC).isoformat(),
            "last_updated":    None,
            "total_runs":      0,
            "run_history":     [],       # list of run summaries (newest last)
            "failure_log":     [],       # list of failed call records
            "quota_events":    [],       # list of quota-exhaustion events
            "model_performance": {},     # model_name → {calls, successes, avg_latency_s}
            "cumulative": {
                "total_calls_analyzed": 0,
                "total_tokens":         0,
                "total_cost_usd":       0.0,
                "total_api_calls":      0,
            },
        }

    def load(self) -> AgentMemory:
        """Load memory from disk. Returns self for chaining."""
        if not self.path.exists():
            log.info("[AgentMemory] No memory file found — starting fresh")
            return self

        try:
            with open(self.path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            # Version check — reset if schema mismatch
            if loaded.get("schema_version") != _SCHEMA_VERSION:
                log.warning("[AgentMemory] Schema version mismatch — resetting memory")
                return self
            self._data = loaded
            log.info(
                "[AgentMemory] Loaded: %d runs  %d total calls  %.4f USD total cost",
                self._data["total_runs"],
                self._data["cumulative"]["total_calls_analyzed"],
                self._data["cumulative"]["total_cost_usd"],
            )
        except Exception as exc:
            log.warning("[AgentMemory] Load failed (%s) — starting fresh", exc)
        return self

    def save(self) -> None:
        """Persist memory to disk."""
        self.path.parent.mkdir(exist_ok=True)
        self._data["last_updated"] = datetime.now(UTC).isoformat()
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2)
        log.info("[AgentMemory] Saved to %s", self.path)

    # ── Write operations ──────────────────────────────────────────────

    def record_run(self, run_summary: dict) -> None:
        """
        Record the outcome of a completed pipeline run.

        Expected keys in run_summary:
            run_timestamp, n_analyzed, n_failed, fcr_rate_pct,
            avg_handle_time_minutes, qa_avg_score, qa_verdict,
            total_tokens, total_cost_usd, model, insights_source,
            offset, seed, n_calls
        """
        self._data["total_runs"] += 1

        entry = {
            "run_id":          self._data["total_runs"],
            "timestamp":       run_summary.get("run_timestamp", datetime.now().isoformat()),
            "offset":          run_summary.get("offset", 0),
            "seed":            run_summary.get("seed", 42),
            "n_requested":     run_summary.get("n_calls", 0),
            "n_analyzed":      run_summary.get("n_analyzed", 0),
            "n_failed":        run_summary.get("n_failed", 0),
            "fcr_rate_pct":    run_summary.get("fcr_rate_pct", 0),
            "aht_minutes":     run_summary.get("avg_handle_time_minutes", 0),
            "qa_avg_score":    run_summary.get("qa_avg_score", 0),
            "qa_verdict":      run_summary.get("qa_verdict", "N/A"),
            "total_tokens":    run_summary.get("total_tokens", 0),
            "total_cost_usd":  run_summary.get("total_cost_usd", 0),
            "model":           run_summary.get("model", "unknown"),
            "insights_source": run_summary.get("insights_source", "unknown"),
        }
        # Keep last 50 runs
        self._data["run_history"].append(entry)
        if len(self._data["run_history"]) > 50:
            self._data["run_history"] = self._data["run_history"][-50:]

        # Update cumulative counters
        c = self._data["cumulative"]
        c["total_calls_analyzed"] += entry["n_analyzed"]
        c["total_tokens"]         += entry["total_tokens"]
        c["total_cost_usd"]       += entry["total_cost_usd"]

    def record_failures(self, failed_ids: list[str], context: str = "") -> None:
        """Log failed call IDs for pattern analysis."""
        if not failed_ids:
            return
        entry = {
            "timestamp":  datetime.now(UTC).isoformat(),
            "context":    context,
            "failed_ids": failed_ids,
            "count":      len(failed_ids),
        }
        self._data["failure_log"].append(entry)
        # Keep last 20 failure events
        if len(self._data["failure_log"]) > 20:
            self._data["failure_log"] = self._data["failure_log"][-20:]

    def record_quota_event(self, model: str, provider: str) -> None:
        """Record a quota-exhaustion event for scheduling awareness."""
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "model":     model,
            "provider":  provider,
        }
        self._data["quota_events"].append(entry)
        if len(self._data["quota_events"]) > 10:
            self._data["quota_events"] = self._data["quota_events"][-10:]
        log.warning(
            "[AgentMemory] Quota event recorded: %s / %s", model, provider
        )

    def record_model_call(self, model: str, success: bool, latency_s: float) -> None:
        """Update per-model performance statistics."""
        if model not in self._data["model_performance"]:
            self._data["model_performance"][model] = {
                "calls":         0,
                "successes":     0,
                "total_latency": 0.0,
            }
        m = self._data["model_performance"][model]
        m["calls"]         += 1
        m["successes"]     += 1 if success else 0
        m["total_latency"] += latency_s

    # ── Read operations ───────────────────────────────────────────────

    def get_run_history(self, last_n: int = 5) -> list[dict]:
        """Return the most recent N run summaries (newest last)."""
        return self._data["run_history"][-last_n:]

    def get_trend_summary(self) -> dict:
        """Summarise trends across all recorded runs."""
        history = self._data["run_history"]
        if not history:
            return {"message": "No prior runs recorded"}

        n = len(history)
        avg_fcr  = sum(r["fcr_rate_pct"] for r in history) / n
        avg_aht  = sum(r["aht_minutes"]  for r in history) / n
        avg_qa   = sum(r["qa_avg_score"] for r in history) / n
        avg_cost = sum(r["total_cost_usd"] for r in history) / n

        return {
            "runs_in_memory":       n,
            "avg_fcr_rate_pct":     round(avg_fcr, 1),
            "avg_aht_minutes":      round(avg_aht, 2),
            "avg_qa_score":         round(avg_qa, 1),
            "avg_cost_usd_per_run": round(avg_cost, 4),
            "total_calls_analyzed": self._data["cumulative"]["total_calls_analyzed"],
            "total_cost_usd":       round(self._data["cumulative"]["total_cost_usd"], 4),
            "quota_events_count":   len(self._data["quota_events"]),
            "last_quota_event":     (
                self._data["quota_events"][-1]["timestamp"]
                if self._data["quota_events"] else None
            ),
        }

    def get_model_stats(self, model: str) -> dict:
        """Return performance stats for a specific model."""
        m = self._data["model_performance"].get(model, {})
        if not m or m.get("calls", 0) == 0:
            return {"model": model, "message": "No data"}
        calls = m["calls"]
        return {
            "model":           model,
            "total_calls":     calls,
            "success_rate_pct": round(m["successes"] / calls * 100, 1),
            "avg_latency_s":   round(m["total_latency"] / calls, 2),
        }

    def get_context_for_insights(self) -> str:
        """
        Return a concise text summary of historical performance
        for injection into the InsightsAgent LLM prompt.
        """
        trend = self.get_trend_summary()
        if "message" in trend:
            return "No historical data available — this is the first run."

        quota_note = ""
        if trend["quota_events_count"] > 0:
            quota_note = f" Quota exhaustion has occurred {trend['quota_events_count']} time(s)."

        return (
            f"Historical context from {trend['runs_in_memory']} prior run(s): "
            f"avg FCR={trend['avg_fcr_rate_pct']}%, "
            f"avg AHT={trend['avg_aht_minutes']} min, "
            f"avg QA={trend['avg_qa_score']}/100, "
            f"total {trend['total_calls_analyzed']} calls analyzed "
            f"at ${trend['total_cost_usd']} USD cumulative cost."
            f"{quota_note}"
        )

    @property
    def total_runs(self) -> int:
        return self._data["total_runs"]

    @property
    def cumulative(self) -> dict:
        return self._data["cumulative"]


# ── Module-level singleton (loaded on first import) ───────────────────

MEMORY = AgentMemory()
