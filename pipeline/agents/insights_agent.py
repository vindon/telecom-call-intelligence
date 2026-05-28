"""
InsightsAgent  —  Agent 5 of 6
---------------------------------
The second LLM agent in the pipeline. Uses Gemini to synthesize aggregated
KPIs into actionable strategic recommendations for telecom operations leaders.

Control loop: Analyze → Critique → Synthesize (self-reflection deliberation)
-----------------------------------------------------------------------------
  Pass 1  Analyze   : Chain-of-Thought KPI analysis → initial insights
  Pass 2  Critique  : Self-reflection — grade each recommendation for specificity,
                      data-grounding, and actionability; identify gaps
  Pass 3  Synthesize: Incorporate critique to produce final recommendations

This 3-pass pattern catches generic recommendations and forces the LLM to
confront weak spots before the output leaves the agent. Enabled by default
(DELIBERATION_ENABLED=True in config); falls back to single-pass if any
Gemini call fails, and to rule-based fallback if all calls fail.

Outputs injected into PipelineState
-------------------------------------
  agent_insights — dict with executive_summary, top_recommendations,
                   quick_wins, risk_flags, source, deliberation_passes
"""

from __future__ import annotations

import json
import os

from pipeline.config import (
    CLAUDE_INSIGHTS_MODEL,
    DELIBERATION_ENABLED,
    INSIGHTS_MODEL,
    INSIGHTS_TEMPERATURE,
    MAX_OUTPUT_TOKENS,
    NVIDIA_BASE_URL,
    NVIDIA_INSIGHTS_MODEL,
)
from pipeline.governance import AUDIT_LOG
from pipeline.logger import get_logger
from pipeline.memory import MEMORY
from pipeline.security import GEMINI_RATE_LIMITER, OUTPUT_SANITIZER, SECRET_GUARD

log = get_logger(__name__)


# ── Prompt templates ──────────────────────────────────────────────────

# Pass 1 — Chain-of-Thought analysis
ANALYZE_PROMPT = """\
You are a senior telecom contact center strategy consultant.

Below are aggregated KPIs from {n_calls} analyzed customer care calls.

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

{historical_context}

STEP-BY-STEP REASONING INSTRUCTIONS (Chain-of-Thought):
Before generating recommendations, reason through each KPI systematically:
  1. Which KPIs are significantly above or below industry benchmarks?
  2. What root causes are most likely given the pattern of KPIs together?
  3. Which interventions would have the highest ROI given this specific data?
  4. What risks are NOT visible in this data but are implied by the patterns?

Respond ONLY with a valid JSON object:
{{
  "_cot_reasoning": "<your step-by-step analysis before recommendations>",
  "executive_summary": "<2-3 sentence board-level summary>",
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

# Pass 2 — Self-critique (self-reflection)
CRITIQUE_PROMPT = """\
You are a critical reviewer of strategic consulting recommendations.

Below are AI-generated insights from a telecom contact center analysis.
Your job is to rigorously critique them BEFORE they reach an executive audience.

--- INSIGHTS TO CRITIQUE ---
{insights_json}

--- KPI CONTEXT ---
FCR: {fcr_pct}%   AHT: {aht_min} min   Avoidable: {avoidable_pct}%
AI-resolvable: {ai_pct}%   Escalation: {escalation_pct}%

Grade each top recommendation on:
  A. Data-grounded (does this directly follow from the KPIs above?)
  B. Specific (does this give a concrete action, not a platitude?)
  C. Non-duplicated (is this meaningfully different from the others?)

Respond ONLY with a valid JSON object:
{{
  "overall_quality": "<strong | adequate | weak>",
  "recommendation_grades": [
    {{"priority": 1, "grade": "A/B/C", "issues": "<specific gaps>", "improvement": "<what would make it better>"}}
  ],
  "executive_summary_critique": "<is it board-ready or too generic?>",
  "missing_insights": ["<important angle not covered>"]
}}
"""

# Pass 3 — Synthesis incorporating the critique
SYNTHESIZE_PROMPT = """\
You are a senior telecom contact center strategy consultant finalizing a board report.

You have initial insights and a quality critique. Produce the FINAL improved version
that addresses every critique point.

--- INITIAL INSIGHTS ---
{insights_json}

--- CRITIQUE ---
{critique_json}

--- KPIs (for reference) ---
FCR: {fcr_pct}%   AHT: {aht_min} min   AI-resolvable: {ai_pct}%
Escalation: {escalation_pct}%   Savings oppty: ${savings_usd:,.0f}/mo

INSTRUCTIONS:
- Rewrite any recommendation graded as "weak" or "inadequate"
- Ensure every recommendation is directly traceable to a specific KPI
- Remove generic recommendations; replace with data-specific ones
- The executive_summary must be board-ready: specific numbers, no platitudes

Respond ONLY with a valid JSON object matching the original schema:
{{
  "executive_summary": "<2-3 sentence board-level summary with specific numbers>",
  "top_recommendations": [
    {{
      "priority": 1,
      "title": "<short action title>",
      "insight": "<why this matters — cite a specific KPI>",
      "estimated_impact": "<quantified impact>"
    }}
  ],
  "quick_wins": ["<actionable item>", "<actionable item>", "<actionable item>"],
  "risk_flags": ["<risk based on data>", "<risk based on data>"]
}}

Generate exactly 5 top_recommendations, 3 quick_wins, and 2 risk_flags.
"""


# ── Rule-based fallback ───────────────────────────────────────────────

def _rule_based_insights(kpis: dict, qa_summary: dict, n_calls: int) -> dict:
    """Fallback when Gemini is unavailable — derives insights from KPI thresholds."""
    fcr    = kpis.get("fcr_rate_pct", 0)
    aht    = kpis.get("avg_handle_time_minutes", 0)
    avoid  = kpis.get("avoidable_call_rate_pct", 0)
    ai_pct = kpis.get("agentic_ai_resolvable_pct", 0)
    esc    = kpis.get("escalation_rate_pct", 0)

    recs = []
    if fcr < 70:
        recs.append({
            "priority": 1,
            "title": "Improve First Call Resolution",
            "insight": f"FCR of {fcr}% is below the 70-80% industry benchmark.",
            "estimated_impact": "Each 1% FCR improvement eliminates ~6 repeat calls per 100.",
        })
    if avoid > 20:
        recs.append({
            "priority": 2,
            "title": "Reduce Avoidable Call Volume",
            "insight": f"{avoid}% of calls are avoidable via proactive or self-serve channels.",
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
    _padding = [
        {
            "title": "Implement Continuous KPI Monitoring",
            "insight": "Ongoing KPI tracking enables faster response to emerging trends.",
            "estimated_impact": "Early detection of FCR dips prevents repeat-call spikes.",
        },
        {
            "title": "Expand Self-Serve Channel Coverage",
            "insight": "Low self-serve adoption suggests gaps in digital deflection.",
            "estimated_impact": "Each 5% deflection shift saves ~$30K/mo at 100K call volume.",
        },
        {
            "title": "Strengthen Agent Coaching Programme",
            "insight": "Consistent coaching on top failure patterns raises FCR and reduces AHT.",
            "estimated_impact": "10% AHT reduction equates to ~$60K/mo in labour savings.",
        },
    ]
    for pad in _padding:
        if len(recs) >= 5:
            break
        recs.append({"priority": len(recs) + 1, **pad})

    return {
        "source": "rule_based_fallback",
        "deliberation_passes": 0,
        "executive_summary": (
            f"Analysis of {n_calls} calls reveals an FCR of {fcr}%, AHT of {aht:.1f} min, "
            f"and {avoid}% avoidable call rate. {ai_pct}% of volume is agentic AI-resolvable."
        ),
        "top_recommendations": recs[:5],
        "quick_wins": [
            "Publish self-serve guides for the top 3 avoidable call reasons",
            "Add real-time FCR coaching alerts to agent desktops",
            "Route agentic-AI-resolvable intents to a chatbot pilot",
        ],
        "risk_flags": [
            f"FCR below 70%: {100 - fcr:.0f}% of customers may call back",
            "Insufficient data for trend analysis — run more batches for confidence",
        ],
    }


# ── Agent ─────────────────────────────────────────────────────────────

class InsightsAgent:
    """
    Stateless agent — instantiate once and call run() per pipeline invocation.

    Implements a 3-pass deliberation loop (Analyze → Critique → Synthesize)
    to produce self-reflective, data-grounded strategic recommendations.
    Falls back gracefully if any pass fails.
    """

    name = "InsightsAgent"

    def run(self, state: dict) -> dict:
        import time
        t0      = time.monotonic()
        metrics = state.get("aggregated_metrics", {})
        kpis    = metrics.get("kpis", {})
        qa_rep  = state.get("qa_report", {})
        n_calls = kpis.get("total_calls_analyzed", len(state.get("analysis_results", [])))

        AUDIT_LOG.record_agent_start(self.name, {"n_calls": n_calls,
                                                  "deliberation": DELIBERATION_ENABLED})
        log.info("[%s] Generating insights for %d calls (deliberation=%s)",
                 self.name, n_calls, DELIBERATION_ENABLED)

        # Retrieve historical context from both flat memory and vector store
        historical_context = self._get_rich_context(kpis, n_calls)

        # ── Deliberation loop or single-pass ─────────────────────────
        insights = None
        passes_completed = 0

        if DELIBERATION_ENABLED:
            insights, passes_completed = self._deliberation_loop(
                kpis, metrics, qa_rep, n_calls, historical_context
            )

        if insights is None:
            # Single-pass fallback
            insights = self._single_pass_llm(kpis, metrics, qa_rep, n_calls, historical_context)
            if insights:
                passes_completed = 1

        if insights is None:
            log.warning("[%s] All LLM calls failed — using rule-based fallback", self.name)
            insights = _rule_based_insights(kpis, qa_rep.get("summary", {}), n_calls)

        insights["deliberation_passes"] = passes_completed
        insights = OUTPUT_SANITIZER.sanitize_insights(insights)

        AUDIT_LOG.record_governance(
            check="insights_source", passed=True,
            details={"source": insights.get("source", "?"),
                     "passes": passes_completed},
        )
        AUDIT_LOG.record_agent_end(
            self.name,
            {"source": insights.get("source"), "passes": passes_completed,
             "n_recs": len(insights.get("top_recommendations", []))},
            elapsed_s=time.monotonic() - t0,
        )
        return {**state, "agent_insights": insights}

    # ── Deliberation: Analyze → Critique → Synthesize ─────────────────

    def _deliberation_loop(
        self,
        kpis: dict,
        metrics: dict,
        qa_rep: dict,
        n_calls: int,
        historical_context: str,
    ) -> tuple[dict | None, int]:
        """
        Run the 3-pass Analyze→Critique→Synthesize loop.
        Returns (final_insights, n_passes_completed) or (None, 0) on failure.
        """
        kpi_ctx = self._kpi_context(kpis, metrics)

        # ── Pass 1: Analyze (CoT) ────────────────────────────────────
        log.info("[%s] Deliberation Pass 1: Analyze (CoT)", self.name)
        initial = self._llm_call(
            self._build_analyze_prompt(kpis, metrics, qa_rep, n_calls, historical_context),
            temperature=INSIGHTS_TEMPERATURE,
        )
        if initial is None:
            return None, 0
        initial["source"] = "llm_single_pass"

        # ── Pass 2: Critique (self-reflection) ───────────────────────
        log.info("[%s] Deliberation Pass 2: Critique (self-reflection)", self.name)
        critique = self._llm_call(
            CRITIQUE_PROMPT.format(
                insights_json=json.dumps(initial, indent=2)[:3000],
                **kpi_ctx,
            ),
            temperature=0.1,  # low temp for consistent grading
        )
        if critique is None:
            log.warning("[%s] Critique pass failed — returning single-pass result", self.name)
            return initial, 1

        # ── Pass 3: Synthesize ───────────────────────────────────────
        log.info("[%s] Deliberation Pass 3: Synthesize", self.name)
        final = self._llm_call(
            SYNTHESIZE_PROMPT.format(
                insights_json=json.dumps(initial, indent=2)[:2000],
                critique_json=json.dumps(critique, indent=2)[:1500],
                **kpi_ctx,
            ),
            temperature=INSIGHTS_TEMPERATURE,
        )
        if final is None:
            log.warning("[%s] Synthesis pass failed — returning post-critique result", self.name)
            return initial, 2

        final["source"]   = "llm_deliberated"
        final["critique"] = critique.get("overall_quality", "unknown")
        log.info("[%s] Deliberation complete: quality=%s", self.name, final["critique"])
        return final, 3

    # ── Single-pass fallback ─────────────────────────────────────────

    def _single_pass_llm(
        self,
        kpis: dict,
        metrics: dict,
        qa_rep: dict,
        n_calls: int,
        historical_context: str,
    ) -> dict | None:
        result = self._llm_call(
            self._build_analyze_prompt(kpis, metrics, qa_rep, n_calls, historical_context),
            temperature=INSIGHTS_TEMPERATURE,
        )
        if result:
            result["source"] = "llm_single_pass"
        return result

    # ── Helpers ──────────────────────────────────────────────────────

    def _llm_call(self, prompt: str, temperature: float = 0.3) -> dict | None:
        """Call NVIDIA first; fall back to Claude if NVIDIA is unavailable."""
        result = self._nvidia_call(prompt, temperature)
        if result is not None:
            return result
        log.info("[%s] NVIDIA unavailable — falling back to Claude", self.name)
        return self._claude_call(prompt, temperature)

    def _nvidia_call(self, prompt: str, temperature: float = 0.3) -> dict | None:
        """Call NVIDIA NIM API (OpenAI-compatible). Returns parsed dict or None."""
        api_key = os.environ.get("NVIDIA_API_KEY")
        if not api_key:
            return None
        try:
            from openai import OpenAI

            client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)
            response = client.chat.completions.create(
                model=NVIDIA_INSIGHTS_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=MAX_OUTPUT_TOKENS,
            )
            raw = response.choices[0].message.content
            SECRET_GUARD.assert_no_secrets_in_output(raw)
            result = json.loads(raw)
            return OUTPUT_SANITIZER.sanitize_insights(result)

        except Exception as exc:
            if "429" in str(exc):
                log.warning("[%s] NVIDIA quota exhausted (429) — model=%s", self.name, NVIDIA_INSIGHTS_MODEL)
            else:
                log.warning("[%s] NVIDIA call failed (%s): %s", self.name, type(exc).__name__, exc)
            return None

    def _claude_call(self, prompt: str, temperature: float = 0.3) -> dict | None:
        """Call Anthropic Claude (fallback). Returns parsed dict or None."""
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=CLAUDE_INSIGHTS_MODEL,
                max_tokens=MAX_OUTPUT_TOKENS,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
                system="You are a strategic telecom analyst. Always respond with valid JSON only — no markdown fences, no prose.",
            )
            raw = response.content[0].text.strip()
            # strip markdown fences if present (```json ... ```)
            if raw.startswith("```"):
                raw = raw.split("```", 2)[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            SECRET_GUARD.assert_no_secrets_in_output(raw)
            result = json.loads(raw)
            return OUTPUT_SANITIZER.sanitize_insights(result)

        except Exception as exc:
            if "429" in str(exc) or "rate" in str(exc).lower():
                log.warning("[%s] Claude rate limited — model=%s", self.name, CLAUDE_INSIGHTS_MODEL)
            else:
                log.warning("[%s] Claude call failed (%s): %s", self.name, type(exc).__name__, exc)
            return None

    def _gemini_call(self, prompt: str, temperature: float = 0.3) -> dict | None:
        """Call Gemini (last-resort fallback). Returns parsed dict or None."""
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None
        try:
            from google import genai
            from google.genai import types

            GEMINI_RATE_LIMITER.acquire()
            client   = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=INSIGHTS_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=temperature,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            SECRET_GUARD.assert_no_secrets_in_output(response.text)
            result = json.loads(response.text)
            return OUTPUT_SANITIZER.sanitize_insights(result)

        except Exception as exc:
            from google.genai import errors as _genai_errors
            if isinstance(exc, _genai_errors.ClientError) and "429" in str(exc):
                log.warning("[%s] Gemini quota exhausted (429) — model=%s", self.name, INSIGHTS_MODEL)
            else:
                log.warning("[%s] Gemini call failed (%s): %s", self.name, type(exc).__name__, exc)
            return None

    def _build_analyze_prompt(
        self,
        kpis: dict,
        metrics: dict,
        qa_rep: dict,
        n_calls: int,
        historical_context: str,
    ) -> str:
        cost_dist  = metrics.get("distributions", {}).get("cost_driver", {})
        top_driver = max(cost_dist, key=cost_dist.get) if cost_dist else "unknown"
        hist_section = (
            f"\n--- Historical Performance Context ---\n{historical_context}\n"
            if historical_context else ""
        )
        return (hist_section + ANALYZE_PROMPT).format(
            n_calls               = n_calls,
            aht_min               = kpis.get("avg_handle_time_minutes", 0),
            fcr_pct               = kpis.get("fcr_rate_pct", 0),
            avoidable_pct         = kpis.get("avoidable_call_rate_pct", 0),
            ai_pct                = kpis.get("agentic_ai_resolvable_pct", 0),
            escalation_pct        = kpis.get("escalation_rate_pct", 0),
            repeat_high_pct       = kpis.get("repeat_call_risk_high_pct", 0),
            sentiment_improved_pct = kpis.get("sentiment_improved_pct", 0),
            savings_usd           = metrics.get("cost_levers", {}).get(
                                        "total_savings_opportunity_usd", 0),
            top_cost_driver       = top_driver,
            qa_avg_score          = qa_rep.get("summary", {}).get("avg_score", "N/A"),
            qa_verdict            = qa_rep.get("dataset_verdict", "N/A"),
            historical_context    = historical_context,
        )

    def _kpi_context(self, kpis: dict, metrics: dict) -> dict:
        """Compact dict of KPI values for the critique and synthesize prompts."""
        return {
            "fcr_pct":        kpis.get("fcr_rate_pct", 0),
            "aht_min":        kpis.get("avg_handle_time_minutes", 0),
            "avoidable_pct":  kpis.get("avoidable_call_rate_pct", 0),
            "ai_pct":         kpis.get("agentic_ai_resolvable_pct", 0),
            "escalation_pct": kpis.get("escalation_rate_pct", 0),
            "savings_usd":    metrics.get("cost_levers", {}).get("total_savings_opportunity_usd", 0),
        }

    def _get_rich_context(self, kpis: dict, n_calls: int) -> str:
        """
        Combine flat memory history with vector-semantic similarity context.
        Vector store retrieves runs most similar to the current KPI profile.
        """
        flat_context = MEMORY.get_context_for_insights()

        # Semantic retrieval from vector memory
        try:
            from pipeline.vector_memory import VECTOR_STORE
            if VECTOR_STORE.size > 0:
                query_text = (
                    f"FCR {kpis.get('fcr_rate_pct', 0)}% "
                    f"AHT {kpis.get('avg_handle_time_minutes', 0)} min "
                    f"escalation {kpis.get('escalation_rate_pct', 0)}% "
                    f"AI-resolvable {kpis.get('agentic_ai_resolvable_pct', 0)}%"
                )
                vector_context = VECTOR_STORE.format_context(query_text)
                if vector_context:
                    return f"{flat_context}\n\n{vector_context}"
        except Exception as exc:
            log.debug("[%s] Vector memory unavailable: %s", self.name, exc)

        return flat_context
