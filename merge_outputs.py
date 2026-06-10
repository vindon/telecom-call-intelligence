"""
merge_outputs.py
----------------
Merges all batch full_results_*.json files into a single combined dataset,
re-runs aggregate_metrics(), and updates summary.json for the dashboard.

Deduplication: if the same call_id appears in multiple batch files
(e.g. from a partial re-run), the most recently produced result wins.

Outputs
-------
  outputs/full_results_combined_{ts}.json   — merged per-call records
  outputs/summary.json                      — updated dashboard metrics
  outputs/merge_manifest_{ts}.json          — audit trail for this merge

Usage
-----
  python merge_outputs.py                   # auto-discover all batch files
  python merge_outputs.py --dry-run         # show what would be merged
  python merge_outputs.py --pattern "full_results_2026*.json"
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from pipeline.config import OUTPUT_DIR

# ── Discovery ─────────────────────────────────────────────────────────

def discover_batch_files(pattern: str = "full_results_[0-9]*.json") -> list[Path]:
    """
    Find all per-batch full_results JSON files, excluding the combined output.
    Sorted by filename (which encodes timestamp) so later files win on dedup.
    """
    matches = sorted(OUTPUT_DIR.glob(pattern))
    # Exclude combined files produced by previous merges
    return [p for p in matches if "combined" not in p.name]


# ── Merge ─────────────────────────────────────────────────────────────

def merge_results(files: list[Path]) -> tuple[list[dict], dict]:
    """
    Load, deduplicate, and merge results from a list of batch files.

    Returns:
        (merged_results, provenance)
        provenance maps file path → number of unique records contributed.
    """
    seen:      dict[str, dict] = {}   # call_id → result (last write wins)
    provenance: dict[str, int] = {}

    for path in files:
        with open(path, encoding="utf-8") as fh:
            batch = json.load(fh)

        new_ids = 0
        for record in batch:
            call_id = str(record.get("call_id", ""))
            if call_id and call_id not in seen:
                new_ids += 1
            seen[call_id] = record   # last file wins on duplicate

        provenance[str(path)] = new_ids
        print(f"  Loaded {len(batch):>4} records from {path.name}  "
              f"(+{new_ids} new unique)")

    merged = list(seen.values())
    return merged, provenance


# ── Main ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Telecom Call Intelligence — batch output merger"
    )
    parser.add_argument(
        "--pattern", type=str, default="full_results_[0-9]*.json",
        help="Glob pattern for batch files inside outputs/ (default: full_results_[0-9]*.json)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show which files would be merged without writing any output.",
    )
    args = parser.parse_args()

    print("\n" + "═" * 60)
    print("  MERGE — Combining batch outputs")
    print("═" * 60)

    files = discover_batch_files(args.pattern)

    if not files:
        print(f"\n  ✗ No batch files found matching: outputs/{args.pattern}")
        print("    Run run_pipeline.py or run_batches.py first.")
        return

    print(f"\n  Found {len(files)} batch file(s):\n")
    for f in files:
        print(f"    {f.name}")

    if args.dry_run:
        print("\n  --dry-run: no files written.")
        return

    print()
    merged, provenance = merge_results(files)

    if not merged:
        print("\n  ✗ No records found in batch files.")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── Re-run aggregation on combined dataset ────────────────────────
    print(f"\n  Aggregating {len(merged)} unique records …")
    # Load dotenv for any imports that need it
    from dotenv import load_dotenv

    from pipeline.aggregator import aggregate_metrics
    from pipeline.token_tracker import token_summary
    load_dotenv()

    metrics      = aggregate_metrics(merged)
    usage_summary = token_summary(merged)
    metrics["token_usage"] = usage_summary

    kpis = metrics["kpis"]
    print(f"  ✓ Total calls    : {kpis['total_calls_analyzed']}")
    print(f"  ✓ FCR rate       : {kpis['fcr_rate_pct']}%")
    print(f"  ✓ Avg AHT        : {kpis['avg_handle_time_minutes']} min")
    print(f"  ✓ Agentic AI oppty: {kpis['agentic_ai_resolvable_pct']}%")
    print(f"  ✓ Savings oppty  : ${metrics['cost_levers']['total_savings_opportunity_usd']:,.0f}/mo")
    if usage_summary:
        print(f"  ✓ Total tokens   : {usage_summary.get('total_tokens', 0):,}")
        print(f"  ✓ Inference cost : ${usage_summary.get('total_cost_usd', 0):.4f} USD")

    # ── Write outputs ─────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Combined per-call records
    combined_path = OUTPUT_DIR / f"full_results_combined_{ts}.json"
    with open(combined_path, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2)

    # Updated summary.json (overwrite — dashboard always reads this file)
    summary_path = OUTPUT_DIR / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)

    # Merge manifest for audit
    manifest = {
        "merge_timestamp":  ts,
        "source_files":     [str(f) for f in files],
        "total_records":    len(merged),
        "provenance":       provenance,
        "duplicates_removed": sum(
            len(json.load(open(f, encoding="utf-8"))) for f in files
        ) - len(merged),
        "output_files": {
            "combined_json":  str(combined_path),
            "summary_json":   str(summary_path),
        },
    }
    manifest_path = OUTPUT_DIR / f"merge_manifest_{ts}.json"
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    print(f"\n  ✓ Combined JSON  : {combined_path}")
    print(f"  ✓ Summary JSON   : {summary_path}  ← dashboard updated")
    print(f"  ✓ Merge manifest : {manifest_path}")
    print("\n  Dashboard: streamlit run dashboard/app.py\n")


if __name__ == "__main__":
    main()
