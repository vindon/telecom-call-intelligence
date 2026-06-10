"""
run_pipeline.py
---------------
Entry point for the Telecom Call Intelligence multi-agent pipeline.

Architecture (6 agents + approval gate, 7-node LangGraph):
  DataIngestionAgent  →  ExtractionAgent  →  QualityAgent
  AggregationAgent    →  InsightsAgent    →  [ApprovalGate]  →  ExportAgent

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

# Load .env before importing any pipeline module (they read API keys at call time)
load_dotenv()

# ── Startup API key validation ─────────────────────────────────────────
# Fail fast with a clear message rather than discovering a missing key
# 30-60 seconds into a run when the first LLM call fires.
# Validation is model-aware: EXTRACTION_MODEL drives which key is required.
from pipeline.config import (  # noqa: E402
    BUDGET_USD,
    DEFAULT_DELAY_S,
    DEFAULT_N_CALLS,
    DEFAULT_SEED,
    EXTRACTION_MODEL,
)


def _validate_api_keys() -> None:
    """Check that the required API keys are present for the configured models."""
    errors: list[str] = []

    if EXTRACTION_MODEL.startswith("claude"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            errors.append(
                f"ANTHROPIC_API_KEY not set — required for EXTRACTION_MODEL='{EXTRACTION_MODEL}'.\n"
                "  Add ANTHROPIC_API_KEY=sk-ant-... to your .env file.\n"
                "  Get a key at: https://console.anthropic.com"
            )
    else:
        if not os.environ.get("GEMINI_API_KEY"):
            errors.append(
                f"GEMINI_API_KEY not set — required for EXTRACTION_MODEL='{EXTRACTION_MODEL}'.\n"
                "  Add GEMINI_API_KEY=AIza... to your .env file.\n"
                "  Free key at: https://aistudio.google.com"
            )

    # NVIDIA key is optional (InsightsAgent falls back to Claude → rule-based)
    # but warn if absent so the user knows which insights tier they'll get.
    if not os.environ.get("NVIDIA_API_KEY"):
        print("  INFO: NVIDIA_API_KEY not set — InsightsAgent will use Claude fallback.")

    if errors:
        print("\nERROR: Missing required API key(s):\n")
        for err in errors:
            print(f"  {err}\n")
        sys.exit(1)

_validate_api_keys()

from pipeline.graph import build_pipeline  # noqa: E402


def main() -> dict:
    parser = argparse.ArgumentParser(
        description="Telecom Call Intelligence — single-batch pipeline runner"
    )
    parser.add_argument(
        "--n",      type=int,   default=DEFAULT_N_CALLS,
        help=f"Number of calls to analyze (default: {DEFAULT_N_CALLS})",
    )
    parser.add_argument(
        "--seed",   type=int,   default=DEFAULT_SEED,
        help=f"Random seed for HuggingFace sampling (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--offset", type=int,   default=0,
        help="Skip first N unique conversations before sampling (default: 0). "
             "Use multiples of --n to guarantee non-overlapping batches.",
    )
    parser.add_argument(
        "--delay",  type=float, default=DEFAULT_DELAY_S,
        help=f"Seconds between API calls (default: {DEFAULT_DELAY_S})",
    )
    parser.add_argument(
        "--budget", type=float, default=None,
        help="Override budget cap for this batch in USD (default: BUDGET_USD from config). "
             "Set by run_batches.py to enforce per-batch spending limits.",
    )
    args = parser.parse_args()

    # Apply per-batch budget override from orchestrator before building the pipeline.
    # This ensures each subprocess enforces its share of the global budget cap,
    # not the full BUDGET_USD, preventing multi-batch runs from exceeding the total limit.
    if args.budget is not None:
        from pipeline.governance import BUDGET_GUARD
        BUDGET_GUARD.max_cost_usd = args.budget

    # Auto-generate a checkpoint key that encodes all sampling parameters
    checkpoint_key = f"offset{args.offset}_n{args.n}_seed{args.seed}"

    from pipeline.token_tracker import PROVIDER as _PROVIDER
    _est_cost_100 = BUDGET_USD  # show budget cap, not a guess
    print("\n" + "█" * 60)
    print("  TELECOM CALL INTELLIGENCE — Multi-Agent Pipeline")
    print("█" * 60)
    print("  Agents     : DataIngestion → Extraction → Quality →")
    print("               Aggregation  → Insights   → Export")
    print("  Dataset    : talkmap/telecom-conversation-corpus")
    print(f"  Model      : {EXTRACTION_MODEL}  ({_PROVIDER})")
    _effective_budget = args.budget if args.budget is not None else BUDGET_USD
    print(f"  Budget cap : ${_effective_budget:.4f} / batch  (global: ${BUDGET_USD:.2f})")
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
