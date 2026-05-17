"""
run_batches.py
--------------
Entry point for multi-batch orchestration of the Telecom Call Intelligence pipeline.

Delegates all batch scheduling, health monitoring, and retry logic to
pipeline.orchestrator.Orchestrator. After all batches complete, optionally
merges outputs and runs a QA audit across the combined dataset.

Default config  : 5 batches × 20 calls = 100 total calls

Usage
-----
  python run_batches.py                        # 5×20 = 100 calls, seed=42
  python run_batches.py --batches 10 --n 10   # 10×10 = 100 calls
  python run_batches.py --batches 3 --n 5     # 3×5  = 15 calls (quick test)
  python run_batches.py --seed 99             # Reproducible alternate sample
  python run_batches.py --delay 2.5           # Slower API pacing
  python run_batches.py --skip-merge          # Batches only, no post-processing
  python run_batches.py --retries 3           # Up to 3 retry attempts per batch
"""

import argparse
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from pipeline.orchestrator import Orchestrator  # noqa: E402


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
        "--n", type=int, default=20,
        help="Calls per batch (default: 20). Total calls = batches × n.",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducible transcript sampling (default: 42).",
    )
    parser.add_argument(
        "--delay", type=float, default=2.0,
        help="Seconds between Gemini API calls within each batch (default: 2.0).",
    )
    parser.add_argument(
        "--retries", type=int, default=2,
        help="Max retry attempts per failed batch (default: 2).",
    )
    parser.add_argument(
        "--rpm", type=int, default=15,
        help="Rate limit in requests per minute — used for duration estimates (default: 15).",
    )
    parser.add_argument(
        "--skip-merge", action="store_true",
        help="Skip merge_outputs.py and qa_audit.py after all batches complete.",
    )
    args = parser.parse_args()

    total_calls = args.batches * args.n

    orch = Orchestrator(
        total_calls    = total_calls,
        batch_size     = args.n,
        seed           = args.seed,
        delay          = args.delay,
        rate_limit_rpm = args.rpm,
        max_retries    = args.retries,
    )

    report = orch.run()

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
