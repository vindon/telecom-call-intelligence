"""
demo/app.py — cci.ai (Care Cost Intelligence) · Live Demo Server
-----------------------------------------------------------
Standalone FastAPI app that serves the interactive demo UI and exposes a
single /analyze endpoint.

Primary path: real Claude Haiku extraction via pipeline.analyzer.
Fallback path: pre-computed mock results for the 3 bundled sample transcripts
  (activated automatically when the API is unavailable / credits exhausted).
  Set DEMO_MOCK_ONLY=1 in .env to always use mock results.

Run from the project root:
    uvicorn demo.app:app --port 8001 --reload
Open:  http://localhost:8001
"""

import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

load_dotenv()

from pipeline.analyzer import (  # noqa: E402
    _USE_CLAUDE,
    analyze_transcript,
    load_system_prompt,
    score_field_coverage,
)
from pipeline.config import EXTRACTION_API_TIMEOUT_S  # noqa: E402
from pipeline.security import INPUT_SANITIZER, OUTPUT_SANITIZER  # noqa: E402

_DEMO_DIR = Path(__file__).parent
_MOCK_ONLY = os.getenv("DEMO_MOCK_ONLY", "").lower() in ("1", "true", "yes")

_client = None
_provider = "Claude Haiku"

# Explicit timeout — without one, a slow/unresponsive provider hangs the
# live demo request for the SDK's 600s default instead of failing fast.
if not _MOCK_ONLY:
    if _USE_CLAUDE:
        try:
            import anthropic
            _client = anthropic.Anthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY", ""), timeout=EXTRACTION_API_TIMEOUT_S, max_retries=1,
            )
            _provider = "Claude Haiku"
        except Exception:
            _client = None
    else:
        try:
            from google import genai
            from google.genai import types as genai_types
            _client = genai.Client(
                api_key=os.getenv("GEMINI_API_KEY", ""),
                http_options=genai_types.HttpOptions(timeout=EXTRACTION_API_TIMEOUT_S * 1000),
            )
            _provider = "Gemini"
        except Exception:
            _client = None

_system_prompt: str | None = None


def _get_prompt() -> str:
    global _system_prompt
    if _system_prompt is None:
        _system_prompt = load_system_prompt()
    return _system_prompt


# ── Pre-computed mock results for the 3 sample transcripts ─────────
_NULL_ISSUE = {
    "description": None, "category": None, "resolved": False, "resolution_method": None
}
_NULL_PRODUCT = {
    "name": None, "category": None, "context": None, "phase": None,
    "first_mentioned": None, "outcome": None
}

_MOCK = {
    "billing": {
        "call_id": "demo-billing-001",
        "call_date": None,
        "call_start_time": "00:00:05",
        "call_end_time": "00:03:37",
        "total_duration_seconds": 212,
        "agent_id": None, "customer_id": None,
        "queue_name": "billing", "channel": "voice",
        "phase_welcome_start": "00:00:05", "phase_welcome_end": "00:00:26",
        "phase_welcome_duration_seconds": 21,
        "phase_discovery_start": "00:00:26", "phase_discovery_end": "00:00:55",
        "phase_discovery_duration_seconds": 29,
        "phase_diagnosis_start": "00:00:55", "phase_diagnosis_end": "00:01:14",
        "phase_diagnosis_duration_seconds": 19,
        "phase_resolution_start": "00:02:48", "phase_resolution_end": "00:03:23",
        "phase_resolution_duration_seconds": 35,
        "phase_hold_total_seconds": 94, "hold_count": 1,
        "hold_timestamps": "00:01:14-00:02:48",
        "phase_upsell_start": None, "phase_upsell_end": None,
        "phase_upsell_duration_seconds": 0,
        "phase_relationship_building_duration_seconds": 15,
        "phase_relationship_building_examples": "Agent expressed empathy over billing shock|Explained roaming mechanism clearly",
        "phase_closing_start": "00:03:23", "phase_closing_end": "00:03:37",
        "phase_closing_duration_seconds": 14,
        "total_issues_count": 1,
        "issue_1_description": "Customer billed $285 vs usual ~$65 due to unexpected international roaming charges incurred near the Canadian border",
        "issue_1_category": "billing", "issue_1_resolved": True,
        "issue_1_resolution_method": "agent_action",
        "issue_2_description": None, "issue_2_category": None,
        "issue_2_resolved": False, "issue_2_resolution_method": None,
        "issue_3_description": None, "issue_3_category": None,
        "issue_3_resolved": False, "issue_3_resolution_method": None,
        "issue_4_description": None, "issue_4_category": None,
        "issue_4_resolved": False, "issue_4_resolution_method": None,
        "issue_5_description": None, "issue_5_category": None,
        "issue_5_resolved": False, "issue_5_resolution_method": None,
        "products_discussed": None, "plans_discussed": None,
        "services_mentioned": "International Roaming|Roaming Alert SMS",
        "account_type": "postpaid",
        "product_1_name": None, "product_1_category": None, "product_1_context": None,
        "product_1_phase": None, "product_1_first_mentioned": None, "product_1_outcome": None,
        "product_2_name": None, "product_2_category": None, "product_2_context": None,
        "product_2_phase": None, "product_2_first_mentioned": None, "product_2_outcome": None,
        "product_3_name": None, "product_3_category": None, "product_3_context": None,
        "product_3_phase": None, "product_3_first_mentioned": None, "product_3_outcome": None,
        "product_4_name": None, "product_4_category": None, "product_4_context": None,
        "product_4_phase": None, "product_4_first_mentioned": None, "product_4_outcome": None,
        "product_5_name": None, "product_5_category": None, "product_5_context": None,
        "product_5_phase": None, "product_5_first_mentioned": None, "product_5_outcome": None,
        "upsell_attempted": False, "upsell_offer_details": None,
        "upsell_relevant_to_eligibility": False, "upsell_scripted_or_personalized": None,
        "upsell_outcome": "not_attempted",
        "agent_skill_rating": "proficient",
        "agent_skill_rating_rationale": "Agent correctly identified roaming root cause, applied a fair one-time credit, and configured preventive alerts — all handled efficiently and empathetically",
        "agent_tool_struggle_detected": False, "agent_tool_struggle_evidence": None,
        "agent_used_correct_troubleshooting_path": True,
        "agent_disproportionate_time_phase": "none",
        "agent_disproportionate_time_rationale": None,
        "agent_empathy_statements_count": 3,
        "agent_followed_compliance_script": True,
        "customer_sentiment_start": "frustrated",
        "customer_sentiment_end": "neutral",
        "customer_sentiment_improved": True,
        "customer_expressed_dissatisfaction": True,
        "customer_dissatisfaction_reason": "Unexpectedly high bill of $285 vs normal $65",
        "primary_issue_resolved": True, "all_issues_resolved": True,
        "fcr_indicator": True, "escalation_required": False,
        "escalation_reason": None, "repeat_call_risk": "low",
        "repeat_call_risk_reason": "Issue fully resolved; roaming alert added to prevent recurrence",
        "could_be_self_served": False, "self_serve_channel_applicable": None,
        "self_serve_deflection_rationale": "Billing credit requires agent authority — not self-serviceable",
        "proactive_outreach_applicable": True,
        "proactive_outreach_trigger": "Customer phone connected to foreign (Canadian) roaming network",
        "agentic_ai_resolvable": True,
        "agentic_ai_resolvable_rationale": "Standard roaming dispute with clear evidence; AI agent could verify charges, apply one-time credit per policy, and configure roaming alerts autonomously",
        "primary_cost_driver": "billing", "avoidable_call": True,
        "avoidable_call_reason": "A proactive roaming alert SMS when the phone connected to a Canadian tower would have prevented bill shock and this call entirely",
        "vendor_tool_used": None, "handle_time_efficiency": "efficient",
        "call_summary": "Customer called billing support regarding a $285 bill (vs normal ~$65). Agent identified international roaming charges from a Canadian border visit, applied a $150 courtesy credit, and configured a roaming alert. Issue resolved in one call.",
        "key_observations": "Roaming charges triggered by border proximity without customer awareness|$150 courtesy credit applied as one-time policy exception|Roaming SMS alert added as preventive measure|AI-resolvable: policy-based credit decision with verifiable evidence|High proactive outreach opportunity: real-time roaming activation trigger available",
        "_cot_reasoning": "The customer's core issue is an unexpectedly high bill caused by international roaming charges incurred when their phone connected to a Canadian network while near the border. The agent correctly diagnosed the cause from the account's call log, resolved it by applying a $150 courtesy credit, and took the preventive step of adding a roaming alert. Customer sentiment improved from frustrated to neutral as the explanation and credit were provided.",
    },

    "technical": {
        "call_id": "demo-technical-001",
        "call_date": None,
        "call_start_time": "00:00:08",
        "call_end_time": "00:03:16",
        "total_duration_seconds": 188,
        "agent_id": None, "customer_id": None,
        "queue_name": "technical", "channel": "voice",
        "phase_welcome_start": "00:00:08", "phase_welcome_end": "00:00:44",
        "phase_welcome_duration_seconds": 36,
        "phase_discovery_start": "00:00:44", "phase_discovery_end": "00:01:15",
        "phase_discovery_duration_seconds": 31,
        "phase_diagnosis_start": "00:01:15", "phase_diagnosis_end": "00:02:22",
        "phase_diagnosis_duration_seconds": 67,
        "phase_resolution_start": "00:02:22", "phase_resolution_end": "00:03:07",
        "phase_resolution_duration_seconds": 45,
        "phase_hold_total_seconds": 0, "hold_count": 0,
        "hold_timestamps": None,
        "phase_upsell_start": None, "phase_upsell_end": None,
        "phase_upsell_duration_seconds": 0,
        "phase_relationship_building_duration_seconds": 18,
        "phase_relationship_building_examples": "Agent apologised for system-caused disruption|Acknowledged impact on customer's work",
        "phase_closing_start": "00:03:07", "phase_closing_end": "00:03:16",
        "phase_closing_duration_seconds": 9,
        "total_issues_count": 1,
        "issue_1_description": "Mobile data suspended for 3 days by automated usage monitoring system despite customer only working from home with video conferences",
        "issue_1_category": "technical", "issue_1_resolved": True,
        "issue_1_resolution_method": "agent_action",
        "issue_2_description": None, "issue_2_category": None,
        "issue_2_resolved": False, "issue_2_resolution_method": None,
        "issue_3_description": None, "issue_3_category": None,
        "issue_3_resolved": False, "issue_3_resolution_method": None,
        "issue_4_description": None, "issue_4_category": None,
        "issue_4_resolved": False, "issue_4_resolution_method": None,
        "issue_5_description": None, "issue_5_category": None,
        "issue_5_resolved": False, "issue_5_resolution_method": None,
        "products_discussed": None, "plans_discussed": None,
        "services_mentioned": "Mobile Data|Network Monitoring System",
        "account_type": "postpaid",
        "product_1_name": None, "product_1_category": None, "product_1_context": None,
        "product_1_phase": None, "product_1_first_mentioned": None, "product_1_outcome": None,
        "product_2_name": None, "product_2_category": None, "product_2_context": None,
        "product_2_phase": None, "product_2_first_mentioned": None, "product_2_outcome": None,
        "product_3_name": None, "product_3_category": None, "product_3_context": None,
        "product_3_phase": None, "product_3_first_mentioned": None, "product_3_outcome": None,
        "product_4_name": None, "product_4_category": None, "product_4_context": None,
        "product_4_phase": None, "product_4_first_mentioned": None, "product_4_outcome": None,
        "product_5_name": None, "product_5_category": None, "product_5_context": None,
        "product_5_phase": None, "product_5_first_mentioned": None, "product_5_outcome": None,
        "upsell_attempted": False, "upsell_offer_details": None,
        "upsell_relevant_to_eligibility": False, "upsell_scripted_or_personalized": None,
        "upsell_outcome": "not_attempted",
        "agent_skill_rating": "adequate",
        "agent_skill_rating_rationale": "Agent correctly identified the suspension cause and restored service promptly, but the systemic issue (second occurrence in 4 months) required escalation rather than a permanent fix",
        "agent_tool_struggle_detected": False, "agent_tool_struggle_evidence": None,
        "agent_used_correct_troubleshooting_path": True,
        "agent_disproportionate_time_phase": "diagnosis",
        "agent_disproportionate_time_rationale": "Diagnosis phase took 67s as agent needed to check outages, review account flags, and identify the automated suspension cause",
        "agent_empathy_statements_count": 4,
        "agent_followed_compliance_script": True,
        "customer_sentiment_start": "frustrated",
        "customer_sentiment_end": "negative",
        "customer_sentiment_improved": False,
        "customer_expressed_dissatisfaction": True,
        "customer_dissatisfaction_reason": "Second occurrence of automated suspension in 4 months impacting ability to work",
        "primary_issue_resolved": True, "all_issues_resolved": True,
        "fcr_indicator": False, "escalation_required": True,
        "escalation_reason": "Repeat automated suspension pattern escalated to network team for threshold review",
        "repeat_call_risk": "high",
        "repeat_call_risk_reason": "Second suspension in 4 months; root cause (threshold misconfiguration) not permanently fixed in this call",
        "could_be_self_served": False, "self_serve_channel_applicable": None,
        "self_serve_deflection_rationale": "Automated suspension removal requires agent-level account access — cannot be self-served through app or IVR",
        "proactive_outreach_applicable": False,
        "proactive_outreach_trigger": None,
        "agentic_ai_resolvable": True,
        "agentic_ai_resolvable_rationale": "Suspension detection and removal follows a deterministic policy pattern; AI agent could detect the suspension flag, verify usage context, and reinstate service with network team notification automatically",
        "primary_cost_driver": "technical", "avoidable_call": True,
        "avoidable_call_reason": "Automated suspension system incorrectly flagged legitimate WFH usage; a smarter usage pattern model would have prevented the suspension and this call",
        "vendor_tool_used": None, "handle_time_efficiency": "efficient",
        "call_summary": "Customer's mobile data was suspended for 3 days by an automated monitoring system after high video conference usage was flagged as unusual. Agent reinstated service, apologised, and escalated to the network team. This is the second such incident in 4 months — repeat call risk is high.",
        "key_observations": "Second automated suspension in 4 months — systemic threshold issue not resolved|Agent reinstated service but root cause remains|FCR not achieved: escalation required for permanent fix|High AI automation potential: suspension pattern is deterministic|Customer sentiment did not improve — lingering trust issue",
        "_cot_reasoning": "The customer's mobile data was suspended for 3 days by an automated system that misclassified normal WFH video conference activity as unusual usage. The agent correctly diagnosed the automated suspension, reinstated the service, and escalated to the network team. However, the customer's sentiment remained negative as this is the second occurrence in 4 months and the systemic issue was not permanently resolved in this call.",
    },

    "plan": {
        "call_id": "demo-plan-001",
        "call_date": None,
        "call_start_time": "00:00:06",
        "call_end_time": "00:02:46",
        "total_duration_seconds": 160,
        "agent_id": None, "customer_id": None,
        "queue_name": "sales", "channel": "voice",
        "phase_welcome_start": "00:00:06", "phase_welcome_end": "00:00:38",
        "phase_welcome_duration_seconds": 32,
        "phase_discovery_start": "00:00:38", "phase_discovery_end": "00:00:56",
        "phase_discovery_duration_seconds": 18,
        "phase_diagnosis_start": "00:00:56", "phase_diagnosis_end": "00:01:28",
        "phase_diagnosis_duration_seconds": 32,
        "phase_resolution_start": "00:01:28", "phase_resolution_end": "00:02:30",
        "phase_resolution_duration_seconds": 62,
        "phase_hold_total_seconds": 0, "hold_count": 0,
        "hold_timestamps": None,
        "phase_upsell_start": "00:00:56", "phase_upsell_end": "00:02:10",
        "phase_upsell_duration_seconds": 74,
        "phase_relationship_building_duration_seconds": 10,
        "phase_relationship_building_examples": "Agent personalised recommendation based on actual usage history",
        "phase_closing_start": "00:02:30", "phase_closing_end": "00:02:46",
        "phase_closing_duration_seconds": 16,
        "total_issues_count": 1,
        "issue_1_description": "Customer repeatedly hitting 10GB data cap before month end; needs plan upgrade",
        "issue_1_category": "plan", "issue_1_resolved": True,
        "issue_1_resolution_method": "agent_action",
        "issue_2_description": None, "issue_2_category": None,
        "issue_2_resolved": False, "issue_2_resolution_method": None,
        "issue_3_description": None, "issue_3_category": None,
        "issue_3_resolved": False, "issue_3_resolution_method": None,
        "issue_4_description": None, "issue_4_category": None,
        "issue_4_resolved": False, "issue_4_resolution_method": None,
        "issue_5_description": None, "issue_5_category": None,
        "issue_5_resolved": False, "issue_5_resolution_method": None,
        "products_discussed": "Basic 10GB|Flex 20GB|Smart 30GB|Unlimited",
        "plans_discussed": "Basic 10GB|Flex 20GB|Smart 30GB|Unlimited",
        "services_mentioned": "Data Rollover|International Roaming",
        "account_type": "postpaid",
        "product_1_name": "Smart 30GB", "product_1_category": "plan",
        "product_1_context": "agent_offer", "product_1_phase": "upsell",
        "product_1_first_mentioned": "00:00:56", "product_1_outcome": "upsell_accepted",
        "product_2_name": "Unlimited", "product_2_category": "plan",
        "product_2_context": "agent_offer", "product_2_phase": "upsell",
        "product_2_first_mentioned": "00:00:56", "product_2_outcome": "information_provided",
        "product_3_name": "Flex 20GB", "product_3_category": "plan",
        "product_3_context": "agent_offer", "product_3_phase": "upsell",
        "product_3_first_mentioned": "00:00:56", "product_3_outcome": "not_pursued",
        "product_4_name": None, "product_4_category": None, "product_4_context": None,
        "product_4_phase": None, "product_4_first_mentioned": None, "product_4_outcome": None,
        "product_5_name": None, "product_5_category": None, "product_5_context": None,
        "product_5_phase": None, "product_5_first_mentioned": None, "product_5_outcome": None,
        "upsell_attempted": True,
        "upsell_offer_details": "Upgrade from Basic 10GB ($35) to Smart 30GB ($55) — 3x data with rollover",
        "upsell_relevant_to_eligibility": True,
        "upsell_scripted_or_personalized": "personalized",
        "upsell_outcome": "accepted",
        "agent_skill_rating": "proficient",
        "agent_skill_rating_rationale": "Agent used actual usage history to personalise the recommendation, correctly identified Smart 30GB as the sweet spot, and efficiently processed the upgrade",
        "agent_tool_struggle_detected": False, "agent_tool_struggle_evidence": None,
        "agent_used_correct_troubleshooting_path": True,
        "agent_disproportionate_time_phase": "none",
        "agent_disproportionate_time_rationale": None,
        "agent_empathy_statements_count": 2,
        "agent_followed_compliance_script": True,
        "customer_sentiment_start": "neutral",
        "customer_sentiment_end": "positive",
        "customer_sentiment_improved": True,
        "customer_expressed_dissatisfaction": False,
        "customer_dissatisfaction_reason": None,
        "primary_issue_resolved": True, "all_issues_resolved": True,
        "fcr_indicator": True, "escalation_required": False,
        "escalation_reason": None, "repeat_call_risk": "low",
        "repeat_call_risk_reason": "Issue resolved by plan upgrade; data usage will be accommodated by new plan",
        "could_be_self_served": True, "self_serve_channel_applicable": "app",
        "self_serve_deflection_rationale": "Plan comparison and self-upgrade is available in the customer app; customer could have discovered and switched without calling",
        "proactive_outreach_applicable": False,
        "proactive_outreach_trigger": None,
        "agentic_ai_resolvable": True,
        "agentic_ai_resolvable_rationale": "Plan upgrade recommendation based on usage patterns is a deterministic, data-driven decision that an AI agent could make and execute autonomously",
        "primary_cost_driver": "plan_change", "avoidable_call": True,
        "avoidable_call_reason": "Customer could have compared plans and upgraded via the mobile app; proactive in-app notification when nearing data cap 3 months in a row could have prompted self-serve upgrade",
        "vendor_tool_used": None, "handle_time_efficiency": "efficient",
        "call_summary": "Customer on Basic 10GB plan called to upgrade after hitting the data cap 3 of 4 months. Agent reviewed usage history, recommended Smart 30GB at $55/month, and processed the upgrade immediately. Upsell accepted; customer satisfied.",
        "key_observations": "Customer hit 10GB cap 3 of last 4 months — clear signal for proactive plan nudge|Smart 30GB upsell accepted — $20/month revenue increase|Call avoidable via in-app plan upgrade with data cap alert|AI agent could automate usage-triggered plan recommendations|Agent used usage data to personalise recommendation — best practice",
        "_cot_reasoning": "The customer called proactively to upgrade their data plan after repeatedly hitting the 10GB cap. The agent correctly reviewed actual usage history to identify the appropriate plan (Smart 30GB), highlighted the rollover feature as a relevant differentiator, and processed the upgrade efficiently. The customer's sentiment was neutral at the start and positive by the end after finding a clear solution.",
    },
}


def _detect_mock(transcript_text: str) -> str | None:
    """Return mock key if transcript matches a known sample, else None."""
    text = transcript_text.lower()
    if "canadian border" in text or "4872-9301" in text or "285" in text:
        return "billing"
    if "sw1a" in text or "555-0147" in text or "mobile data has been completely dead" in text:
        return "technical"
    if "555-0289" in text or "smart 30gb" in text or "basic 10gb" in text:
        return "plan"
    return None


def _make_mock_response(key: str, call_id: str, t0: float) -> dict:
    result = dict(_MOCK[key])
    result["call_id"] = call_id
    result["call_date"] = time.strftime("%Y-%m-%d")
    qa = score_field_coverage(result)
    return {
        "call_id": call_id,
        "extraction": result,
        "qa_score": qa,
        "provider": "Claude Haiku (demo)",
        "processing_time_seconds": round(time.monotonic() - t0, 2),
        "demo_mode": True,
    }


# ── FastAPI app ────────────────────────────────────────────────────

app = FastAPI(title="cci.ai — Care Cost Intelligence", version="1.0.0", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    transcript: str = Field(..., min_length=10, max_length=50_000)
    call_id: str | None = Field(default=None, max_length=64)


@app.get("/")
def serve_demo() -> FileResponse:
    return FileResponse(_DEMO_DIR / "index.html", media_type="text/html")


@app.get("/architecture")
def serve_architecture() -> FileResponse:
    return FileResponse(_DEMO_DIR / "architecture.html", media_type="text/html")


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "provider": _provider,
        "ready": _client is not None or _MOCK_ONLY,
        "mock_only": _MOCK_ONLY,
    })


@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> JSONResponse:
    t0 = time.monotonic()
    call_id = req.call_id or str(uuid.uuid4())
    transcript_text = req.transcript

    # Try real extraction if client is available
    if _client is not None and not _MOCK_ONLY:
        transcript_dict: dict = {
            "call_id": call_id,
            "transcript_text": transcript_text,
            "call_date": time.strftime("%Y-%m-%d"),
        }
        try:
            transcript_dict = INPUT_SANITIZER.sanitize_transcript(transcript_dict)
        except ValueError:
            pass  # fall through to mock

        result = analyze_transcript(_client, _get_prompt(), transcript_dict)
        if result is not None:
            qa = score_field_coverage(result)
            result = OUTPUT_SANITIZER.sanitize_extraction_result(result)
            for key in (
                "_prompt_tokens", "_completion_tokens", "_total_tokens",
                "_cache_creation_tokens", "_cache_read_tokens",
            ):
                result.pop(key, None)
            return JSONResponse({
                "call_id": call_id,
                "extraction": result,
                "qa_score": qa,
                "provider": _provider,
                "processing_time_seconds": round(time.monotonic() - t0, 2),
            })

    # Fallback: detect which sample and return pre-computed mock
    mock_key = _detect_mock(transcript_text)
    if mock_key:
        return JSONResponse(_make_mock_response(mock_key, call_id, t0))

    # Custom transcript with no API — return informative error
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": "Live extraction unavailable (check ANTHROPIC_API_KEY and API credits). "
                      "Use the Load Sample button to run demo with pre-computed results.",
        },
    )
