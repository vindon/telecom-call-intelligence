"""
smoke_test.py
-------------
Run before any paid batch run (run_batches.py / make run-batches).

Catches, for free wherever possible, the two failure classes that caused
wasted spend on 2026-08-09:

  1. Live-API hangs — InsightsAgent's NVIDIA NIM call hung with no explicit
     timeout, up to the SDK default of 600s — the same order of magnitude as
     Orchestrator's own 600s per-batch subprocess timeout — so a slow
     provider discarded an already-successful extraction batch on retry.
     Validated here with ONE real call through the full pipeline (--live),
     wrapped in a hard subprocess timeout so a hang fails this smoke test in
     ~2.5 minutes instead of silently burning the real batch's budget.

  2. Non-overlapping-offset sampling bugs — hf_loader.py's old sampling
     produced 10-90% duplicate conversation IDs across batches at offsets
     spaced by n (a 10-batch run only returned 136/200 unique calls before
     the fix). Validated here for FREE — no API calls — against the exact
     offsets your planned run will use.

Usage
-----
  python smoke_test.py                                          # free checks only
  python smoke_test.py --start-offset 400 --batches 10 --n 20    # validate a specific plan
  python smoke_test.py --live                                    # + one real ~$0.02 API call
  python smoke_test.py --skip-tests                               # skip the pytest run (faster iteration)

Exit code 0 = safe to proceed with the real batch run. Non-zero = don't spend money yet.
"""

import argparse
import json
import os
import subprocess
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from pipeline.config import (  # noqa: E402
    BUDGET_USD,
    EXTRACTION_API_TIMEOUT_S,
    INSIGHTS_API_TIMEOUT_S,
    LOCAL_CSV_PATH,
    OUTPUT_DIR,
)

# Fixed offset for the live smoke call — deliberately far from any realistic
# production range (offsets 0-400 used so far) but comfortably within the
# ~220K-conversation dataset's real capacity even after _BUFFER_X=6 scaling,
# so it always resolves to a valid transcript regardless of what plan is
# being validated by --start-offset/--batches/--n.
_LIVE_SMOKE_OFFSET = 30_000


def _check(label: str, ok: bool, detail: str = "") -> bool:
    status = "✓ PASS" if ok else "✗ FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    return ok


# ── Free checks ──────────────────────────────────────────────────────

def check_env_vars() -> bool:
    print("\n── Environment ──")
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    ok = _check(
        "ANTHROPIC_API_KEY set", has_anthropic,
        "" if has_anthropic else "required — extraction will fail without it",
    )
    has_nvidia = bool(os.environ.get("NVIDIA_API_KEY"))
    _check(
        "NVIDIA_API_KEY set (optional)", True,
        "present" if has_nvidia else "absent — insights will use Claude fallback directly",
    )
    return ok


def check_config_sanity() -> bool:
    print("\n── Config sanity ──")
    ok = True
    ok &= _check("BUDGET_USD > 0", BUDGET_USD > 0, f"${BUDGET_USD:.2f}")
    ok &= _check(
        "EXTRACTION_API_TIMEOUT_S is set and reasonable",
        0 < EXTRACTION_API_TIMEOUT_S <= 120, f"{EXTRACTION_API_TIMEOUT_S}s",
    )
    ok &= _check(
        "INSIGHTS_API_TIMEOUT_S is set and reasonable",
        0 < INSIGHTS_API_TIMEOUT_S <= 120, f"{INSIGHTS_API_TIMEOUT_S}s",
    )
    return ok


def check_unit_tests() -> bool:
    print("\n── Unit test suite ──")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        capture_output=True, text=True, timeout=120,
    )
    ok = result.returncode == 0
    tail = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    _check("pytest tests/ -q", ok, tail)
    if not ok:
        print(result.stdout[-2000:])
    return ok


def check_offset_disjointness(start_offset: int, batches: int, n: int, seed: int) -> bool:
    """
    Free (no API calls): simulate the exact offsets the planned real run will
    use and confirm zero duplicate conversation IDs across batches — this is
    the actual regression that caused only 136/200 unique calls to be
    produced on 2026-08-09.
    """
    print(f"\n── Offset disjointness (start_offset={start_offset}, batches={batches}, n={n}, seed={seed}) ──")
    if not LOCAL_CSV_PATH.exists():
        print("  [SKIP] LOCAL_CSV_PATH not found — cannot verify without a HuggingFace network fetch")
        return True

    import pandas as pd

    from pipeline.hf_loader import _select_ids

    df = pd.read_csv(LOCAL_CSV_PATH, dtype={"conversation_id": str}, usecols=["conversation_id"])
    all_ids_ordered = sorted(df["conversation_id"].dropna().unique().tolist())

    seen: set[str] = set()
    ok = True
    for i in range(batches):
        offset = start_offset + i * n
        ids = set(_select_ids(all_ids_ordered, n, seed, offset, source="smoke_test"))
        overlap = ids & seen
        if overlap:
            ok = False
            print(f"  [✗ FAIL] offset={offset}: {len(overlap)} duplicate ID(s) vs earlier batches in this plan")
        seen |= ids

    return _check(f"{batches} batches × n={n} — zero duplicates across {len(seen)} conversations", ok)


# ── Live check (costs real money — opt-in only via --live) ────────────

def check_live_pipeline(seed: int) -> bool:
    """
    Runs ONE real call through the full pipeline (extraction, QA, aggregation,
    insights, export) — the exact path that hung on 2026-08-09. Wrapped in a
    hard subprocess timeout so a hang fails this check in minutes instead of
    silently costing the real batch's budget. Estimated cost: ~$0.01-0.02.

    Self-cleaning: backs up and restores summary.json (a single-call smoke
    test would otherwise overwrite the real tracked dashboard data — exactly
    the mistake made mid-session on 2026-08-09 debugging this same pipeline),
    and deletes every throwaway per-call artifact it creates.
    """
    print(f"\n── Live pipeline smoke call (offset={_LIVE_SMOKE_OFFSET}, ~$0.01-0.02) ──")

    summary_path = OUTPUT_DIR / "summary.json"
    summary_backup = summary_path.read_bytes() if summary_path.exists() else None
    before_files = set(OUTPUT_DIR.glob("*")) if OUTPUT_DIR.exists() else set()

    try:
        t0 = time.monotonic()
        # Hard timeout well above the fixed API-client timeouts (60s/45s) but
        # well below Orchestrator's real 600s subprocess timeout — a hang
        # here fails fast instead of reproducing the original incident.
        result = subprocess.run(
            [
                sys.executable, "run_pipeline.py",
                "--n", "1", "--offset", str(_LIVE_SMOKE_OFFSET),
                "--seed", str(seed), "--budget", "0.10",
            ],
            capture_output=True, text=True, timeout=150,
        )
        elapsed = time.monotonic() - t0
        timed_out = False
    except subprocess.TimeoutExpired:
        elapsed = 150.0
        timed_out = True
        result = None
    finally:
        # Never let a smoke test clobber the real tracked dashboard data.
        if summary_backup is not None:
            summary_path.write_bytes(summary_backup)
        elif summary_path.exists():
            summary_path.unlink()

    if timed_out:
        _check(
            "Live pipeline completes within 150s", False,
            "TIMED OUT — this is the exact failure mode from 2026-08-09; "
            "check for a client with no explicit timeout",
        )
        return False

    ok = _check("Live pipeline exits 0", result.returncode == 0, f"{elapsed:.0f}s")
    if not ok:
        print(result.stdout[-1500:])
        print(result.stderr[-1500:])

    new_files = set(OUTPUT_DIR.glob("*")) - before_files
    manifest_files = sorted(
        (p for p in new_files if p.name.startswith("run_manifest_")),
        key=lambda p: p.stat().st_mtime,
    )
    manifest = json.loads(manifest_files[-1].read_text()) if manifest_files else None

    if manifest:
        ok &= _check(
            "n_analyzed == n_requested",
            manifest.get("n_analyzed") == manifest.get("n_requested"),
            f"{manifest.get('n_analyzed')}/{manifest.get('n_requested')}",
        )
        ok &= _check("n_failed == 0", manifest.get("n_failed", 1) == 0)
        ok &= _check(
            "insights_source is not empty",
            bool(manifest.get("insights_source")) and manifest.get("insights_source") != "none",
            manifest.get("insights_source", "MISSING"),
        )
        tu = manifest.get("token_usage", {})
        cache_used = (tu.get("total_cache_read_tokens", 0) or 0) + (tu.get("total_cache_creation_tokens", 0) or 0)
        _check("prompt caching engaged (cache tokens > 0)", cache_used > 0, f"{cache_used} tokens")
    else:
        ok = _check("run_manifest written", False, "no manifest found — pipeline likely failed before export")

    # Clean up every throwaway artifact this call created — it has no
    # business in the real merged dataset.
    for f in new_files:
        if f.name == "summary.json":
            continue  # already restored above
        try:
            f.unlink()
        except OSError:
            pass
    print(f"  (cleaned up {len(new_files)} throwaway file(s) from this smoke call)")

    return ok


# ── Main ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-flight smoke test — run before any paid batch")
    parser.add_argument("--start-offset", type=int, default=0, help="Planned start_offset for the real run (default: 0)")
    parser.add_argument("--batches", type=int, default=5, help="Planned number of batches (default: 5)")
    parser.add_argument("--n", type=int, default=20, help="Planned calls per batch (default: 20)")
    parser.add_argument("--seed", type=int, default=42, help="Planned seed (default: 42)")
    parser.add_argument("--live", action="store_true", help="Also run one real ~$0.01-0.02 API call through the full pipeline")
    parser.add_argument("--skip-tests", action="store_true", help="Skip the pytest run")
    args = parser.parse_args()

    print("═" * 60)
    print("  PRE-FLIGHT SMOKE TEST")
    print("  Run this before any paid batch run.")
    print("═" * 60)

    results = [check_env_vars(), check_config_sanity()]
    if not args.skip_tests:
        results.append(check_unit_tests())
    results.append(check_offset_disjointness(args.start_offset, args.batches, args.n, args.seed))

    if args.live:
        results.append(check_live_pipeline(args.seed))
    else:
        print("\n── Live pipeline check ──")
        print("  [SKIPPED] pass --live to also validate the real API path (~$0.01-0.02)")

    print("\n" + "═" * 60)
    if all(results):
        print("  ALL CHECKS PASSED — safe to proceed with the real batch run.")
        if not args.live:
            print("  Live API path was NOT tested — strongly recommend --live before a large/expensive run.")
        print("═" * 60)
        sys.exit(0)
    else:
        print("  ✗ SOME CHECKS FAILED — do not run the paid batch yet.")
        print("═" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
