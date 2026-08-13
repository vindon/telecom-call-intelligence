"""
Tests for pipeline/circuit_breaker.py — the shared provider-unavailability
breaker used by analyzer.py (Gemini quota) and insights_agent.py (NVIDIA
timeouts). All filesystem I/O redirected to tmp_path.
"""

from pipeline.circuit_breaker import CircuitBreaker


class TestCircuitBreaker:
    def test_starts_untripped_when_no_sentinel(self, tmp_path):
        breaker = CircuitBreaker(tmp_path / ".sentinel")
        assert breaker.tripped is False

    def test_starts_tripped_when_sentinel_already_exists(self, tmp_path):
        sentinel = tmp_path / ".sentinel"
        sentinel.touch()
        breaker = CircuitBreaker(sentinel)
        assert breaker.tripped is True

    def test_trip_sets_flag_and_writes_sentinel(self, tmp_path):
        sentinel = tmp_path / ".sentinel"
        breaker = CircuitBreaker(sentinel)
        breaker.trip()
        assert breaker.tripped is True
        assert sentinel.exists()

    def test_trip_creates_parent_dir_if_missing(self, tmp_path):
        sentinel = tmp_path / "nested" / ".sentinel"
        breaker = CircuitBreaker(sentinel)
        breaker.trip()
        assert sentinel.exists()

    def test_reset_clears_flag_and_sentinel(self, tmp_path):
        sentinel = tmp_path / ".sentinel"
        breaker = CircuitBreaker(sentinel)
        breaker.trip()
        breaker.reset()
        assert breaker.tripped is False
        assert not sentinel.exists()

    def test_reset_is_safe_when_never_tripped(self, tmp_path):
        breaker = CircuitBreaker(tmp_path / ".sentinel")
        breaker.reset()  # must not raise
        assert breaker.tripped is False
