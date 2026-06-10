"""
Tests for pipeline/orchestrator.py — BatchTask, WorkPlanner, AgentHealthMonitor.
Orchestrator._run_task() (which spawns subprocesses) is covered by integration tests only.
"""


from pipeline.orchestrator import AgentHealthMonitor, BatchTask, WorkPlanner

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

    def test_can_retry_when_failed_and_under_limit(self):
        task = self._task(status="failed", attempts=1, max_retries=2)
        assert task.can_retry is True

    def test_can_retry_when_zero_attempts(self):
        task = self._task(status="failed", attempts=0, max_retries=2)
        assert task.can_retry is True

    def test_cannot_retry_at_max_retries(self):
        task = self._task(status="failed", attempts=2, max_retries=2)
        assert task.can_retry is False

    def test_cannot_retry_when_done(self):
        task = self._task(status="done", attempts=0, max_retries=2)
        assert task.can_retry is False

    def test_cannot_retry_when_pending(self):
        task = self._task(status="pending", attempts=0, max_retries=2)
        assert task.can_retry is False

    def test_default_status_is_pending(self):
        task = self._task()
        assert task.status == "pending"

    def test_default_attempts_is_zero(self):
        task = self._task()
        assert task.attempts == 0


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

    def test_plan_max_retries_propagated(self):
        tasks = WorkPlanner.plan(total_calls=40, batch_size=20, max_retries=5)
        assert all(t.max_retries == 5 for t in tasks)

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
