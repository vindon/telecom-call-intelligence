"""
run_batches.py
--------------
Entry point for multi-batch orchestration of the Telecom Call Intelligence pipeline.

Delegates all batch scheduling, health monitoring, and the strict failure
policy to pipeline.orchestrator.Orchestrator: the first batch failure halts
the entire run and requires explicit human review before any further batch
runs are allowed (see --acknowledge-halt). After all batches complete,
optionally merges outputs and runs a QA audit across the combined dataset.

Default config  : 5 batches × 20 calls = 100 total calls

Usage
-----
  python run_batches.py                        # 5×20 = 100 calls, seed=42
  python run_batches.py --batches 10 --n 10   # 10×10 = 100 calls
  python run_batches.py --batches 3 --n 5     # 3×5  = 15 calls (quick test)
  python run_batches.py --seed 99             # Reproducible alternate sample
  python run_batches.py --delay 2.5           # Slower API pacing
  python run_batches.py --skip-merge          # Batches only, no post-processing
  python run_batches.py --start-offset 200    # Fresh sample, skips offsets already used
  python run_batches.py --acknowledge-halt    # Clear a prior halt and proceed (after review)
"""

import argparse
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from pipeline.config import (  # noqa: E402
    DEFAULT_BATCH_SIZE,
    DEFAULT_DELAY_S,
    DEFAULT_RATE_LIMIT_RPM,
    DEFAULT_SEED,
)
from pipeline.orchestrator import Orchestrator, clear_halt_sentinel  # noqa: E402


def _run_subprocess(cmd: list[str], label: str) -> bool:
    """Run a post-processing subprocess, stream output, return True on success."""
    print(f"\n{'─' * 60}")
    print(f"  RUNNING: {label}")
    print(f"  CMD    : {' '.join(cmd)}")
    print('─' * 60)
    result = subprocess.run(cmd, check=False)
    if result.returncode == 0:
        print(f"\n  ✓ {label} — completed (exit 0)")
        return True
    print(f"\n  ✗ {label} — FAILED (exit {result.returncode})")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Telecom Call Intelligence — multi-batch orchestrator"
    )
    parser.add_argument(
        "--batches", type=int, default=5,
        help="Number of sequential batches to run (default: 5)",
    )
    parser.add_argument(
        "--n", type=int, default=DEFAULT_BATCH_SIZE,
        help="Calls per batch (default: 20). Total calls = batches × n.",
    )
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED,
        help="Random seed for reproducible transcript sampling (default: 42).",
    )
    parser.add_argument(
        "--start-offset", type=int, default=0,
        help="Offset of the first batch (default: 0). Batches always start at 0 "
             "otherwise, so re-running with the same seed reprocesses the same "
             "conversations — pass a value beyond any previous run's "
             "offset+n_calls to guarantee a fresh, non-overlapping sample.",
    )
    parser.add_argument(
        "--delay", type=float, default=DEFAULT_DELAY_S,
        help="Seconds between LLM API calls within each batch (default: 2.0).",
    )
    parser.add_argument(
        "--acknowledge-halt", action="store_true",
        help="Clear a prior run's halt-for-human-review sentinel and proceed. "
             "Required after any batch failure — review outputs/pipeline.log first.",
    )
    parser.add_argument(
        "--rpm", type=int, default=DEFAULT_RATE_LIMIT_RPM,
        help="Rate limit in requests per minute — used for duration estimates (default: 15).",
    )
    parser.add_argument(
        "--skip-merge", action="store_true",
        help="Skip merge_outputs.py and qa_audit.py after all batches complete.",
    )
    args = parser.parse_args()

    if args.acknowledge_halt:
        if clear_halt_sentinel():
            print("  ✓ Prior halt acknowledged and cleared — proceeding.\n")
        else:
            print("  (No halt sentinel present — nothing to acknowledge.)\n")

    total_calls = args.batches * args.n

    orch = Orchestrator(
        total_calls    = total_calls,
        batch_size     = args.n,
        seed           = args.seed,
        delay          = args.delay,
        rate_limit_rpm = args.rpm,
        start_offset   = args.start_offset,
    )

    report = orch.run()

    if report.get("halted_pending_review"):
        sys.exit(1)

    # Abort post-processing if nothing succeeded
    if report["execution_summary"]["tasks_done"] == 0:
        print("\n  ✗ No batches succeeded — skipping merge and QA audit.")
        sys.exit(1)

    # ── Post-processing ───────────────────────────────────────────────
    if args.skip_merge:
        print("\n  --skip-merge set: skipping merge and QA audit.")
        print("  Run manually:\n"
              "    python merge_outputs.py\n"
              "    python qa_audit.py")
        return

    print(f"\n{'═' * 60}")
    print("  POST-PROCESSING")
    print(f"{'═' * 60}")

    merge_ok = _run_subprocess(
        [sys.executable, "merge_outputs.py"],
        "Merge batch outputs → combined dataset",
    )

    if merge_ok:
        _run_subprocess(
            [sys.executable, "qa_audit.py"],
            "QA audit — score combined results",
        )
    else:
        print("\n  ⚠ Merge failed. QA audit skipped.")
        print("    Retry: python merge_outputs.py && python qa_audit.py")

    print(f"\n{'█' * 60}")
    print("  PIPELINE ORCHESTRATION COMPLETE")
    print(f"{'█' * 60}")
    print("  Dashboard  : streamlit run dashboard/app.py")
    print(f"  Outputs    : {Path('outputs').resolve()}")
    print(f"{'█' * 60}\n")


if __name__ == "__main__":
    main()
