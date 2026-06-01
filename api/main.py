"""
api/main.py
-----------
FastAPI wrapper for the Telecom Call Intelligence pipeline.

Endpoints:
  GET  /health    — liveness + model configuration
  GET  /summary   — latest aggregated KPIs from outputs/summary.json
  POST /analyze   — extract structured metadata from a single transcript

Run:
  uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

The /analyze endpoint calls analyze_transcript() directly — no LangGraph
orchestration — so it avoids the full batch pipeline overhead for one-shot use.
"""

import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

load_dotenv()

from pipeline.analyzer import _USE_CLAUDE, analyze_transcript, load_system_prompt
from pipeline.config import (
    EXTRACTION_MODEL,
    MAX_OUTPUT_TOKENS,
    EXTRACTION_TEMPERATURE,
    OUTPUT_DIR,
)
from pipeline.security import INPUT_SANITIZER, OUTPUT_SANITIZER

# Initialise the correct LLM client based on EXTRACTION_MODEL.
# Changing EXTRACTION_MODEL in config.py automatically switches the API client here.
_extraction_client = None
_client_provider   = "unknown"

if _USE_CLAUDE:
    try:
        import anthropic
        _extraction_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
        _client_provider   = "Anthropic (Claude)"
    except Exception:
        _extraction_client = None
else:
    try:
        from google import genai
        _extraction_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
        _client_provider   = "Google AI Studio"
    except Exception:
        _extraction_client = None

_system_prompt: str | None = None
_start_time = time.time()

app = FastAPI(
    title="Telecom Call Intelligence API",
    version="1.0.0",
    description="Structured metadata extraction from telecom call transcripts.",
    docs_url="/docs",
    redoc_url=None,
)


def _get_system_prompt() -> str:
    global _system_prompt
    if _system_prompt is None:
        _system_prompt = load_system_prompt()
    return _system_prompt


# ── Request / response models ──────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    transcript: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="Raw call transcript text (timestamped conversation).",
    )
    call_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional call identifier. Auto-generated UUID if omitted.",
    )
    agent_id: str | None = Field(default=None, max_length=64)
    customer_id: str | None = Field(default=None, max_length=64)
    call_date: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Call date in YYYY-MM-DD format.",
    )
    queue_name: str | None = Field(default=None, max_length=128)
    channel: str | None = Field(default=None, pattern=r"^(voice|chat)$")


class AnalyzeResponse(BaseModel):
    request_id: str
    call_id: str
    extraction: dict
    processing_time_seconds: float


class SummaryResponse(BaseModel):
    meta: dict
    kpis: dict
    phase_avg_seconds: dict
    distributions: dict
    cost_levers: dict | None = None


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float
    model: str
    provider: str
    max_output_tokens: int
    client_ready: bool
    summary_available: bool


# ── Route: health ──────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Operations"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        uptime_seconds=round(time.time() - _start_time, 1),
        model=EXTRACTION_MODEL,
        provider=_client_provider,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        client_ready=_extraction_client is not None,
        summary_available=Path(OUTPUT_DIR / "summary.json").exists(),
    )


# ── Route: summary ─────────────────────────────────────────────────────

@app.get("/summary", response_model=SummaryResponse, tags=["Analytics"])
def summary() -> JSONResponse:
    path = Path(OUTPUT_DIR / "summary.json")
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No summary found. Run the pipeline first: python run_pipeline.py",
        )
    import json
    with open(path) as f:
        data = json.load(f)
    return JSONResponse(content=data)


# ── Route: analyze ─────────────────────────────────────────────────────

@app.post("/analyze", response_model=AnalyzeResponse, tags=["Extraction"])
def analyze(req: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    if _extraction_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM client unavailable. Check {'ANTHROPIC_API_KEY' if _USE_CLAUDE else 'GEMINI_API_KEY'} in your environment.",
        )

    t0 = time.monotonic()
    call_id = req.call_id or str(uuid.uuid4())

    transcript_dict: dict = {"call_id": call_id, "transcript_text": req.transcript}
    for opt in ("agent_id", "customer_id", "call_date", "queue_name", "channel"):
        val = getattr(req, opt)
        if val is not None:
            transcript_dict[opt] = val

    try:
        transcript_dict = INPUT_SANITIZER.sanitize_transcript(transcript_dict)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    system_prompt = _get_system_prompt()

    result = analyze_transcript(_extraction_client, system_prompt, transcript_dict)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Extraction failed after retries. Check {_client_provider} quota or transcript validity.",
        )

    result = OUTPUT_SANITIZER.sanitize_extraction_result(result)

    # Strip internal token-accounting keys from the public response
    for key in ("_prompt_tokens", "_completion_tokens", "_total_tokens"):
        result.pop(key, None)

    return AnalyzeResponse(
        request_id=str(uuid.uuid4()),
        call_id=call_id,
        extraction=result,
        processing_time_seconds=round(time.monotonic() - t0, 3),
    )


# ── Global error handler ───────────────────────────────────────────────

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error. Check server logs."},
    )
