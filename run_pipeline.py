"""
run_pipeline.py
---------------
Entry point for the Telecom Call Intelligence multi-agent pipeline.

Architecture (6 agents):
  DataIngestionAgent  →  ExtractionAgent  →  QualityAgent
  AggregationAgent    →  InsightsAgent    →  ExportAgent

Usage
-----
  python run_pipeline.py                   # 100 calls, default seed, no offset
  python run_pipeline.py --n 3             # 3-call smoke test
  python run_pipeline.py --n 20 --offset 0    # Batch 1 (calls 0-19)
  python run_pipeline.py --n 20 --offset 20   # Batch 2 (calls 20-39)
  python run_pipeline.py --seed 99         # Different random sample
  python run_pipeline.py --delay 2.0       # Slower inter-call delay

Batching
--------
Use --offset to run non-overlapping batches. Each batch is reproducible
with the same (--offset, --n, --seed) triple. Use run_batches.py to
orchestrate multiple batches automatically.

Checkpoint / resume
-------------------
A checkpoint key is auto-generated from (offset, n, seed). If a run
is killed mid-way, restart with the same flags and already-analyzed
calls will be loaded from disk — no duplicated API calls.
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env before importing any pipeline module (they read GEMINI_API_KEY at call time)
load_dotenv()

if not os.environ.get("GEMINI_API_KEY"):
    print("ERROR: GEMINI_API_KEY not set.")
    print("  Copy .env.example to .env and add your Google AI Studio key.")
    print("  Free key at: https://aistudio.google.com")
    sys.exit(1)

from pipeline.graph import build_pipeline  # noqa: E402


def main() -> dict:
    parser = argparse.ArgumentParser(
        description="Telecom Call Intelligence — single-batch pipeline runner"
    )
    parser.add_argument(
        "--n",      type=int,   default=100,
        help="Number of calls to analyze (default: 100)",
    )
    parser.add_argument(
        "--seed",   type=int,   default=42,
        help="Random seed for HuggingFace sampling (default: 42)",
    )
    parser.add_argument(
        "--offset", type=int,   default=0,
        help="Skip first N unique conversations before sampling (default: 0). "
             "Use multiples of --n to guarantee non-overlapping batches.",
    )
    parser.add_argument(
        "--delay",  type=float, default=2.0,
        help="Seconds between Gemini API calls (default: 2.0)",
    )
    args = parser.parse_args()

    # Auto-generate a checkpoint key that encodes all sampling parameters
    checkpoint_key = f"offset{args.offset}_n{args.n}_seed{args.seed}"

    print("\n" + "█" * 60)
    print("  TELECOM CALL INTELLIGENCE — Multi-Agent Pipeline")
    print("█" * 60)
    print("  Agents     : DataIngestion → Extraction → Quality →")
    print("               Aggregation  → Insights   → Export")
    print("  Dataset    : talkmap/telecom-conversation-corpus")
    print("  Model      : gemini-2.5-flash-lite (Google AI Studio)")
    print(f"  Calls      : {args.n}")
    print(f"  Seed       : {args.seed}")
    print(f"  Offset     : {args.offset}")
    print(f"  API delay  : {args.delay}s/call")
    print(f"  Checkpoint : outputs/.checkpoint_{checkpoint_key}.jsonl")
    print("█" * 60 + "\n")

    initial_state = {
        "n_calls":               args.n,
        "seed":                  args.seed,
        "offset":                args.offset,
        "inter_call_delay":      args.delay,
        "checkpoint_key":        checkpoint_key,
        "raw_transcripts":       [],
        "validated_transcripts": [],
        "analysis_results":      [],
        "qa_report":             {},
        "qa_passed_results":     [],
        "aggregated_metrics":    {},
        "agent_insights":        {},
        "export_paths":          {},
        "validation_errors":     [],
        "failed_call_ids":       [],
        "token_usage":           {},
        "react_stats":           {},
        "approval_granted":      False,
        "decision_log":          [],
    }

    pipeline    = build_pipeline()
    final_state = pipeline.invoke(initial_state)

    usage = final_state.get("token_usage", {})

    qa   = final_state.get("qa_report", {})
    ins  = final_state.get("agent_insights", {})

    print("\n" + "█" * 60)
    print("  MULTI-AGENT PIPELINE COMPLETE")
    print("█" * 60)
    print(f"  Results saved to : {Path('outputs').resolve()}")
    print("  Dashboard        : streamlit run dashboard/app.py")
    if usage:
        print(f"  Tokens used      : {usage.get('total_tokens', 0):,}")
        print(f"  Inference cost   : ${usage.get('total_cost_usd', 0):.4f} USD")
    if qa:
        print(f"  QA verdict       : {qa.get('dataset_verdict', 'N/A')}  "
              f"(avg score: {qa.get('summary', {}).get('avg_score', 0)}/100)")
    if ins:
        print(f"  Insights source  : {ins.get('source', 'N/A')}")
    from pipeline.governance import AUDIT_LOG
    audit_summary = AUDIT_LOG.summary()
    print(f"  Audit events     : {audit_summary['total_events']}  "
          f"(errors: {audit_summary['error_count']})")
    from pipeline.memory import MEMORY
    print(f"  Memory runs      : {MEMORY.total_runs}  "
          f"total calls: {MEMORY.cumulative['total_calls_analyzed']}")
    print("█" * 60 + "\n")

    return final_state


if __name__ == "__main__":
    main()
