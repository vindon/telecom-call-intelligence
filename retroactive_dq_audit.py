"""
retroactive_dq_audit.py
------------------------
Retroactively applies the data-quality gate (qa_audit.check_phase_reconciliation,
check_timestamp_ground_truth, looks_truncated_heuristic) to batches that were
already processed BEFORE that gate existed — without any new LLM calls or a
new extraction batch.

Why this is possible without spending anything
------------------------------------------------
Every full_results_{ts}.json produced by ExportAgent has a matching
run_manifest_{ts}.json recording the exact (offset, seed, n_requested) used
to fetch its transcripts. hf_loader.load_telecom_transcripts() is a pure,
deterministic function of those three values — calling it again returns the
exact same transcript slice, for free, from the local CSV if present
(pipeline/config.LOCAL_CSV_PATH) or by re-streaming from HuggingFace. No LLM
is involved in re-fetching, so this recovers raw_duration_seconds (ground
truth) and transcript_text (for the truncation heuristic) at zero cost.

What can and can't be recovered
---------------------------------
  phase_reconciliation     — full strength: phase_*_duration_seconds and
                              total_duration_seconds already exist in every
                              surviving full_results record.
  timestamp_ground_truth   — backfilled: raw_duration_seconds is recovered
                              by re-fetching the transcript slice.
  transcript_truncation    — heuristic-only: the LLM was never asked to grade
                              transcript_truncated in these older extractions
                              (that schema field postdates this batch), so
                              only the free closing-phrase heuristic
                              (qa_audit.looks_truncated_heuristic) can run.
                              This is explicitly weaker than the primary
                              LLM-graded signal and is reported as such.
  runs with no surviving
  full_results_{ts}.json   — not auditable at all; reported, not skipped.

Usage
-----
  python retroactive_dq_audit.py
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from pipeline.config import OUTPUT_DIR
from pipeline.hf_loader import load_telecom_transcripts
from qa_audit import (
    check_phase_reconciliation,
    check_timestamp_ground_truth,
    looks_truncated_heuristic,
)

_TS_RE = re.compile(r"(\d{8}_\d{6})")


def _timestamp_of(path: Path) -> str | None:
    m = _TS_RE.search(path.name)
    return m.group(1) if m else None


def _file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


# ── Discovery ─────────────────────────────────────────────────────────

def discover_runs() -> tuple[list[tuple[Path, Path]], list[Path]]:
    """
    Pair each per-batch full_results_{ts}.json with its run_manifest_{ts}.json.

    "combined" files are skipped — they are re-merges of the individual batch
    files (already paired below) and, per merge_outputs.py's own dedup, are
    not guaranteed to be a clean union (last-call_id-wins can drop records),
    so the individual batches are the authoritative per-offset source.

    Returns:
        (paired, unmatched_manifests) — unmatched_manifests are manifests
        whose full_results file has been rotated/deleted; reported as
        "no_per_call_data_available", never silently skipped.
    """
    full_results = sorted(
        p for p in OUTPUT_DIR.glob("full_results_[0-9]*.json") if "combined" not in p.name
    )
    manifests = {
        _timestamp_of(p): p for p in OUTPUT_DIR.glob("run_manifest_*.json")
    }

    paired: list[tuple[Path, Path]] = []
    matched_ts: set[str] = set()
    for fr in full_results:
        ts = _timestamp_of(fr)
        manifest = manifests.get(ts)
        if manifest:
            paired.append((fr, manifest))
            matched_ts.add(ts)

    unmatched_manifests = [p for ts, p in manifests.items() if ts not in matched_ts]
    return paired, sorted(unmatched_manifests)


# ── Per-run audit ─────────────────────────────────────────────────────

def audit_run(full_results_path: Path, manifest_path: Path) -> dict:
    with open(full_results_path, encoding="utf-8") as fh:
        records: list[dict] = json.load(fh)
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    offset = manifest.get("offset")
    seed = manifest.get("seed")
    n_requested = manifest.get("n_requested")
    can_backfill = None not in (offset, seed, n_requested)

    ground_truth: dict[str, dict] = {}
    if can_backfill:
        transcripts = load_telecom_transcripts(n=n_requested, seed=seed, offset=offset)
        ground_truth = {t["call_id"]: t for t in transcripts}

    call_results: list[dict] = []
    for r in records:
        call_id = str(r.get("call_id", "UNKNOWN"))
        phase_check = check_phase_reconciliation(r)

        src = ground_truth.get(call_id)
        if src is not None:
            enriched = {**r, "_raw_duration_seconds": src.get("raw_duration_seconds")}
            timestamp_check = check_timestamp_ground_truth(enriched)
            timestamp_check["confidence"] = "backfilled"
            heuristic_truncated = looks_truncated_heuristic(src["transcript_text"])
        else:
            timestamp_check = {"passed": True, "confidence": "unavailable"}
            heuristic_truncated = None

        call_results.append({
            "call_id": call_id,
            "phase_reconciliation": {**phase_check, "confidence": "full"},
            "timestamp_ground_truth": timestamp_check,
            "heuristic_truncation_flag": heuristic_truncated,
        })

    n = len(call_results)
    n_phase_pass = sum(1 for c in call_results if c["phase_reconciliation"]["passed"])
    ts_checked = [c for c in call_results if c["timestamp_ground_truth"]["confidence"] == "backfilled"]
    n_ts_pass = sum(1 for c in ts_checked if c["timestamp_ground_truth"]["passed"])
    n_heuristic_flagged = sum(1 for c in call_results if c["heuristic_truncation_flag"] is True)

    flagged = [
        {
            "call_id": c["call_id"],
            "phase_reconciliation_failed": not c["phase_reconciliation"]["passed"],
            "timestamp_ground_truth_failed": not c["timestamp_ground_truth"]["passed"],
            "heuristic_truncation_flag": c["heuristic_truncation_flag"],
        }
        for c in call_results
        if not c["phase_reconciliation"]["passed"]
        or not c["timestamp_ground_truth"]["passed"]
        or c["heuristic_truncation_flag"] is True
    ]

    return {
        "run_timestamp": manifest.get("run_timestamp", _timestamp_of(full_results_path)),
        "source_file": str(full_results_path),
        "n_calls": n,
        "backfill_available": can_backfill,
        "phase_reconciliation_pass_rate_pct": round(n_phase_pass / n * 100, 1) if n else None,
        "timestamp_ground_truth_pass_rate_pct": (
            round(n_ts_pass / len(ts_checked) * 100, 1) if ts_checked else None
        ),
        "heuristic_truncation_flag_rate_pct": round(n_heuristic_flagged / n * 100, 1) if n else None,
        "flagged_calls": flagged,
    }


# ── Main ──────────────────────────────────────────────────────────────

def main() -> None:
    print("\n" + "═" * 60)
    print("  RETROACTIVE DATA QUALITY AUDIT")
    print("  (existing batches — no new LLM calls, no new extraction)")
    print("═" * 60)

    paired, unmatched_manifests = discover_runs()

    if not paired:
        print("\n  ✗ No full_results_*.json + run_manifest_*.json pairs found.")
        return

    print(f"\n  Found {len(paired)} auditable run(s), "
          f"{len(unmatched_manifests)} run(s) with no surviving per-call data.\n")

    run_reports = [audit_run(fr, mf) for fr, mf in paired]

    total_calls = sum(r["n_calls"] for r in run_reports)
    total_phase_pass = sum(
        round(r["phase_reconciliation_pass_rate_pct"] / 100 * r["n_calls"]) for r in run_reports
    )
    ts_runs = [r for r in run_reports if r["timestamp_ground_truth_pass_rate_pct"] is not None]
    total_ts_checked = sum(
        r["n_calls"] for r in ts_runs
    )
    total_ts_pass = sum(
        round(r["timestamp_ground_truth_pass_rate_pct"] / 100 * r["n_calls"]) for r in ts_runs
    )
    total_heuristic_flagged = sum(
        round(r["heuristic_truncation_flag_rate_pct"] / 100 * r["n_calls"]) for r in run_reports
    )

    overall = {
        "total_calls_audited": total_calls,
        "phase_reconciliation_pass_rate_pct": (
            round(total_phase_pass / total_calls * 100, 1) if total_calls else None
        ),
        "timestamp_ground_truth_pass_rate_pct": (
            round(total_ts_pass / total_ts_checked * 100, 1) if total_ts_checked else None
        ),
        "heuristic_truncation_flag_rate_pct": (
            round(total_heuristic_flagged / total_calls * 100, 1) if total_calls else None
        ),
        "runs_audited": len(run_reports),
        "runs_with_no_per_call_data": [str(p) for p in unmatched_manifests],
    }

    print(f"  {'─' * 50}")
    print(f"  Total calls audited          : {overall['total_calls_audited']}")
    print(f"  Phase reconciliation pass    : {overall['phase_reconciliation_pass_rate_pct']}%  (full strength)")
    print(f"  Timestamp ground-truth pass  : {overall['timestamp_ground_truth_pass_rate_pct']}%  (backfilled)")
    print(f"  Heuristic truncation flagged : {overall['heuristic_truncation_flag_rate_pct']}%  (heuristic only, corroborating)")
    print(f"  Runs with NO per-call data   : {len(unmatched_manifests)}  (cannot be audited — full_results rotated)")
    if unmatched_manifests:
        for p in unmatched_manifests:
            print(f"    - {p.name}")

    print("\n  Per-run breakdown:")
    for r in run_reports:
        n_flagged = len(r["flagged_calls"])
        print(
            f"    {r['run_timestamp']}  n={r['n_calls']:>3}  "
            f"phase_pass={r['phase_reconciliation_pass_rate_pct']:>5.1f}%  "
            f"ts_pass={r['timestamp_ground_truth_pass_rate_pct']}%  "
            f"heuristic_flagged={r['heuristic_truncation_flag_rate_pct']}%  "
            f"flagged_calls={n_flagged}"
        )

    OUTPUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = OUTPUT_DIR / f"retroactive_dq_report_{ts}.json"
    report = {
        "audit_timestamp": ts,
        "overall": overall,
        "runs": run_reports,
    }
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print(f"\n  ✓ Report written: {report_path}\n")


if __name__ == "__main__":
    main()
