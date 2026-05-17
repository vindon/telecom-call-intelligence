"""
pipeline/agents/
-----------------
Specialized agents for the Telecom Call Intelligence multi-agent pipeline.

Agent roster (execution order):
  1. DataIngestionAgent   — fetch + validate transcripts from HuggingFace
  2. ExtractionAgent      — Gemini structured JSON extraction per call
  3. QualityAgent         — inline QA scoring (completeness/enum/consistency/plausibility)
  4. AggregationAgent     — executive KPI computation and cost levers
  5. InsightsAgent        — LLM-generated strategic recommendations from KPIs
  6. ExportAgent          — CSV, JSON, manifest, QA report to disk
"""

from pipeline.agents.data_agent        import DataIngestionAgent
from pipeline.agents.extraction_agent  import ExtractionAgent
from pipeline.agents.quality_agent     import QualityAgent
from pipeline.agents.aggregation_agent import AggregationAgent
from pipeline.agents.insights_agent    import InsightsAgent
from pipeline.agents.export_agent      import ExportAgent

__all__ = [
    "DataIngestionAgent",
    "ExtractionAgent",
    "QualityAgent",
    "AggregationAgent",
    "InsightsAgent",
    "ExportAgent",
]
