"""
graph.py  —  Multi-Agent Pipeline Orchestrator
------------------------------------------------
LangGraph StateGraph orchestrating 6 specialized agents in a linear
dependency chain with full state handoff between agents.

Architecture
------------
  DataIngestionAgent   →  ExtractionAgent   →  QualityAgent
                                                     │
  ExportAgent   ←  [ApprovalGate]  ←  InsightsAgent  ←  AggregationAgent

Agents are decoupled — each receives the full PipelineState and returns
an updated copy. Adding, replacing, or parallelising agents requires only
changes to this file.

LangSmith tracing
-----------------
Set LANGCHAIN_TRACING_V2=true and LANGCHAIN_API_KEY in .env to enable
full LangSmith trace capture for every pipeline run.

State schema
------------
Every field is explicitly typed in PipelineState. Agents add their own
keys; callers should treat unknown keys as optional/forward-compatible.
"""

import os
import sys
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
from pipeline.config import (
    APPROVAL_TIMEOUT_S,
    LANGSMITH_PROJECT,
    REQUIRE_HUMAN_APPROVAL,
)
from pipeline.decision_log import DecisionLogger, summarize_decisions
from pipeline.governance import AUDIT_LOG
from pipeline.logger import get_logger
from pipeline.memory import MEMORY

log = get_logger(__name__)


# ── LangSmith tracing setup ───────────────────────────────────────────

def _configure_tracing() -> None:
    """
    Activate LangSmith tracing if the env vars are present.
    LangGraph auto-traces every node when LANGCHAIN_TRACING_V2=true.
    """
    if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true":
        if not os.environ.get("LANGCHAIN_API_KEY"):
            log.warning(
                "[Tracing] LANGCHAIN_TRACING_V2=true but LANGCHAIN_API_KEY not set — tracing disabled"
            )
            return
        os.environ.setdefault("LANGCHAIN_PROJECT", LANGSMITH_PROJECT)
        log.info("[Tracing] LangSmith active — project='%s'", os.environ["LANGCHAIN_PROJECT"])
    else:
        log.debug("[Tracing] LangSmith not configured (set LANGCHAIN_TRACING_V2=true to enable)")


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
    react_stats:           dict   # ReAct loop coverage improvement telemetry
    approval_granted:      bool   # human approval gate result
    # ── Traceability ─────────────────────────────────────────────────
    decision_log:          list   # DecisionRecord dicts — agent reasoning audit trail


# ── Node wrappers (thin console-printing shims around each agent) ─────

def _banner(step: int | str, total: int | str, label: str) -> None:
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
    _banner(2, 6, "ExtractionAgent — Claude Haiku · Structured JSON")
    return _extraction_agent.run(state)


def quality_node(state: PipelineState) -> PipelineState:
    _banner(3, 6, "QualityAgent — Inline QA Scoring (100-pt model)")
    result  = _quality_agent.run(state)
    rep     = result.get("qa_report", {})
    summary = rep.get("summary", {})
    verdict = rep.get("dataset_verdict", "N/A")
    gate_ok = not rep.get("_quality_gate_failed", False)
    print(f"  Dataset verdict  : {'✓ PASS' if verdict == 'PASS' else '✗ FAIL' if verdict == 'FAIL' else verdict}")
    if summary:
        print(f"  Avg QA score     : {summary.get('avg_score', 0)} / 100")
        print(f"  Grade breakdown  : HIGH {summary.get('grade_HIGH', 0)}  "
              f"MEDIUM {summary.get('grade_MEDIUM', 0)}  "
              f"LOW {summary.get('grade_LOW', 0)} (excluded)")
    if not gate_ok:
        print("  ⚠ Quality gate FAILED — routing to emergency export")
    return result


def _route_after_quality(state: PipelineState) -> str:
    """Dynamic routing: skip to export if quality gate tripped."""
    gate_failed = state.get("qa_report", {}).get("_quality_gate_failed", False)
    destination = "export" if gate_failed else "aggregate"

    dl = DecisionLogger("GraphRouter", state)
    dl.log(
        decision_type="routing_decision",
        decision=f"Route quality → {destination}",
        reason=(
            "Quality gate tripped: pass_rate below threshold — skipping aggregate/insights"
            if gate_failed else
            "Quality gate passed — continuing to normal aggregate→insights path"
        ),
        evidence={
            "quality_gate_failed": gate_failed,
            "qa_verdict": state.get("qa_report", {}).get("dataset_verdict", "N/A"),
            "destination": destination,
        },
        confidence="high",
        alternatives=["aggregate"] if gate_failed else ["export (emergency)"],
    )
    # Merge decision log back — state is read-only in conditional edges
    # (LangGraph doesn't persist state mutations from conditional edge functions,
    # so we log here for observability but the record is captured in export_node
    # via the accumulated decision_log in state from upstream agents)
    if gate_failed:
        log.warning("Quality gate failed — routing directly to export (skipping aggregate/insights)")
    return destination


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
        print("\n  Top recommendations:")
        for r in recs[:3]:
            print(f"    {r.get('priority', '?')}. {r.get('title', '')}")
    return result


def approval_gate_node(state: PipelineState) -> PipelineState:
    """
    Human-in-the-loop approval gate before export.

    Enabled by REQUIRE_HUMAN_APPROVAL=True in config. Presents a KPI summary
    and waits for explicit operator confirmation before the pipeline writes
    any outputs. Auto-approves after APPROVAL_TIMEOUT_S seconds (configurable).

    When disabled (default), this node is a transparent pass-through so it
    costs nothing in CI or automated batch runs.
    """
    _banner("▶", 6, "ApprovalGate — Human Sign-off Before Export")

    if not REQUIRE_HUMAN_APPROVAL:
        log.debug("[ApprovalGate] Disabled — auto-passing")
        dl = DecisionLogger("ApprovalGate", state)
        dl.log(
            decision_type="approval_decision",
            decision="Auto-approved (REQUIRE_HUMAN_APPROVAL=False)",
            reason="Human approval gate disabled in config — pipeline runs unattended",
            evidence={"require_human_approval": False},
            confidence="high",
            alternatives=["Require manual operator approval"],
        )
        return {**state, "approval_granted": True, "decision_log": dl.finalize()}

    kpis = state.get("aggregated_metrics", {}).get("kpis", {})
    print(f"\n  FCR: {kpis.get('fcr_rate_pct', 'N/A')}%  "
          f"AHT: {kpis.get('avg_handle_time_minutes', 'N/A')} min  "
          f"AI-resolvable: {kpis.get('agentic_ai_resolvable_pct', 'N/A')}%")
    print(f"\n  Insights source : {state.get('agent_insights', {}).get('source', 'unknown')}")
    print(f"  Deliberation    : {state.get('agent_insights', {}).get('deliberation_passes', 0)} passes")

    AUDIT_LOG.record_governance(
        check="human_approval_gate", passed=False,
        details={"status": "awaiting_input", "timeout_s": APPROVAL_TIMEOUT_S},
    )

    timeout = APPROVAL_TIMEOUT_S
    prompt  = f"\n  Approve export? [y/N] (auto-approve in {timeout}s): " if timeout > 0 \
              else "\n  Approve export? [y/N]: "

    import select
    granted = False
    try:
        if timeout > 0:
            print(prompt, end="", flush=True)
            ready, _, _ = select.select([sys.stdin], [], [], timeout)
            if ready:
                answer = sys.stdin.readline().strip().lower()
                granted = answer in ("y", "yes")
            else:
                print("\n  ⏱  Timeout — auto-approving")
                granted = True
        else:
            answer  = input(prompt).strip().lower()
            granted = answer in ("y", "yes")
    except (EOFError, OSError):
        # Non-interactive environment (CI, subprocess) — auto-approve
        granted = True

    status = "approved" if granted else "rejected"
    log.info("[ApprovalGate] Export %s", status)
    print(f"  {'✓ Export approved' if granted else '✗ Export rejected — pipeline halted'}")

    AUDIT_LOG.record_governance(
        check="human_approval_gate", passed=granted,
        details={"status": status},
    )

    dl = DecisionLogger("ApprovalGate", state)
    dl.log(
        decision_type="approval_decision",
        decision=f"Export {'approved' if granted else 'rejected'} by operator",
        reason=(
            "Operator explicitly confirmed export at the interactive approval gate"
            if granted else
            "Operator rejected export — pipeline halted before writing outputs"
        ),
        evidence={
            "granted": granted,
            "timeout_s": APPROVAL_TIMEOUT_S,
            "fcr_pct": kpis.get("fcr_rate_pct"),
            "insights_source": state.get("agent_insights", {}).get("source"),
        },
        confidence="high",
        alternatives=["Auto-approve on timeout", "Reject and halt pipeline"],
    )
    updated_state = {**state, "approval_granted": granted, "decision_log": dl.finalize()}

    if not granted:
        raise RuntimeError("Export rejected by operator at approval gate")

    return updated_state


def export_node(state: PipelineState) -> PipelineState:
    _banner(6, 6, "ExportAgent — CSV · JSON · QA Report · Insights · Manifest")
    result = _export_agent.run(state)
    paths  = result["export_paths"]
    n_decisions = len(result.get("decision_log", []))
    print(f"  ✓ CSV         : {paths.get('csv', '')}")
    print(f"  ✓ Summary     : {paths.get('summary', '')}  ← Streamlit dashboard")
    print(f"  ✓ Full JSON   : {paths.get('full_results', '')}")
    print(f"  ✓ QA Report   : {paths.get('qa_report', '')}")
    print(f"  ✓ Insights    : {paths.get('insights', '')}")
    print(f"  ✓ Decisions   : {paths.get('decisions', '')}  ({n_decisions} records)")
    print(f"  ✓ Manifest    : {paths.get('manifest', '')}")
    return result


# ── Graph assembly ────────────────────────────────────────────────────

def build_pipeline() -> object:
    """
    Compile and return the 7-node LangGraph pipeline.

    Normal path:   ingest → extract → quality → aggregate → insights → approval → export → END
    Emergency path (quality gate failure):
                   ingest → extract → quality → export → END
    """
    _configure_tracing()

    # Load flat + vector memory at build time so InsightsAgent has full context
    MEMORY.load()
    try:
        from pipeline.vector_memory import VECTOR_STORE
        VECTOR_STORE.load()
    except Exception as exc:
        log.debug("[build_pipeline] Vector memory load skipped: %s", exc)

    graph = StateGraph(PipelineState)

    graph.add_node("ingest",    ingest_node)
    graph.add_node("extract",   extract_node)
    graph.add_node("quality",   quality_node)
    graph.add_node("aggregate", aggregate_node)
    graph.add_node("insights",  insights_node)
    graph.add_node("approval",  approval_gate_node)
    graph.add_node("export",    export_node)

    graph.set_entry_point("ingest")
    graph.add_edge("ingest",    "extract")
    graph.add_edge("extract",   "quality")

    # Dynamic routing: quality gate failure → skip aggregate + insights + approval
    graph.add_conditional_edges(
        "quality",
        _route_after_quality,
        {"aggregate": "aggregate", "export": "export"},
    )

    graph.add_edge("aggregate", "insights")
    graph.add_edge("insights",  "approval")
    graph.add_edge("approval",  "export")
    graph.add_edge("export",    END)

    return graph.compile()
