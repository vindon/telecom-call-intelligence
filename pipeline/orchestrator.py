"""
pipeline/orchestrator.py  —  Pipeline Orchestrator
-----------------------------------------------------
The Orchestrator sits above the LangGraph graph. It is responsible for:

  1. Work planning   — decides how to split a large job across batches,
                       balancing API rate limits with throughput targets
  2. Health monitoring — tracks per-agent success/failure rates in real time
  3. Strict failure policy — the first task failure halts the entire run and
                       requires explicit human review (--acknowledge-halt)
                       before any further batch runs; no automatic retry
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

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime

from pipeline.config import (
    BUDGET_USD,
    GEMINI_QUOTA_SENTINEL,
    NVIDIA_UNAVAILABLE_SENTINEL,
    OUTPUT_DIR,
)
from pipeline.logger import get_logger
from pipeline.memory import MEMORY

log = get_logger(__name__)

# Sentinel written by analyzer.py's circuit breaker when Gemini daily quota is exhausted
_QUOTA_SENTINEL = GEMINI_QUOTA_SENTINEL
# Sentinel written by insights_agent.py's circuit breaker when NVIDIA NIM times out
_NVIDIA_SENTINEL = NVIDIA_UNAVAILABLE_SENTINEL
# Sentinel written by Orchestrator when a batch fails — see run()'s strict
# human-intervention policy. Blocks every subsequent orchestration run until
# a human explicitly clears it (run_batches.py --acknowledge-halt). Added
# 2026-08-09 after two batches silently auto-retried into a hang, burning
# real API spend on discarded work before a human noticed.
_HALT_SENTINEL = OUTPUT_DIR / ".halted_for_human_review.json"


def clear_halt_sentinel() -> bool:
    """Explicit human acknowledgment that a prior halt has been reviewed. Returns True if a sentinel was cleared."""
    if _HALT_SENTINEL.exists():
        _HALT_SENTINEL.unlink()
        return True
    return False


# ── Work unit ─────────────────────────────────────────────────────────


@dataclass
class BatchTask:
    """Represents a single unit of work for the orchestrator."""

    task_id: int
    offset: int
    n_calls: int
    seed: int
    delay: float
    status: str = "pending"  # pending | running | done | failed
    n_ok: int = 0
    n_failed: int = 0
    elapsed_s: float = 0.0
    exit_code: int = -1
    error_msg: str = ""
    # Populated from that batch's own run_manifest_{ts}.json after a successful
    # subprocess exit — exit code 0 only means the process didn't crash, not
    # that every requested call actually succeeded (analyze_batch continues
    # past individual call failures). See _record_task_outcome().
    qa_verdict: str = ""
    data_quality_pass_rate_pct: float | None = None
    failed_call_ids: list = field(default_factory=list)

    @property
    def checkpoint_key(self) -> str:
        return f"offset{self.offset}_n{self.n_calls}_seed{self.seed}"


# ── Agent health tracker ──────────────────────────────────────────────


@dataclass
class AgentHealthMonitor:
    """Tracks per-agent success/failure counts across all tasks."""

    _stats: dict = field(default_factory=dict)

    def record(self, agent: str, success: bool, elapsed_s: float = 0) -> None:
        if agent not in self._stats:
            self._stats[agent] = {"calls": 0, "successes": 0, "total_elapsed": 0.0}
        s = self._stats[agent]
        s["calls"] += 1
        s["successes"] += 1 if success else 0
        s["total_elapsed"] += elapsed_s

    def summary(self) -> dict:
        result = {}
        for agent, s in self._stats.items():
            calls = s["calls"]
            result[agent] = {
                "calls": calls,
                "success_rate_pct": round(s["successes"] / calls * 100, 1) if calls else 0,
                "avg_elapsed_s": round(s["total_elapsed"] / calls, 2) if calls else 0,
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
        batch_size: int,
        seed: int = 42,
        delay: float = 2.0,
        start_offset: int = 0,
    ) -> list[BatchTask]:
        n_batches = (total_calls + batch_size - 1) // batch_size  # ceiling division
        tasks = []
        for i in range(n_batches):
            offset = start_offset + i * batch_size
            n = min(batch_size, total_calls - i * batch_size)
            tasks.append(
                BatchTask(
                    task_id=i + 1,
                    offset=offset,
                    n_calls=n,
                    seed=seed,
                    delay=delay,
                )
            )
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
    cannot corrupt other batches' state). Monitors health, halts immediately
    on the first failure (see run()'s strict human-intervention policy — no
    auto-retry), and produces a final orchestration report.
    """

    def __init__(
        self,
        total_calls: int = 100,
        batch_size: int = 20,
        seed: int = 42,
        delay: float = 2.0,
        rate_limit_rpm: int = 15,
        start_offset: int = 0,
    ):
        self.total_calls = total_calls
        self.batch_size = batch_size
        self.seed = seed
        self.delay = delay
        self.rate_limit_rpm = rate_limit_rpm
        self.start_offset = start_offset

        self.health = AgentHealthMonitor()
        self.tasks = WorkPlanner.plan(
            total_calls,
            batch_size,
            seed,
            delay,
            start_offset,
        )
        self._started_at = datetime.now()
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

        Strict human-intervention policy: the FIRST task failure halts the
        entire run immediately — no automatic retry, no proceeding to the
        next batch. A live-API failure (hang, timeout, crash) is exactly the
        situation where auto-retry silently compounds spend on discarded
        work (confirmed in production 2026-08-09: two batches each retried
        twice into the same hang before a human noticed). A halt sentinel
        is written to disk and blocks every subsequent orchestration run —
        see run_batches.py --acknowledge-halt — until a human has reviewed
        what happened and explicitly chooses to continue.
        """
        if _HALT_SENTINEL.exists():
            halt = json.loads(_HALT_SENTINEL.read_text())
            print("\n" + "!" * 60)
            print("  HALTED — PRIOR RUN REQUIRES HUMAN REVIEW")
            print("!" * 60)
            print(f"  Halted at    : {halt.get('halted_at')}")
            print(
                f"  Failed task  : {halt.get('task_id')}  offset={halt.get('offset')}  n={halt.get('n_calls')}"
            )
            print(f"  Reason       : {halt.get('reason')}")
            print(f"  Error        : {halt.get('error')}")
            print(f"  Completed OK : {halt.get('tasks_completed_before_halt')}")
            print("\n  This run has NOT started. Review the failure above, then either:")
            print("    - Fix the underlying issue and re-run with --acknowledge-halt, or")
            print("    - Investigate outputs/pipeline.log around the timestamp above first.")
            print("!" * 60 + "\n")
            return {
                "halted_pending_review": True,
                "halt_details": halt,
                "execution_summary": {
                    "tasks_total": len(self.tasks),
                    "tasks_done": 0,
                    "tasks_failed": 0,
                },
            }

        self._print_plan()
        est = WorkPlanner.estimate_duration(self.tasks)
        print(f"  Estimated duration : ~{est} min  ({self.rate_limit_rpm} RPM limit)")
        print(
            f"  Budget per batch   : ${self._budget_per_batch:.4f}  "
            f"(${BUDGET_USD:.2f} / {len(self.tasks)} batches)"
        )
        print(
            "  Failure policy     : STRICT — any task failure halts the run immediately; "
            "no auto-retry (see --acknowledge-halt)\n"
        )

        # Clear any stale provider-unavailable sentinels from a previous run so
        # each circuit breaker starts fresh for this new orchestration — a
        # provider that was down last run may be back up now.
        if _QUOTA_SENTINEL.exists():
            _QUOTA_SENTINEL.unlink()
            log.info("[Orchestrator] Cleared stale Gemini quota sentinel from previous run.")
        if _NVIDIA_SENTINEL.exists():
            _NVIDIA_SENTINEL.unlink()
            log.info("[Orchestrator] Cleared stale NVIDIA-unavailable sentinel from previous run.")

        queue = list(self.tasks)

        while queue:
            task = queue.pop(0)
            self._run_task(task)

            if task.status == "failed":
                self._write_halt_sentinel(task)
                log.error(
                    "[Orchestrator] Task %d failed — HALTING per strict human-intervention "
                    "policy (no auto-retry). %d task(s) never started.",
                    task.task_id,
                    len(queue),
                )
                print(
                    f"\n  ✗ Task {task.task_id} (offset={task.offset}) FAILED — "
                    f"halting run. {len(queue)} remaining task(s) NOT started."
                )
                print(f"  Sentinel written: {_HALT_SENTINEL}")
                print("  Review outputs/pipeline.log, then re-run with --acknowledge-halt.\n")
                break

        # Final merge + report
        report = self._build_report()
        self._print_report(report)

        # Record orchestration run in agent memory
        self._update_memory(report)

        return report

    def _write_halt_sentinel(self, failed_task: BatchTask) -> None:
        """Persist why the run halted so the next invocation refuses to start blind."""
        OUTPUT_DIR.mkdir(exist_ok=True)
        completed = [t.task_id for t in self.tasks if t.status == "done"]
        halt_info = {
            "halted_at": datetime.now().isoformat(),
            "task_id": failed_task.task_id,
            "offset": failed_task.offset,
            "n_calls": failed_task.n_calls,
            "error": failed_task.error_msg,
            "exit_code": failed_task.exit_code,
            "elapsed_s": round(failed_task.elapsed_s, 1),
            "reason": (
                "Task failed (timeout or non-zero exit) — strict human-intervention "
                "policy halts on the first failure instead of auto-retrying, since "
                "auto-retry on a live-API hang silently compounds spend on discarded work."
            ),
            "tasks_completed_before_halt": completed,
        }
        _HALT_SENTINEL.write_text(json.dumps(halt_info, indent=2))

    # ── Task execution ────────────────────────────────────────────────

    def _run_task(self, task: BatchTask) -> None:
        task.status = "running"
        t0 = time.monotonic()

        log.info(
            "[Orchestrator] Starting task %d/%d: offset=%d n=%d",
            task.task_id,
            len(self.tasks),
            task.offset,
            task.n_calls,
        )

        cmd = [
            sys.executable,
            "run_pipeline.py",
            "--n",
            str(task.n_calls),
            "--offset",
            str(task.offset),
            "--seed",
            str(task.seed),
            "--delay",
            str(task.delay),
            "--budget",
            str(self._budget_per_batch),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=False,  # let stdout/stderr flow to terminal
                timeout=600,  # 10-minute per-batch timeout
            )
            task.elapsed_s = time.monotonic() - t0
            task.exit_code = result.returncode

            if result.returncode == 0:
                task.status = "done"
                self._record_task_outcome(task)
                self.health.record("ExtractionAgent", success=True, elapsed_s=task.elapsed_s)
                log.info(
                    "[Orchestrator] Task %d DONE in %.1fs  (n_ok=%d n_failed=%d)",
                    task.task_id,
                    task.elapsed_s,
                    task.n_ok,
                    task.n_failed,
                )
                if task.n_failed:
                    log.warning(
                        "[Orchestrator] Task %d exited 0 but %d/%d call(s) failed inside the "
                        "batch (see that run's failed_call_ids) — subprocess exit code alone "
                        "does not guarantee every requested call succeeded.",
                        task.task_id,
                        task.n_failed,
                        task.n_calls,
                    )
            else:
                task.status = "failed"
                task.error_msg = f"exit code {result.returncode}"
                self.health.record("ExtractionAgent", success=False, elapsed_s=task.elapsed_s)
                log.error(
                    "[Orchestrator] Task %d FAILED (exit %d) in %.1fs",
                    task.task_id,
                    result.returncode,
                    task.elapsed_s,
                )

        except subprocess.TimeoutExpired:
            task.status = "failed"
            task.error_msg = "timeout (600s)"
            task.elapsed_s = time.monotonic() - t0
            self.health.record("ExtractionAgent", success=False, elapsed_s=task.elapsed_s)
            log.error("[Orchestrator] Task %d TIMED OUT", task.task_id)

        except Exception as exc:
            task.status = "failed"
            task.error_msg = str(exc)[:200]
            task.elapsed_s = time.monotonic() - t0
            self.health.record("ExtractionAgent", success=False, elapsed_s=task.elapsed_s)
            log.exception("[Orchestrator] Task %d unexpected error: %s", task.task_id, exc)

    def _record_task_outcome(self, task: BatchTask) -> None:
        """
        Read back this batch's own run_manifest_{ts}.json to find out how many
        of the n_calls requested actually succeeded, and whether the data
        quality gate (QualityAgent — phase reconciliation, timestamp ground
        truth, transcript completeness) passed for this batch. Safe to call
        right after a successful subprocess exit because Orchestrator runs
        batches strictly sequentially — the most recently written manifest is
        unambiguously this task's own.
        """
        manifests = sorted(
            OUTPUT_DIR.glob("run_manifest_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not manifests:
            log.warning(
                "[Orchestrator] Task %d: no run_manifest found to verify outcome", task.task_id
            )
            return

        latest = manifests[-1]
        try:
            manifest = json.loads(latest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("[Orchestrator] Task %d: could not read %s (%s)", task.task_id, latest, exc)
            return

        if manifest.get("offset") != task.offset:
            log.warning(
                "[Orchestrator] Task %d: latest manifest offset=%s doesn't match task offset=%d "
                "— skipping outcome verification for this task",
                task.task_id,
                manifest.get("offset"),
                task.offset,
            )
            return

        task.n_ok = manifest.get("n_analyzed", 0)
        task.n_failed = len(manifest.get("failed_call_ids", []))
        task.qa_verdict = manifest.get("qa_verdict", "N/A")
        task.data_quality_pass_rate_pct = manifest.get("data_quality_pass_rate_pct")
        task.failed_call_ids = manifest.get("failed_call_ids", [])

    # ── Report ────────────────────────────────────────────────────────

    def _build_report(self) -> dict:
        total_elapsed = (datetime.now() - self._started_at).total_seconds()
        done = [t for t in self.tasks if t.status == "done"]
        failed = [t for t in self.tasks if t.status == "failed"]

        total_n_ok = sum(t.n_ok for t in done)
        total_n_failed = sum(t.n_failed for t in done)
        all_failed_ids = [cid for t in done for cid in t.failed_call_ids]
        dq_rates = [
            t.data_quality_pass_rate_pct for t in done if t.data_quality_pass_rate_pct is not None
        ]

        return {
            "orchestrator_version": "1.0",
            "generated_at": datetime.now().isoformat(),
            "configuration": {
                "total_calls": self.total_calls,
                "batch_size": self.batch_size,
                "n_batches": len(self.tasks),
                "seed": self.seed,
                "delay_s": self.delay,
                "rate_limit_rpm": self.rate_limit_rpm,
                "start_offset": self.start_offset,
            },
            "execution_summary": {
                "tasks_total": len(self.tasks),
                "tasks_done": len(done),
                "tasks_failed": len(failed),
                "total_elapsed_s": round(total_elapsed, 1),
                "total_elapsed_min": round(total_elapsed / 60, 1),
                "success_rate_pct": round(len(done) / len(self.tasks) * 100, 1)
                if self.tasks
                else 0,
                # Completeness at the CALL level, not just the batch level — a
                # batch subprocess can exit 0 while some of its calls still
                # failed internally (see _record_task_outcome).
                "calls_requested": self.total_calls,
                "calls_analyzed": total_n_ok,
                "calls_failed": total_n_failed,
                "calls_complete": total_n_ok == self.total_calls and total_n_failed == 0,
                "failed_call_ids": all_failed_ids,
                "data_quality_pass_rate_pct_by_batch": [round(r, 1) for r in dq_rates],
            },
            "agent_health": self.health.summary(),
            "task_details": [
                {
                    "task_id": t.task_id,
                    "offset": t.offset,
                    "n_calls": t.n_calls,
                    "status": t.status,
                    "elapsed_s": round(t.elapsed_s, 1),
                    "error": t.error_msg,
                    "n_ok": t.n_ok,
                    "n_failed": t.n_failed,
                    "qa_verdict": t.qa_verdict,
                    "data_quality_pass_rate_pct": t.data_quality_pass_rate_pct,
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
        print("  Failure policy : STRICT — halts on first failure, no auto-retry")
        print("  Execution    : sequential (rate-limit safe)")
        print(f"  {'─' * 54}")
        for t in self.tasks:
            print(
                f"  Task {t.task_id:02d} │ offset={t.offset:<4} n={t.n_calls:<3} "
                f"checkpoint={t.checkpoint_key}"
            )
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
        print(f"\n  Calls requested : {s['calls_requested']}")
        print(f"  Calls analyzed  : {s['calls_analyzed']}")
        print(f"  Calls failed    : {s['calls_failed']}")
        print(
            f"  COMPLETE        : {'✓ YES' if s['calls_complete'] else '✗ NO — see failed_call_ids in report'}"
        )
        if s["data_quality_pass_rate_pct_by_batch"]:
            avg_dq = round(
                sum(s["data_quality_pass_rate_pct_by_batch"])
                / len(s["data_quality_pass_rate_pct_by_batch"]),
                1,
            )
            print(
                f"  Data quality pass rate (avg across batches) : {avg_dq}%  "
                f"{s['data_quality_pass_rate_pct_by_batch']}"
            )

        if h:
            print("\n  Agent health:")
            for agent, stats in h.items():
                print(
                    f"    {agent:<25} success={stats['success_rate_pct']}%  "
                    f"avg={stats['avg_elapsed_s']}s/call"
                )

        if report["failed_task_ids"]:
            print(f"\n  Failed task IDs: {report['failed_task_ids']}")
            print(
                "  Halted for human review — see the sentinel printed above. "
                "Re-run with --acknowledge-halt once reviewed; completed batches' "
                "checkpoints are preserved."
            )

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
