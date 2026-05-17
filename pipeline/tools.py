"""
pipeline/tools.py  —  Agent Tool Registry
------------------------------------------
Formal tool definitions for the multi-agent pipeline. Each tool has:
  • A JSON schema for inputs and outputs (enabling LLM-driven tool selection)
  • Execution logging via the audit log
  • A callable implementation

Agents invoke tools through the registry — not by calling Python functions
directly — which gives us:
  • Uniform invocation audit trail
  • Runtime schema validation
  • Swappable implementations (mock in tests, real in prod)

Built-in tools:
  fetch_transcripts      DataIngestionAgent
  score_extraction       QualityAgent
  compute_kpis           AggregationAgent
  generate_insights      InsightsAgent
  export_results         ExportAgent
"""

from __future__ import annotations

import functools
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from pipeline.logger import get_logger

log = get_logger(__name__)


# ── Tool definition ───────────────────────────────────────────────────

@dataclass
class Tool:
    name:         str
    description:  str
    agent:        str           # which agent owns this tool
    input_schema: dict          # JSON Schema for inputs
    output_schema: dict         # JSON Schema for outputs
    func:         Callable

    def invoke(self, audit_log=None, **kwargs) -> dict:
        t0 = time.monotonic()
        log.debug("[Tool:%s] Invoking with keys: %s", self.name, list(kwargs))

        try:
            result = self.func(**kwargs)
            elapsed = time.monotonic() - t0
            log.debug("[Tool:%s] OK in %.2fs", self.name, elapsed)
            if audit_log:
                audit_log.record_tool_call(
                    tool=self.name,
                    agent=self.agent,
                    inputs=list(kwargs.keys()),
                    success=True,
                    elapsed_s=round(elapsed, 3),
                )
            return result
        except Exception as exc:
            elapsed = time.monotonic() - t0
            log.error("[Tool:%s] FAILED in %.2fs: %s", self.name, elapsed, exc)
            if audit_log:
                audit_log.record_tool_call(
                    tool=self.name,
                    agent=self.agent,
                    inputs=list(kwargs.keys()),
                    success=False,
                    elapsed_s=round(elapsed, 3),
                    error=str(exc)[:200],
                )
            raise


# ── Tool Registry ─────────────────────────────────────────────────────

class ToolRegistry:
    """Central registry — agents discover and invoke tools through this."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        log.debug("[ToolRegistry] Registered tool: %s (agent=%s)", tool.name, tool.agent)

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found. Available: {self.list()}")
        return self._tools[name]

    def invoke(self, name: str, audit_log=None, **kwargs) -> Any:
        return self.get(name).invoke(audit_log=audit_log, **kwargs)

    def list(self) -> list[str]:
        return list(self._tools)

    def manifest(self) -> list[dict]:
        """Return tool definitions suitable for embedding in an LLM system prompt."""
        return [
            {
                "name":          t.name,
                "description":   t.description,
                "agent":         t.agent,
                "input_schema":  t.input_schema,
                "output_schema": t.output_schema,
            }
            for t in self._tools.values()
        ]


# ── Tool implementations (thin wrappers around pipeline modules) ──────

def _fetch_transcripts(n: int, seed: int, offset: int) -> dict:
    from pipeline.hf_loader import load_telecom_transcripts
    transcripts = load_telecom_transcripts(n=n, seed=seed, offset=offset)
    return {"transcripts": transcripts, "count": len(transcripts)}


def _score_extraction(record: dict) -> dict:
    from qa_audit import audit_record
    return audit_record(record)


def _compute_kpis(results: list) -> dict:
    from pipeline.aggregator import aggregate_metrics
    return aggregate_metrics(results)


def _generate_insights(kpis: dict, metrics: dict, qa_summary: dict, n_calls: int) -> dict:
    from pipeline.agents.insights_agent import _rule_based_insights
    return _rule_based_insights(kpis, qa_summary, n_calls)


def _export_results(results: list, metrics: dict, output_dir: str) -> dict:
    import json
    from datetime import datetime
    from pathlib import Path
    p = Path(output_dir)
    p.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = p / f"tool_export_{ts}.json"
    with open(path, "w") as fh:
        json.dump({"results": results, "metrics": metrics}, fh, indent=2)
    return {"path": str(path), "n_records": len(results)}


# ── Registry singleton ────────────────────────────────────────────────

REGISTRY = ToolRegistry()

REGISTRY.register(Tool(
    name         = "fetch_transcripts",
    description  = "Stream and sample call transcripts from the HuggingFace corpus",
    agent        = "DataIngestionAgent",
    input_schema = {
        "type": "object",
        "properties": {
            "n":      {"type": "integer", "description": "Number of calls to fetch"},
            "seed":   {"type": "integer", "description": "Random seed for reproducibility"},
            "offset": {"type": "integer", "description": "Conversation offset for batching"},
        },
        "required": ["n", "seed", "offset"],
    },
    output_schema = {
        "type": "object",
        "properties": {
            "transcripts": {"type": "array"},
            "count":       {"type": "integer"},
        },
    },
    func = _fetch_transcripts,
))

REGISTRY.register(Tool(
    name         = "score_extraction",
    description  = "Score a single extracted call record on 100-point QA model",
    agent        = "QualityAgent",
    input_schema = {
        "type": "object",
        "properties": {
            "record": {"type": "object", "description": "Extracted call result dict"},
        },
        "required": ["record"],
    },
    output_schema = {
        "type": "object",
        "properties": {
            "call_id":          {"type": "string"},
            "total_score":      {"type": "number"},
            "grade":            {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
            "dimension_scores": {"type": "object"},
            "issues":           {"type": "object"},
        },
    },
    func = _score_extraction,
))

REGISTRY.register(Tool(
    name         = "compute_kpis",
    description  = "Aggregate per-call results into executive KPIs and cost levers",
    agent        = "AggregationAgent",
    input_schema = {
        "type": "object",
        "properties": {
            "results": {"type": "array", "description": "List of extracted + QA-scored call dicts"},
        },
        "required": ["results"],
    },
    output_schema = {
        "type": "object",
        "properties": {
            "kpis":        {"type": "object"},
            "cost_levers": {"type": "object"},
            "distributions": {"type": "object"},
        },
    },
    func = _compute_kpis,
))

REGISTRY.register(Tool(
    name         = "generate_insights",
    description  = "Derive strategic recommendations from aggregated KPIs (rule-based fallback)",
    agent        = "InsightsAgent",
    input_schema = {
        "type": "object",
        "properties": {
            "kpis":       {"type": "object"},
            "metrics":    {"type": "object"},
            "qa_summary": {"type": "object"},
            "n_calls":    {"type": "integer"},
        },
        "required": ["kpis", "metrics", "qa_summary", "n_calls"],
    },
    output_schema = {
        "type": "object",
        "properties": {
            "executive_summary":   {"type": "string"},
            "top_recommendations": {"type": "array"},
            "quick_wins":          {"type": "array"},
            "risk_flags":          {"type": "array"},
        },
    },
    func = _generate_insights,
))

REGISTRY.register(Tool(
    name         = "export_results",
    description  = "Persist results and metrics to the output directory",
    agent        = "ExportAgent",
    input_schema = {
        "type": "object",
        "properties": {
            "results":    {"type": "array"},
            "metrics":    {"type": "object"},
            "output_dir": {"type": "string"},
        },
        "required": ["results", "metrics", "output_dir"],
    },
    output_schema = {
        "type": "object",
        "properties": {
            "path":      {"type": "string"},
            "n_records": {"type": "integer"},
        },
    },
    func = _export_results,
))
