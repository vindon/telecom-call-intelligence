"""
InsightsAgent  —  Agent 5 of 6
---------------------------------
The second LLM agent in the pipeline. Uses Gemini to synthesize aggregated
KPIs into actionable strategic recommendations for telecom operations leaders.

Unlike ExtractionAgent (which reads individual transcripts), InsightsAgent
operates on the aggregated view of all calls — thinking cross-functionally
about cost reduction, customer experience, and automation opportunities.

Prompt design:
  Input  : KPI summary (FCR, AHT, avoidable call rate, AI resolvability,
           sentiment, escalation, repeat risk, cost levers)
  Output : JSON with executive_summary, top_recommendations (prioritised),
           quick_wins, and risk_flags

Graceful degradation:
  If the Gemini quota is exhausted or the call fails, InsightsAgent falls
  back to rule-based insights derived directly from the KPIs — so the
  pipeline always completes.

Outputs injected into PipelineState:
  agent_insights — dict with recommendations and summary text
"""

from __future__ import annotations

import json
import os

from pipeline.governance import AUDIT_LOG
from pipeline.logger     import get_logger
from pipeline.memory     import MEMORY

log = get_logger(__name__)

INSIGHTS_MODEL = "gemini-2.5-flash-lite"

INSIGHTS_PROMPT_TEMPLATE = """\
You are a senior telecom contact center strategy consultant.

Below are aggregated KPIs from a sample of {n_calls} analyzed customer care calls.
Generate strategic recommendations to reduce cost-to-serve and improve customer experience.

--- KPIs ---
Total calls analyzed       : {n_calls}
Average Handle Time        : {aht_min} min
First Call Resolution (FCR): {fcr_pct}%
Avoidable Call Rate        : {avoidable_pct}%
Agentic AI Resolvable      : {ai_pct}%
Escalation Rate            : {escalation_pct}%
Repeat Call Risk (High)    : {repeat_high_pct}%
Customer Sentiment Improved: {sentiment_improved_pct}%
Est. Monthly Savings Oppty : ${savings_usd:,.0f}
Top Cost Driver            : {top_cost_driver}

--- QA Summary ---
Average QA Score           : {qa_avg_score}/100
Extraction Quality Verdict : {qa_verdict}

Respond ONLY with a valid JSON object matching this exact schema:
{{
  "executive_summary": "<2-3 sentence board-level summary of the data>",
  "top_recommendations": [
    {{
      "priority": 1,
      "title": "<short action title>",
      "insight": "<why this matters based on the KPIs>",
      "estimated_impact": "<quantified or directional impact>"
    }}
  ],
  "quick_wins": ["<actionable item>", "<actionable item>", "<actionable item>"],
  "risk_flags": ["<risk based on data>", "<risk based on data>"]
}}

Generate exactly 5 top_recommendations, 3 quick_wins, and 2 risk_flags.
"""


def _rule_based_insights(kpis: dict, qa_summary: dict, n_calls: int) -> dict:
    """Fallback when Gemini is unavailable — derives insights from KPI thresholds."""
    fcr     = kpis.get("fcr_rate_pct", 0)
    aht     = kpis.get("avg_handle_time_minutes", 0)
    avoid   = kpis.get("avoidable_call_rate_pct", 0)
    ai_pct  = kpis.get("agentic_ai_resolvable_pct", 0)
    esc     = kpis.get("escalation_rate_pct", 0)

    recs = []
    if fcr < 70:
        recs.append({
            "priority": 1,
            "title": "Improve First Call Resolution",
            "insight": f"FCR of {fcr}% is below the 70-80% industry benchmark.",
            "estimated_impact": "Each 1% FCR improvement saves ~6 repeat calls per 100.",
        })
    if avoid > 20:
        recs.append({
            "priority": 2,
            "title": "Reduce Avoidable Call Volume",
            "insight": f"{avoid}% of calls are avoidable through proactive or self-serve channels.",
            "estimated_impact": f"Deflecting half saves ~${avoid * 0.005 * n_calls * 6:,.0f}/mo.",
        })
    if ai_pct > 30:
        recs.append({
            "priority": 3,
            "title": "Deploy Agentic AI for High-Volume Intents",
            "insight": f"{ai_pct}% of calls are fully resolvable by an AI agent.",
            "estimated_impact": "Automating these calls reduces live-agent load significantly.",
        })
    if aht > 8:
        recs.append({
            "priority": 4,
            "title": "Reduce Average Handle Time",
            "insight": f"AHT of {aht:.1f} min is above the 6-8 min benchmark.",
            "estimated_impact": "Each 1-min AHT reduction ≈ 12.5% cost saving on handle time.",
        })
    if esc > 15:
        recs.append({
            "priority": 5,
            "title": "Reduce Escalation Rate",
            "insight": f"Escalation rate of {esc}% adds cost and reduces satisfaction.",
            "estimated_impact": "Targeted coaching on top escalation triggers reduces rate by 20-30%.",
        })
    while len(recs) < 5:
        recs.append({
            "priority": len(recs) + 1,
            "title": "Implement Continuous Monitoring",
            "insight": "Ongoing KPI tracking enables faster response to emerging trends.",
            "estimated_impact": "Early detection of FCR dips prevents repeat-call spikes.",
        })

    return {
        "source":            "rule_based_fallback",
        "executive_summary": (
            f"Analysis of {n_calls} calls reveals an FCR of {fcr}%, AHT of {aht:.1f} min, "
            f"and {avoid}% avoidable call rate. {ai_pct}% of volume is agentic AI-resolvable, "
            f"representing a significant automation opportunity."
        ),
        "top_recommendations": recs[:5],
        "quick_wins": [
            "Publish self-serve guides for the top 3 avoidable call reasons",
            "Add real-time FCR coaching alerts to agent desktops",
            "Route agentic-AI-resolvable intents to a chatbot pilot",
        ],
        "risk_flags": [
            f"FCR below 70% risk: {100 - fcr:.0f}% of customers may call back",
            "Insufficient data for trend analysis — run more batches for confidence",
        ],
    }


class InsightsAgent:
    """
    Stateless agent — instantiate once and call run() per pipeline invocation.

    Makes one Gemini call to generate strategic recommendations from the KPIs.
    Falls back to rule-based insights if Gemini quota is exhausted.
    """

    name = "InsightsAgent"

    def run(self, state: dict) -> dict:
        import time
        t0      = time.monotonic()
        metrics = state.get("aggregated_metrics", {})
        kpis    = metrics.get("kpis", {})
        qa_rep  = state.get("qa_report", {})
        n_calls = kpis.get("total_calls_analyzed", len(state.get("analysis_results", [])))

        AUDIT_LOG.record_agent_start(self.name, {"n_calls": n_calls})
        log.info("[%s] Generating strategic insights for %d calls", self.name, n_calls)

        # Load historical context from agent memory
        historical_context = MEMORY.get_context_for_insights()
        if historical_context:
            log.info("[%s] Memory context: %s", self.name, historical_context[:80])

        # ── Attempt LLM insights ─────────────────────────────────────
        insights = self._llm_insights(kpis, metrics, qa_rep, n_calls, historical_context)

        if insights:
            log.info("[%s] LLM insights generated successfully", self.name)
            AUDIT_LOG.record_governance(
                check="insights_source", passed=True,
                details={"source": "gemini_llm", "historical_context_used": bool(historical_context)},
            )
        else:
            log.warning("[%s] LLM unavailable — using rule-based fallback", self.name)
            insights = _rule_based_insights(kpis, qa_rep.get("summary", {}), n_calls)
            AUDIT_LOG.record_governance(
                check="insights_source", passed=True,
                details={"source": "rule_based_fallback"},
            )

        AUDIT_LOG.record_agent_end(
            self.name,
            {"source": insights.get("source", "unknown"), "n_recommendations": len(insights.get("top_recommendations", []))},
            elapsed_s=time.monotonic() - t0,
        )
        return {**state, "agent_insights": insights}

    def _llm_insights(
        self,
        kpis:               dict,
        metrics:            dict,
        qa_rep:             dict,
        n_calls:            int,
        historical_context: str = "",
    ) -> dict | None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None

        try:
            from google import genai
            from google.genai import types
            from google.genai import errors as genai_errors

            client = genai.Client(api_key=api_key)

            # Build cost driver from distributions
            cost_dist  = metrics.get("distributions", {}).get("cost_driver", {})
            top_driver = max(cost_dist, key=cost_dist.get) if cost_dist else "unknown"

            sentiment_dist = metrics.get("distributions", {}).get("sentiment_end", {})
            positive_end   = sentiment_dist.get("positive", 0) + sentiment_dist.get("neutral", 0)

            # Append historical context from agent memory if available
            hist_section = (
                f"\n--- Historical Performance Context ---\n{historical_context}\n"
                if historical_context else ""
            )
            prompt = (hist_section + INSIGHTS_PROMPT_TEMPLATE).format(
                n_calls              = n_calls,
                aht_min              = kpis.get("avg_handle_time_minutes", 0),
                fcr_pct              = kpis.get("fcr_rate_pct", 0),
                avoidable_pct        = kpis.get("avoidable_call_rate_pct", 0),
                ai_pct               = kpis.get("agentic_ai_resolvable_pct", 0),
                escalation_pct       = kpis.get("escalation_rate_pct", 0),
                repeat_high_pct      = kpis.get("repeat_call_risk_high_pct", 0),
                sentiment_improved_pct = kpis.get("sentiment_improved_pct", 0),
                savings_usd          = metrics.get("cost_levers", {}).get(
                                           "total_savings_opportunity_usd", 0),
                top_cost_driver      = top_driver,
                qa_avg_score         = qa_rep.get("summary", {}).get("avg_score", "N/A"),
                qa_verdict           = qa_rep.get("dataset_verdict", "N/A"),
            )

            response = client.models.generate_content(
                model=INSIGHTS_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3,
                    max_output_tokens=2048,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )

            result = json.loads(response.text)
            result["source"] = "gemini_llm"
            return result

        except Exception as exc:
            log.warning("[%s] LLM insights failed: %s", self.name, str(exc)[:120])
            return None
