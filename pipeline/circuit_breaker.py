"""
pipeline/circuit_breaker.py  —  Shared Provider Circuit Breaker
-----------------------------------------------------------------------
analyzer.py's Gemini-quota breaker and insights_agent.py's NVIDIA-
availability breaker were two independent reimplementations of the same
shape: a module-level bool, tripped once a provider is observed to be
genuinely unavailable (not on a single transient failure), and persisted
to a sentinel file so the state survives Orchestrator's per-batch
subprocess boundary — each subprocess otherwise resets the flag and
re-pays the full timeout discovering what a prior subprocess already
learned. Both call sites now share one implementation instead of two
copies of the same logic with two copies of the same bugs.

Orchestrator clears the sentinel at the start of a new top-level run —
see orchestrator.py's GEMINI_QUOTA_SENTINEL/NVIDIA_UNAVAILABLE_SENTINEL
usage, both sourced from pipeline.config so there is exactly one path
literal per breaker, not three.
"""

from __future__ import annotations

from pathlib import Path


class CircuitBreaker:
    """
    Once tripped, stays tripped for the rest of this run — including
    across the per-batch subprocess boundary, via the sentinel file.
    """

    def __init__(self, sentinel_path: Path):
        self.sentinel_path = sentinel_path
        self.tripped = sentinel_path.exists()

    def trip(self) -> None:
        self.tripped = True
        self.sentinel_path.parent.mkdir(parents=True, exist_ok=True)
        self.sentinel_path.touch()

    def reset(self) -> None:
        self.tripped = False
        self.sentinel_path.unlink(missing_ok=True)
