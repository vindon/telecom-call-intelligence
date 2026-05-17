"""
run_batches.py
--------------
Orchestrates N sequential pipeline batches, then merges and QA-audits the results.

Each batch runs as a subprocess so a crash in one batch does not affect others.
After all batches complete, merge_outputs.py and qa_audit.py are invoked
automatically.

Default config  : 5 batches × 20 calls = 100 total calls

Usage
-----
  python run_batches.py                        # 5×20, seed=42
  python run_batches.py --batches 10 --n 10    # 10×10 = 100 calls
  python run_batches.py --batches 3 --n 5      # 3×5 = 15 calls (quick test)
  python run_batches.py --seed 99              # Reproducible alternate sample
  python run_batches.py --delay 2.5            # Slower Groq pacing
  python run_batches.py --skip-merge           # Batches only, no post-processing
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Helpers ───────────────────────────────────────────────────────────

def _hr(char: str = "─", width: int = 60) -> str:
    return char * width


def _run_subprocess(cmd: list[str], label: str) -> bool:
    """
    Run a subprocess, stream output, return True on success.
    """
    print(f"\n{_hr('─')}")
    print(f"  RUNNING: {label}")
    print(f"  CMD    : {' '.join(cmd)}")
    print(_hr("─"))

    result = subprocess.run(cmd, check=False)

    if result.returncode == 0:
        print(f"\n  ✓ {label} — completed (exit 0)")
        return True
    else:
        print(f"\n  ✗ {label} — FAILED (exit {result.returncode})")
        return False


# ── Main ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Telecom Call Intelligence — multi-batch orchestrator"
    )
    parser.add_argument(
        "--batches", type=int, default=5,
        help="Number of sequential batches to run (default: 5)",
    )
    parser.add_argument(
        "--n",       type=int, default=20,
        help="Calls per batch (default: 20). Total calls = batches × n.",
    )
    parser.add_argument(
        "--seed",    type=int, default=42,
        help="Base random seed. Each batch uses the same seed for reproducibility (default: 42).",
    )
    parser.add_argument(
        "--delay",   type=float, default=2.0,
        help="Seconds between Groq API calls within each batch (default: 2.0).",
    )
    parser.add_argument(
        "--skip-merge", action="store_true",
        help="Skip merge_outputs.py and qa_audit.py after all batches complete.",
    )
    args = parser.parse_args()

    total_calls = args.batches * args.n
    started_at  = datetime.now()

    print("\n" + "█" * 60)
    print("  TELECOM CALL INTELLIGENCE — Batch Orchestrator")
    print("█" * 60)
    print(f"  Batches      : {args.batches}")
    print(f"  Calls/batch  : {args.n}")
    print(f"  Total calls  : {total_calls}")
    print(f"  Seed         : {args.seed}")
    print(f"  API delay    : {args.delay}s/call")
    print(f"  Est. runtime : ~{total_calls * (args.delay + 4) / 60:.0f} min")
    print("█" * 60)

    succeeded: list[int] = []
    failed:    list[int] = []

    for batch_num in range(1, args.batches + 1):
        offset = (batch_num - 1) * args.n

        print(f"\n{'═' * 60}")
        print(f"  BATCH {batch_num}/{args.batches}  │  offset={offset}, n={args.n}, seed={args.seed}")
        print(f"{'═' * 60}")

        cmd = [
            sys.executable, "run_pipeline.py",
            "--n",      str(args.n),
            "--seed",   str(args.seed),
            "--offset", str(offset),
            "--delay",  str(args.delay),
        ]

        ok = _run_subprocess(cmd, f"Batch {batch_num}/{args.batches}")
        if ok:
            succeeded.append(batch_num)
        else:
            failed.append(batch_num)
            print(f"\n  ⚠ Batch {batch_num} failed. Check outputs/pipeline.log for details.")
            print(f"    The checkpoint file (if any) is preserved for resume.")

        # Brief pause between batches to let Groq rate limits reset
        if batch_num < args.batches:
            pause = 5
            print(f"\n  Pausing {pause}s before next batch …")
            time.sleep(pause)

    # ── Summary ───────────────────────────────────────────────────────
    elapsed = (datetime.now() - started_at).total_seconds()

    print(f"\n{'█' * 60}")
    print(f"  ALL BATCHES DONE")
    print(f"{'█' * 60}")
    print(f"  Succeeded : {len(succeeded)}/{args.batches}  {succeeded}")
    print(f"  Failed    : {len(failed)}/{args.batches}  {failed}")
    print(f"  Elapsed   : {elapsed / 60:.1f} min")

    if not succeeded:
        print("\n  ✗ No batches succeeded. Nothing to merge.")
        sys.exit(1)

    # ── Post-processing ───────────────────────────────────────────────
    if args.skip_merge:
        print("\n  --skip-merge set: skipping merge and QA audit.")
        print(f"  Run manually:\n"
              f"    python merge_outputs.py\n"
              f"    python qa_audit.py")
        return

    print(f"\n{'═' * 60}")
    print(f"  POST-PROCESSING")
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
    print(f"  PIPELINE ORCHESTRATION COMPLETE")
    print(f"{'█' * 60}")
    print(f"  Dashboard  : streamlit run dashboard/app.py")
    print(f"  Outputs    : {Path('outputs').resolve()}")
    print(f"{'█' * 60}\n")


if __name__ == "__main__":
    main()
