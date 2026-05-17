"""
graph.py  —  LangGraph pipeline orchestration
-----------------------------------------------
Linear 5-node StateGraph:
  fetch → validate → analyze → aggregate → export → END

Each node is a pure function: receives PipelineState, returns updated state.
State accumulates data and metadata across all nodes.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import TypedDict

import pandas as pd
from langgraph.graph import END, StateGraph

from pipeline.aggregator import aggregate_metrics
from pipeline.analyzer import analyze_batch
from pipeline.hf_loader import load_telecom_transcripts
from pipeline.logger import get_logger
from pipeline.token_tracker import token_summary

log = get_logger(__name__)

OUTPUT_DIR = Path("outputs")


# ── State schema ──────────────────────────────────────────────────────

class PipelineState(TypedDict):
    # ── Run configuration ────────────────────────────────────────────
    n_calls:               int
    seed:                  int
    offset:                int     # Skip first N unique conversations (for batching)
    inter_call_delay:      float
    checkpoint_key:        str     # Unique key for checkpoint file (empty = no checkpoint)
    # ── Pipeline data ────────────────────────────────────────────────
    raw_transcripts:       list
    validated_transcripts: list
    analysis_results:      list
    aggregated_metrics:    dict
    export_paths:          dict
    # ── Telemetry ────────────────────────────────────────────────────
    validation_errors:     list
    failed_call_ids:       list
    token_usage:           dict


# ── Node 1: Fetch ─────────────────────────────────────────────────────

def fetch_node(state: PipelineState) -> PipelineState:
    """Pull transcripts from the HuggingFace streaming dataset."""
    print("\n" + "═" * 60)
    print("  NODE 1/5 │ Fetch — HuggingFace Dataset")
    print("═" * 60)

    log.info("Fetch node: n=%d  seed=%d  offset=%d",
             state["n_calls"], state["seed"], state.get("offset", 0))

    transcripts = load_telecom_transcripts(
        n      = state["n_calls"],
        seed   = state["seed"],
        offset = state.get("offset", 0),
    )

    log.info("Fetch complete: %d transcripts loaded", len(transcripts))
    return {**state, "raw_transcripts": transcripts}


# ── Node 2: Validate ──────────────────────────────────────────────────

def validate_node(state: PipelineState) -> PipelineState:
    """Schema and quality checks before sending to Groq."""
    print("\n" + "═" * 60)
    print("  NODE 2/5 │ Validate — Schema & Quality Checks")
    print("═" * 60)

    raw    = state["raw_transcripts"]
    valid: list[dict] = []
    errors: list[str] = []

    for t in raw:
        call_id = t.get("call_id", "UNKNOWN")

        if not t.get("transcript_text"):
            errors.append(f"{call_id}: empty transcript")
            continue

        if len(t["transcript_text"]) < 150:
            errors.append(
                f"{call_id}: transcript too short ({len(t['transcript_text'])} chars)"
            )
            continue

        if t.get("turn_count", 0) < 4:
            errors.append(f"{call_id}: too few turns ({t.get('turn_count')})")
            continue

        valid.append(t)

    print(f"  ✓ Valid: {len(valid)}  |  Skipped: {len(errors)}")
    for e in errors[:5]:
        print(f"    - {e}")
    if len(errors) > 5:
        print(f"    … (+{len(errors) - 5} more)")

    log.info("Validate: %d valid, %d skipped", len(valid), len(errors))
    return {**state, "validated_transcripts": valid, "validation_errors": errors}


# ── Node 3: Analyze ───────────────────────────────────────────────────

def analyze_node(state: PipelineState) -> PipelineState:
    """Send each transcript to Groq / Llama 3.3 70B for structured extraction."""
    print("\n" + "═" * 60)
    print("  NODE 3/5 │ Analyze — Groq · Llama 3.3 70B")
    print("═" * 60)

    log.info("Analyze node: %d transcripts, checkpoint_key='%s'",
             len(state["validated_transcripts"]), state.get("checkpoint_key", ""))

    results = analyze_batch(
        state["validated_transcripts"],
        inter_call_delay = state.get("inter_call_delay", 2.0),
        checkpoint_key   = state.get("checkpoint_key", ""),
    )

    # Identify which validated calls produced no result
    result_ids = {r.get("call_id") for r in results}
    failed = [
        t["call_id"]
        for t in state["validated_transcripts"]
        if t["call_id"] not in result_ids
    ]

    log.info("Analyze complete: %d results, %d failures", len(results), len(failed))
    return {**state, "analysis_results": results, "failed_call_ids": failed}


# ── Node 4: Aggregate ─────────────────────────────────────────────────

def aggregate_node(state: PipelineState) -> PipelineState:
    """Compute executive KPIs, distributions, and cost levers from all results."""
    print("\n" + "═" * 60)
    print("  NODE 4/5 │ Aggregate — KPI Computation")
    print("═" * 60)

    results = state["analysis_results"]
    if not results:
        raise RuntimeError("No analysis results to aggregate. Check Node 3 logs.")

    metrics      = aggregate_metrics(results)
    usage_summary = token_summary(results)

    kpis = metrics["kpis"]
    print(f"  Calls aggregated  : {kpis['total_calls_analyzed']}")
    print(f"  Avg handle time   : {kpis['avg_handle_time_minutes']} min")
    print(f"  FCR rate          : {kpis['fcr_rate_pct']}%")
    print(f"  Avoidable calls   : {kpis['avoidable_call_rate_pct']}%")
    print(f"  Agentic AI oppty  : {kpis['agentic_ai_resolvable_pct']}%")
    print(f"  Savings oppty     : ${metrics['cost_levers']['total_savings_opportunity_usd']:,.0f}/mo (est.)")
    print(f"  Inference tokens  : {usage_summary.get('total_tokens', 0):,}  "
          f"(${usage_summary.get('total_cost_usd', 0):.4f} USD)")

    log.info(
        "Aggregate: FCR=%.1f%%  AHT=%.1f min  tokens=%d  cost=$%.4f",
        kpis["fcr_rate_pct"],
        kpis["avg_handle_time_minutes"],
        usage_summary.get("total_tokens", 0),
        usage_summary.get("total_cost_usd", 0),
    )

    return {**state, "aggregated_metrics": metrics, "token_usage": usage_summary}


# ── Node 5: Export ────────────────────────────────────────────────────

def export_node(state: PipelineState) -> PipelineState:
    """Persist all outputs: per-call CSV, summary JSON, full results JSON, manifest."""
    print("\n" + "═" * 60)
    print("  NODE 5/5 │ Export — CSV + Dashboard JSON")
    print("═" * 60)

    OUTPUT_DIR.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. Per-call CSV
    df       = pd.DataFrame(state["analysis_results"])
    csv_path = OUTPUT_DIR / f"call_results_{ts}.csv"
    df.to_csv(csv_path, index=False)

    # 2. Summary JSON — this is what the Streamlit dashboard reads
    metrics = dict(state["aggregated_metrics"])
    metrics["token_usage"] = state.get("token_usage", {})
    summary_path = OUTPUT_DIR / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)

    # 3. Full results JSON — for QA audit, debugging, and batch merging
    full_path = OUTPUT_DIR / f"full_results_{ts}.json"
    with open(full_path, "w", encoding="utf-8") as fh:
        json.dump(state["analysis_results"], fh, indent=2)

    # 4. Run manifest — immutable audit record for this execution
    manifest = {
        "run_timestamp":    ts,
        "offset":           state.get("offset", 0),
        "seed":             state.get("seed", 42),
        "n_requested":      state.get("n_calls", 0),
        "n_raw":            len(state.get("raw_transcripts", [])),
        "n_validated":      len(state.get("validated_transcripts", [])),
        "n_analyzed":       len(state.get("analysis_results", [])),
        "n_failed":         len(state.get("failed_call_ids", [])),
        "validation_errors":state.get("validation_errors", []),
        "failed_call_ids":  state.get("failed_call_ids", []),
        "token_usage":      state.get("token_usage", {}),
        "output_files": {
            "csv":          str(csv_path),
            "summary_json": str(summary_path),
            "full_json":    str(full_path),
        },
    }
    manifest_path = OUTPUT_DIR / f"run_manifest_{ts}.json"
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    log.info(
        "Export complete: %d results → %s | %s | %s",
        len(state["analysis_results"]), csv_path, summary_path, full_path,
    )

    print(f"  ✓ CSV         : {csv_path}")
    print(f"  ✓ Summary     : {summary_path}  ← loaded by Streamlit dashboard")
    print(f"  ✓ Full JSON   : {full_path}")
    print(f"  ✓ Manifest    : {manifest_path}")

    export_paths = {
        "csv":          str(csv_path),
        "summary":      str(summary_path),
        "full_results": str(full_path),
        "manifest":     str(manifest_path),
    }
    return {**state, "export_paths": export_paths}


# ── Graph assembly ────────────────────────────────────────────────────

def build_pipeline() -> object:
    """Compile and return the LangGraph pipeline."""
    graph = StateGraph(PipelineState)

    graph.add_node("fetch",     fetch_node)
    graph.add_node("validate",  validate_node)
    graph.add_node("analyze",   analyze_node)
    graph.add_node("aggregate", aggregate_node)
    graph.add_node("export",    export_node)

    graph.set_entry_point("fetch")
    graph.add_edge("fetch",     "validate")
    graph.add_edge("validate",  "analyze")
    graph.add_edge("analyze",   "aggregate")
    graph.add_edge("aggregate", "export")
    graph.add_edge("export",    END)

    return graph.compile()
