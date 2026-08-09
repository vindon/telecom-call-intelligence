"""
Tests for pipeline/orchestrator.py — BatchTask, WorkPlanner, AgentHealthMonitor,
and the strict human-intervention failure policy (halt-on-first-failure).
Orchestrator._run_task() itself (which spawns real subprocesses) is exercised
here only via monkeypatching — real subprocess spawning is integration-tested
manually (see smoke_test.py --live), not in the unit suite.
"""

import json

import pipeline.orchestrator as orchestrator_module
from pipeline.orchestrator import (
    AgentHealthMonitor,
    BatchTask,
    Orchestrator,
    WorkPlanner,
    clear_halt_sentinel,
)

# ── BatchTask ─────────────────────────────────────────────────────────

class TestBatchTask:
    def _task(self, **overrides) -> BatchTask:
        defaults = dict(task_id=1, offset=0, n_calls=20, seed=42, delay=2.0)
        return BatchTask(**{**defaults, **overrides})

    def test_checkpoint_key_format(self):
        task = self._task(offset=20, n_calls=20, seed=42)
        assert task.checkpoint_key == "offset20_n20_seed42"

    def test_checkpoint_key_zero_offset(self):
        task = self._task(offset=0, n_calls=20, seed=42)
        assert task.checkpoint_key == "offset0_n20_seed42"

    def test_default_status_is_pending(self):
        task = self._task()
        assert task.status == "pending"


# ── WorkPlanner ───────────────────────────────────────────────────────

class TestWorkPlanner:
    def test_plan_exact_multiple(self):
        tasks = WorkPlanner.plan(total_calls=40, batch_size=20)
        assert len(tasks) == 2
        assert all(t.n_calls == 20 for t in tasks)

    def test_plan_non_overlapping_offsets(self):
        tasks = WorkPlanner.plan(total_calls=60, batch_size=20)
        offsets = [t.offset for t in tasks]
        assert offsets == [0, 20, 40]

    def test_plan_ceiling_division_last_batch(self):
        tasks = WorkPlanner.plan(total_calls=50, batch_size=20)
        assert len(tasks) == 3
        assert tasks[0].n_calls == 20
        assert tasks[1].n_calls == 20
        assert tasks[2].n_calls == 10  # 50 - 40 remainder

    def test_plan_single_batch_smaller_than_size(self):
        tasks = WorkPlanner.plan(total_calls=5, batch_size=20)
        assert len(tasks) == 1
        assert tasks[0].n_calls == 5
        assert tasks[0].offset == 0

    def test_plan_task_ids_are_sequential(self):
        tasks = WorkPlanner.plan(total_calls=60, batch_size=20)
        ids = [t.task_id for t in tasks]
        assert ids == [1, 2, 3]

    def test_plan_seed_propagated(self):
        tasks = WorkPlanner.plan(total_calls=40, batch_size=20, seed=99)
        assert all(t.seed == 99 for t in tasks)

    def test_plan_delay_propagated(self):
        tasks = WorkPlanner.plan(total_calls=40, batch_size=20, delay=3.5)
        assert all(t.delay == 3.5 for t in tasks)

    def test_plan_100_calls_5_batches(self):
        tasks = WorkPlanner.plan(total_calls=100, batch_size=20)
        assert len(tasks) == 5
        assert sum(t.n_calls for t in tasks) == 100

    def test_estimate_duration_positive(self):
        tasks = WorkPlanner.plan(total_calls=20, batch_size=20)
        est = WorkPlanner.estimate_duration(tasks, avg_call_s=10.0)
        assert est > 0

    def test_estimate_duration_proportional(self):
        tasks_20  = WorkPlanner.plan(total_calls=20,  batch_size=20)
        tasks_100 = WorkPlanner.plan(total_calls=100, batch_size=20)
        est_20  = WorkPlanner.estimate_duration(tasks_20,  avg_call_s=10.0)
        est_100 = WorkPlanner.estimate_duration(tasks_100, avg_call_s=10.0)
        assert est_100 > est_20


# ── Strict human-intervention failure policy ────────────────────────────
# The first task failure must halt the entire run immediately — no
# auto-retry, no proceeding to the next batch — and write a sentinel that
# blocks every subsequent orchestration run until a human clears it. This
# replaced an auto-retry loop that, in production on 2026-08-09, silently
# retried a hung batch twice before a human noticed the wasted spend.

class TestStrictFailurePolicy:
    def _patch_sentinels(self, monkeypatch, tmp_path):
        for name in ("_HALT_SENTINEL", "_QUOTA_SENTINEL", "_NVIDIA_SENTINEL"):
            monkeypatch.setattr(orchestrator_module, name, tmp_path / f"{name}.json")

    def test_halts_on_first_failure_no_further_tasks_run(self, monkeypatch, tmp_path):
        self._patch_sentinels(monkeypatch, tmp_path)
        orch = Orchestrator(total_calls=60, batch_size=20, rate_limit_rpm=999)
        ran: list[int] = []

        def fake_run_task(task):
            ran.append(task.task_id)
            task.status    = "failed"
            task.error_msg = "simulated failure"

        monkeypatch.setattr(orch, "_run_task", fake_run_task)
        report = orch.run()

        assert ran == [1]  # tasks 2 and 3 never started
        assert report["execution_summary"]["tasks_done"] == 0
        assert report["execution_summary"]["tasks_failed"] == 1
        assert orchestrator_module._HALT_SENTINEL.exists()

    def test_halt_sentinel_records_failure_details(self, monkeypatch, tmp_path):
        self._patch_sentinels(monkeypatch, tmp_path)
        orch = Orchestrator(total_calls=20, batch_size=20, rate_limit_rpm=999)

        def fake_run_task(task):
            task.status    = "failed"
            task.error_msg = "timeout (600s)"
            task.exit_code = -1

        monkeypatch.setattr(orch, "_run_task", fake_run_task)
        orch.run()

        halt = json.loads(orchestrator_module._HALT_SENTINEL.read_text())
        assert halt["task_id"] == 1
        assert halt["offset"] == 0
        assert halt["error"] == "timeout (600s)"
        assert "human-intervention" in halt["reason"]

    def test_halt_sentinel_blocks_next_run(self, monkeypatch, tmp_path):
        self._patch_sentinels(monkeypatch, tmp_path)
        orchestrator_module._HALT_SENTINEL.write_text(json.dumps({
            "halted_at": "2026-01-01T00:00:00", "task_id": 1, "offset": 0, "n_calls": 20,
            "error": "timeout", "reason": "test", "tasks_completed_before_halt": [],
        }))
        orch = Orchestrator(total_calls=20, batch_size=20, rate_limit_rpm=999)
        called: list[int] = []
        monkeypatch.setattr(orch, "_run_task", lambda task: called.append(task.task_id))

        report = orch.run()

        assert called == []  # run() must refuse to start any task while halted
        assert report["halted_pending_review"] is True

    def test_successful_run_does_not_write_halt_sentinel(self, monkeypatch, tmp_path):
        self._patch_sentinels(monkeypatch, tmp_path)
        orch = Orchestrator(total_calls=20, batch_size=20, rate_limit_rpm=999)
        monkeypatch.setattr(orch, "_run_task", lambda task: setattr(task, "status", "done"))
        orch.run()
        assert not orchestrator_module._HALT_SENTINEL.exists()

    def test_clear_halt_sentinel_removes_file(self, monkeypatch, tmp_path):
        self._patch_sentinels(monkeypatch, tmp_path)
        orchestrator_module._HALT_SENTINEL.write_text("{}")
        assert clear_halt_sentinel() is True
        assert not orchestrator_module._HALT_SENTINEL.exists()

    def test_clear_halt_sentinel_noop_when_absent(self, monkeypatch, tmp_path):
        self._patch_sentinels(monkeypatch, tmp_path)
        assert clear_halt_sentinel() is False

    def test_timeout_records_health_failure(self, monkeypatch, tmp_path):
        """A hung batch (subprocess.TimeoutExpired) must count against agent
        health the same way an exit-code failure does — this was silently
        skipped before (only the exit!=0 branch called health.record())."""
        self._patch_sentinels(monkeypatch, tmp_path)
        orch = Orchestrator(total_calls=20, batch_size=20, rate_limit_rpm=999)

        def fake_subprocess_run(*args, **kwargs):
            import subprocess
            raise subprocess.TimeoutExpired(cmd="run_pipeline.py", timeout=600)

        monkeypatch.setattr(orchestrator_module.subprocess, "run", fake_subprocess_run)
        orch._run_task(orch.tasks[0])

        assert orch.tasks[0].status == "failed"
        assert orch.tasks[0].error_msg == "timeout (600s)"
        health = orch.health.summary()
        assert health["ExtractionAgent"]["success_rate_pct"] == 0.0
        assert health["ExtractionAgent"]["calls"] == 1

    def test_unexpected_exception_records_health_failure(self, monkeypatch, tmp_path):
        self._patch_sentinels(monkeypatch, tmp_path)
        orch = Orchestrator(total_calls=20, batch_size=20, rate_limit_rpm=999)

        def fake_subprocess_run(*args, **kwargs):
            raise OSError("simulated crash")

        monkeypatch.setattr(orchestrator_module.subprocess, "run", fake_subprocess_run)
        orch._run_task(orch.tasks[0])

        assert orch.tasks[0].status == "failed"
        health = orch.health.summary()
        assert health["ExtractionAgent"]["success_rate_pct"] == 0.0
        assert health["ExtractionAgent"]["calls"] == 1


# ── AgentHealthMonitor ────────────────────────────────────────────────

class TestAgentHealthMonitor:
    def test_empty_monitor_is_empty(self):
        monitor = AgentHealthMonitor()
        assert monitor.summary() == {}

    def test_record_single_success(self):
        monitor = AgentHealthMonitor()
        monitor.record("ExtractionAgent", success=True, elapsed_s=5.0)
        summary = monitor.summary()
        assert "ExtractionAgent" in summary
        assert summary["ExtractionAgent"]["success_rate_pct"] == 100.0
        assert summary["ExtractionAgent"]["calls"] == 1

    def test_record_single_failure(self):
        monitor = AgentHealthMonitor()
        monitor.record("ExtractionAgent", success=False, elapsed_s=1.0)
        assert monitor.summary()["ExtractionAgent"]["success_rate_pct"] == 0.0

    def test_mixed_success_rate_50_pct(self):
        monitor = AgentHealthMonitor()
        monitor.record("ExtractionAgent", success=True,  elapsed_s=5.0)
        monitor.record("ExtractionAgent", success=False, elapsed_s=1.0)
        assert monitor.summary()["ExtractionAgent"]["success_rate_pct"] == 50.0

    def test_avg_elapsed_computed(self):
        monitor = AgentHealthMonitor()
        monitor.record("ExtractionAgent", success=True, elapsed_s=4.0)
        monitor.record("ExtractionAgent", success=True, elapsed_s=6.0)
        assert monitor.summary()["ExtractionAgent"]["avg_elapsed_s"] == 5.0

    def test_multiple_agents_tracked_independently(self):
        monitor = AgentHealthMonitor()
        monitor.record("ExtractionAgent", success=True,  elapsed_s=5.0)
        monitor.record("InsightsAgent",   success=False, elapsed_s=1.0)
        summary = monitor.summary()
        assert summary["ExtractionAgent"]["success_rate_pct"] == 100.0
        assert summary["InsightsAgent"]["success_rate_pct"]   == 0.0

    def test_is_healthy_no_data(self):
        monitor = AgentHealthMonitor()
        assert monitor.is_healthy("UnknownAgent") is True  # no data → assume healthy

    def test_is_healthy_above_threshold(self):
        monitor = AgentHealthMonitor()
        monitor.record("ExtractionAgent", success=True, elapsed_s=5.0)
        assert monitor.is_healthy("ExtractionAgent", min_success_rate=0.5) is True

    def test_is_healthy_below_threshold(self):
        monitor = AgentHealthMonitor()
        monitor.record("ExtractionAgent", success=False, elapsed_s=1.0)
        assert monitor.is_healthy("ExtractionAgent", min_success_rate=0.5) is False

    def test_is_healthy_exactly_at_threshold(self):
        monitor = AgentHealthMonitor()
        monitor.record("ExtractionAgent", success=True,  elapsed_s=1.0)
        monitor.record("ExtractionAgent", success=False, elapsed_s=1.0)
        # 50% success, threshold 50% → healthy
        assert monitor.is_healthy("ExtractionAgent", min_success_rate=0.5) is True
