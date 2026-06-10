"""
pipeline/orchestrator.py  —  Pipeline Orchestrator
-----------------------------------------------------
The Orchestrator sits above the LangGraph graph. It is responsible for:

  1. Work planning   — decides how to split a large job across batches,
                       balancing API rate limits with throughput targets
  2. Health monitoring — tracks per-agent success/failure rates in real time
  3. Adaptive retry  — re-queues failed batches with adjusted parameters
  4. Progress reporting — emits a structured orchestration report at the end

Design: The Orchestrator does NOT replace LangGraph. It wraps it. Each
pipeline.invoke() call is one "task" from the Orchestrator's perspective.
Multiple tasks may be run sequentially (free tier) or concurrently (paid
tier) depending on the rate_limit_rpm parameter.

Usage:
    from pipeline.orchestrator import Orchestrator

    orch = Orchestrator(total_calls=100, batch_size=20, rate_limit_rpm=15)
    report = orch.run()
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime

from pipeline.config import BUDGET_USD, OUTPUT_DIR
from pipeline.logger import get_logger
from pipeline.memory import MEMORY

log = get_logger(__name__)

# Sentinel written by analyzer.py when Gemini daily quota is exhausted
_QUOTA_SENTINEL = OUTPUT_DIR / ".react_quota_exhausted"


# ── Work unit ─────────────────────────────────────────────────────────

@dataclass
class BatchTask:
    """Represents a single unit of work for the orchestrator."""
    task_id:    int
    offset:     int
    n_calls:    int
    seed:       int
    delay:      float
    status:     str  = "pending"   # pending | running | done | failed | retrying
    attempts:   int  = 0
    max_retries: int = 2
    n_ok:       int  = 0
    n_failed:   int  = 0
    elapsed_s:  float = 0.0
    exit_code:  int  = -1
    error_msg:  str  = ""

    @property
    def checkpoint_key(self) -> str:
        return f"offset{self.offset}_n{self.n_calls}_seed{self.seed}"

    @property
    def can_retry(self) -> bool:
        return self.attempts < self.max_retries and self.status == "failed"


# ── Agent health tracker ──────────────────────────────────────────────

@dataclass
class AgentHealthMonitor:
    """Tracks per-agent success/failure counts across all tasks."""
    _stats: dict = field(default_factory=dict)

    def record(self, agent: str, success: bool, elapsed_s: float = 0) -> None:
        if agent not in self._stats:
            self._stats[agent] = {"calls": 0, "successes": 0, "total_elapsed": 0.0}
        s = self._stats[agent]
        s["calls"]         += 1
        s["successes"]     += 1 if success else 0
        s["total_elapsed"] += elapsed_s

    def summary(self) -> dict:
        result = {}
        for agent, s in self._stats.items():
            calls = s["calls"]
            result[agent] = {
                "calls":           calls,
                "success_rate_pct": round(s["successes"] / calls * 100, 1) if calls else 0,
                "avg_elapsed_s":   round(s["total_elapsed"] / calls, 2) if calls else 0,
            }
        return result

    def is_healthy(self, agent: str, min_success_rate: float = 0.5) -> bool:
        s = self._stats.get(agent)
        if not s or s["calls"] == 0:
            return True  # no data = assume healthy
        return (s["successes"] / s["calls"]) >= min_success_rate


# ── Work planner ──────────────────────────────────────────────────────

class WorkPlanner:
    """
    Generates the sequence of BatchTasks for a given job configuration.

    Guarantees non-overlapping offsets across all tasks.
    """

    @staticmethod
    def plan(
        total_calls: int,
        batch_size:  int,
        seed:        int = 42,
        delay:       float = 2.0,
        max_retries: int = 2,
    ) -> list[BatchTask]:
        n_batches = (total_calls + batch_size - 1) // batch_size  # ceiling division
        tasks = []
        for i in range(n_batches):
            offset   = i * batch_size
            n        = min(batch_size, total_calls - offset)
            tasks.append(BatchTask(
                task_id     = i + 1,
                offset      = offset,
                n_calls     = n,
                seed        = seed,
                delay       = delay,
                max_retries = max_retries,
            ))
        return tasks

    @staticmethod
    def estimate_duration(tasks: list[BatchTask], avg_call_s: float = 10.0) -> float:
        """Estimate total wall-clock time in minutes for a task list."""
        total_calls = sum(t.n_calls for t in tasks)
        return round(total_calls * (avg_call_s + 2.0) / 60, 1)  # +2s delay


# ── Orchestrator ──────────────────────────────────────────────────────

class Orchestrator:
    """
    Top-level coordinator for the multi-agent pipeline.

    Runs each BatchTask as a subprocess (process isolation: a crashed batch
    cannot corrupt other batches' state). Monitors health, retries failures,
    and produces a final orchestration report.
    """

    def __init__(
        self,
        total_calls:     int   = 100,
        batch_size:      int   = 20,
        seed:            int   = 42,
        delay:           float = 2.0,
        rate_limit_rpm:  int   = 15,
        max_retries:     int   = 2,
    ):
        self.total_calls    = total_calls
        self.batch_size     = batch_size
        self.seed           = seed
        self.delay          = delay
        self.rate_limit_rpm = rate_limit_rpm
        self.max_retries    = max_retries

        self.health         = AgentHealthMonitor()
        self.tasks          = WorkPlanner.plan(total_calls, batch_size, seed, delay, max_retries)
        self._started_at    = datetime.now()
        # Per-batch budget = total budget divided equally across all batches.
        # Prevents a single subprocess from consuming the entire budget while
        # sibling batches (even sequential) would then exceed the global cap.
        n_batches = len(self.tasks) or 1
        self._budget_per_batch = round(BUDGET_USD / n_batches, 4)

    # ── Public API ────────────────────────────────────────────────────

    def run(self) -> dict:
        """
        Execute all planned tasks. Returns the orchestration report.
        Sequential execution respects the free-tier rate limit (15 RPM).
        """
        self._print_plan()
        est = WorkPlanner.estimate_duration(self.tasks)
        print(f"  Estimated duration : ~{est} min  ({self.rate_limit_rpm} RPM limit)")
        print(f"  Budget per batch   : ${self._budget_per_batch:.4f}  "
              f"(${BUDGET_USD:.2f} / {len(self.tasks)} batches)\n")

        # Clear any stale Gemini quota sentinel from a previous run so the
        # circuit breaker starts fresh for this new orchestration.
        if _QUOTA_SENTINEL.exists():
            _QUOTA_SENTINEL.unlink()
            log.info("[Orchestrator] Cleared stale Gemini quota sentinel from previous run.")

        queue = list(self.tasks)  # work queue (includes retries)

        while queue:
            task = queue.pop(0)
            self._run_task(task)

            # Retry logic
            if task.status == "failed" and task.can_retry:
                task.status   = "retrying"
                task.attempts += 1
                log.warning(
                    "[Orchestrator] Task %d failed — scheduling retry %d/%d",
                    task.task_id, task.attempts, task.max_retries,
                )
                print(f"\n  ⟳ Retry {task.attempts}/{task.max_retries} for batch {task.task_id} "
                      f"(offset={task.offset})\n")
                queue.insert(0, task)  # retry immediately (at front of queue)

        # Final merge + report
        report = self._build_report()
        self._print_report(report)

        # Record orchestration run in agent memory
        self._update_memory(report)

        return report

    # ── Task execution ────────────────────────────────────────────────

    def _run_task(self, task: BatchTask) -> None:
        # task.attempts counts *retries consumed* (incremented by run() when a
        # retry is scheduled) — incrementing it here too would burn a retry per run.
        task.status = "running"
        t0 = time.monotonic()

        log.info(
            "[Orchestrator] Starting task %d/%d: offset=%d n=%d attempt=%d",
            task.task_id, len(self.tasks), task.offset, task.n_calls, task.attempts + 1,
        )

        cmd = [
            sys.executable, "run_pipeline.py",
            "--n",      str(task.n_calls),
            "--offset", str(task.offset),
            "--seed",   str(task.seed),
            "--delay",  str(task.delay),
            "--budget", str(self._budget_per_batch),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=False,  # let stdout/stderr flow to terminal
                timeout=600,           # 10-minute per-batch timeout
            )
            task.elapsed_s = time.monotonic() - t0
            task.exit_code = result.returncode

            if result.returncode == 0:
                task.status = "done"
                self.health.record("ExtractionAgent", success=True, elapsed_s=task.elapsed_s)
                log.info(
                    "[Orchestrator] Task %d DONE in %.1fs",
                    task.task_id, task.elapsed_s,
                )
            else:
                task.status    = "failed"
                task.error_msg = f"exit code {result.returncode}"
                self.health.record("ExtractionAgent", success=False, elapsed_s=task.elapsed_s)
                log.error(
                    "[Orchestrator] Task %d FAILED (exit %d) in %.1fs",
                    task.task_id, result.returncode, task.elapsed_s,
                )

        except subprocess.TimeoutExpired:
            task.status    = "failed"
            task.error_msg = "timeout (600s)"
            task.elapsed_s = time.monotonic() - t0
            log.error("[Orchestrator] Task %d TIMED OUT", task.task_id)

        except Exception as exc:
            task.status    = "failed"
            task.error_msg = str(exc)[:200]
            task.elapsed_s = time.monotonic() - t0
            log.exception("[Orchestrator] Task %d unexpected error: %s", task.task_id, exc)

    # ── Report ────────────────────────────────────────────────────────

    def _build_report(self) -> dict:
        total_elapsed = (datetime.now() - self._started_at).total_seconds()
        done   = [t for t in self.tasks if t.status == "done"]
        failed = [t for t in self.tasks if t.status == "failed"]

        return {
            "orchestrator_version":  "1.0",
            "generated_at":          datetime.now().isoformat(),
            "configuration": {
                "total_calls":    self.total_calls,
                "batch_size":     self.batch_size,
                "n_batches":      len(self.tasks),
                "seed":           self.seed,
                "delay_s":        self.delay,
                "rate_limit_rpm": self.rate_limit_rpm,
            },
            "execution_summary": {
                "tasks_total":     len(self.tasks),
                "tasks_done":      len(done),
                "tasks_failed":    len(failed),
                "total_elapsed_s": round(total_elapsed, 1),
                "total_elapsed_min": round(total_elapsed / 60, 1),
                "success_rate_pct": round(len(done) / len(self.tasks) * 100, 1) if self.tasks else 0,
            },
            "agent_health": self.health.summary(),
            "task_details": [
                {
                    "task_id":    t.task_id,
                    "offset":     t.offset,
                    "n_calls":    t.n_calls,
                    "status":     t.status,
                    "attempts":   t.attempts,
                    "elapsed_s":  round(t.elapsed_s, 1),
                    "error":      t.error_msg,
                }
                for t in self.tasks
            ],
            "failed_task_ids": [t.task_id for t in failed],
        }

    def _print_plan(self) -> None:
        print("\n" + "▓" * 60)
        print("  PIPELINE ORCHESTRATOR — Work Plan")
        print("▓" * 60)
        print(f"  Total calls  : {self.total_calls}")
        print(f"  Batch size   : {self.batch_size}")
        print(f"  Batches      : {len(self.tasks)}")
        print(f"  Rate limit   : {self.rate_limit_rpm} RPM (free tier)")
        print(f"  Max retries  : {self.max_retries} per batch")
        print("  Execution    : sequential (rate-limit safe)")
        print(f"  {'─' * 54}")
        for t in self.tasks:
            print(f"  Task {t.task_id:02d} │ offset={t.offset:<4} n={t.n_calls:<3} "
                  f"checkpoint={t.checkpoint_key}")
        print("▓" * 60)

    def _print_report(self, report: dict) -> None:
        s = report["execution_summary"]
        h = report["agent_health"]

        print("\n" + "▓" * 60)
        print("  ORCHESTRATION REPORT")
        print("▓" * 60)
        print(f"  Tasks done   : {s['tasks_done']} / {s['tasks_total']}")
        print(f"  Success rate : {s['success_rate_pct']}%")
        print(f"  Total time   : {s['total_elapsed_min']} min")

        if h:
            print("\n  Agent health:")
            for agent, stats in h.items():
                print(f"    {agent:<25} success={stats['success_rate_pct']}%  "
                      f"avg={stats['avg_elapsed_s']}s/call")

        if report["failed_task_ids"]:
            print(f"\n  Failed task IDs: {report['failed_task_ids']}")
            print("  Re-run run_batches.py — completed calls resume from checkpoints automatically")

        print("▓" * 60 + "\n")

    def _update_memory(self, report: dict) -> None:
        try:
            MEMORY.load()
            # Record each quota event detected (failed tasks)
            if report["failed_task_ids"]:
                from pipeline.token_tracker import MODEL as CURRENT_MODEL
                from pipeline.token_tracker import PROVIDER as CURRENT_PROVIDER
                MEMORY.record_quota_event(CURRENT_MODEL, CURRENT_PROVIDER)
            MEMORY.save()
        except Exception as exc:
            log.warning("[Orchestrator] Memory update failed: %s", exc)

    # ── Context manager support ───────────────────────────────────────

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass
