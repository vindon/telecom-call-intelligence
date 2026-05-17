"""
graph.py  —  Multi-Agent Pipeline Orchestrator
------------------------------------------------
LangGraph StateGraph orchestrating 6 specialized agents in a linear
dependency chain with full state handoff between agents.

Architecture
------------
  DataIngestionAgent   →  ExtractionAgent   →  QualityAgent
                                                     │
  ExportAgent          ←  InsightsAgent     ←  AggregationAgent

Agents are decoupled — each receives the full PipelineState and returns
an updated copy. Adding, replacing, or parallelising agents requires only
changes to this file.

State schema
------------
Every field is explicitly typed in PipelineState. Agents add their own
keys; callers should treat unknown keys as optional/forward-compatible.
"""

from typing import TypedDict

from langgraph.graph import END, StateGraph

from pipeline.agents import (
    AggregationAgent,
    DataIngestionAgent,
    ExportAgent,
    ExtractionAgent,
    InsightsAgent,
    QualityAgent,
)
from pipeline.logger import get_logger

log = get_logger(__name__)

# ── Agent singletons (stateless — safe to share across invocations) ───
_data_agent        = DataIngestionAgent()
_extraction_agent  = ExtractionAgent()
_quality_agent     = QualityAgent()
_aggregation_agent = AggregationAgent()
_insights_agent    = InsightsAgent()
_export_agent      = ExportAgent()


# ── State schema ──────────────────────────────────────────────────────

class PipelineState(TypedDict):
    # ── Run configuration ────────────────────────────────────────────
    n_calls:               int
    seed:                  int
    offset:                int
    inter_call_delay:      float
    checkpoint_key:        str
    # ── Agent outputs ────────────────────────────────────────────────
    raw_transcripts:       list   # DataIngestionAgent
    validated_transcripts: list   # DataIngestionAgent
    analysis_results:      list   # ExtractionAgent  (enriched by QualityAgent)
    qa_report:             dict   # QualityAgent
    qa_passed_results:     list   # QualityAgent
    aggregated_metrics:    dict   # AggregationAgent
    agent_insights:        dict   # InsightsAgent
    export_paths:          dict   # ExportAgent
    # ── Telemetry ────────────────────────────────────────────────────
    validation_errors:     list
    failed_call_ids:       list
    token_usage:           dict


# ── Node wrappers (thin console-printing shims around each agent) ─────

def _banner(step: int, total: int, label: str) -> None:
    print("\n" + "═" * 60)
    print(f"  AGENT {step}/{total} │ {label}")
    print("═" * 60)


def ingest_node(state: PipelineState) -> PipelineState:
    _banner(1, 6, "DataIngestionAgent — Fetch & Validate")
    result = _data_agent.run(state)
    n_valid = len(result["validated_transcripts"])
    n_skip  = len(result["validation_errors"])
    print(f"  ✓ Valid: {n_valid}  |  Skipped: {n_skip}")
    for e in result["validation_errors"][:5]:
        print(f"    - {e}")
    if n_skip > 5:
        print(f"    … (+{n_skip - 5} more)")
    return result


def extract_node(state: PipelineState) -> PipelineState:
    _banner(2, 6, "ExtractionAgent — Gemini 2.5 Flash Lite · Structured JSON")
    return _extraction_agent.run(state)


def quality_node(state: PipelineState) -> PipelineState:
    _banner(3, 6, "QualityAgent — Inline QA Scoring (100-pt model)")
    result  = _quality_agent.run(state)
    rep     = result.get("qa_report", {})
    summary = rep.get("summary", {})
    verdict = rep.get("dataset_verdict", "N/A")
    print(f"  Dataset verdict  : {'✓ PASS' if verdict == 'PASS' else '✗ FAIL' if verdict == 'FAIL' else verdict}")
    if summary:
        print(f"  Avg QA score     : {summary.get('avg_score', 0)} / 100")
        print(f"  Grade breakdown  : HIGH {summary.get('grade_HIGH', 0)}  "
              f"MEDIUM {summary.get('grade_MEDIUM', 0)}  "
              f"LOW {summary.get('grade_LOW', 0)} (excluded)")
    return result


def aggregate_node(state: PipelineState) -> PipelineState:
    _banner(4, 6, "AggregationAgent — Executive KPI Computation")
    result = _aggregation_agent.run(state)
    kpis   = result["aggregated_metrics"]["kpis"]
    usage  = result["token_usage"]
    print(f"  Calls aggregated  : {kpis['total_calls_analyzed']}")
    print(f"  Avg handle time   : {kpis['avg_handle_time_minutes']} min")
    print(f"  FCR rate          : {kpis['fcr_rate_pct']}%")
    print(f"  Avoidable calls   : {kpis['avoidable_call_rate_pct']}%")
    print(f"  Agentic AI oppty  : {kpis['agentic_ai_resolvable_pct']}%")
    print(f"  Savings oppty     : ${result['aggregated_metrics']['cost_levers']['total_savings_opportunity_usd']:,.0f}/mo (est.)")
    print(f"  Inference tokens  : {usage.get('total_tokens', 0):,}  "
          f"(${usage.get('total_cost_usd', 0):.4f} USD)")
    return result


def insights_node(state: PipelineState) -> PipelineState:
    _banner(5, 6, "InsightsAgent — LLM Strategic Recommendations")
    result   = _insights_agent.run(state)
    insights = result.get("agent_insights", {})
    source   = insights.get("source", "unknown")
    print(f"  Insights source  : {source}")
    summary_text = insights.get("executive_summary", "")
    if summary_text:
        # Word-wrap at 56 chars for clean console output
        words  = summary_text.split()
        line   = "  "
        for word in words:
            if len(line) + len(word) + 1 > 58:
                print(line)
                line = "  " + word + " "
            else:
                line += word + " "
        if line.strip():
            print(line)
    recs = insights.get("top_recommendations", [])
    if recs:
        print(f"\n  Top recommendations:")
        for r in recs[:3]:
            print(f"    {r.get('priority', '?')}. {r.get('title', '')}")
    return result


def export_node(state: PipelineState) -> PipelineState:
    _banner(6, 6, "ExportAgent — CSV · JSON · QA Report · Insights · Manifest")
    result = _export_agent.run(state)
    paths  = result["export_paths"]
    print(f"  ✓ CSV         : {paths.get('csv', '')}")
    print(f"  ✓ Summary     : {paths.get('summary', '')}  ← Streamlit dashboard")
    print(f"  ✓ Full JSON   : {paths.get('full_results', '')}")
    print(f"  ✓ QA Report   : {paths.get('qa_report', '')}")
    print(f"  ✓ Insights    : {paths.get('insights', '')}")
    print(f"  ✓ Manifest    : {paths.get('manifest', '')}")
    return result


# ── Graph assembly ────────────────────────────────────────────────────

def build_pipeline() -> object:
    """Compile and return the 6-agent LangGraph pipeline."""
    graph = StateGraph(PipelineState)

    graph.add_node("ingest",     ingest_node)
    graph.add_node("extract",    extract_node)
    graph.add_node("quality",    quality_node)
    graph.add_node("aggregate",  aggregate_node)
    graph.add_node("insights",   insights_node)
    graph.add_node("export",     export_node)

    graph.set_entry_point("ingest")
    graph.add_edge("ingest",    "extract")
    graph.add_edge("extract",   "quality")
    graph.add_edge("quality",   "aggregate")
    graph.add_edge("aggregate", "insights")
    graph.add_edge("insights",  "export")
    graph.add_edge("export",    END)

    return graph.compile()
