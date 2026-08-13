"""
pipeline/llm_clients.py  —  Centralized LLM Client Construction
-------------------------------------------------------------------
Single seam for constructing provider SDK clients. Before this module
existed, analyzer.py, agents/extraction_agent.py, agents/insights_agent.py,
and vector_memory.py each built their own anthropic.Anthropic()/
google.genai.Client()/openai.OpenAI() independently — meaning the
timeout=/max_retries=1 policy (see config.py's EXTRACTION_API_TIMEOUT_S
comment on why both matter) had to be re-applied correctly at four
separate call sites instead of one.

Each getter raises OSError if its API key env var is unset. Callers that
want a silent fallback instead of a raised error (e.g. InsightsAgent's
NVIDIA → Claude → rule-based chain) catch OSError themselves — this
module doesn't guess at per-caller fallback semantics.
"""

from __future__ import annotations

import os
from typing import Any

from pipeline.config import NVIDIA_BASE_URL


def get_anthropic_client(timeout_s: float) -> Any:
    """
    Construct an Anthropic client. max_retries=1 (not the SDK default of 2):
    callers already retry with their own backoff, and the two layers
    compounding is what let a single stuck provider approach the
    orchestrator's 600s subprocess timeout — see config.py.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise OSError("ANTHROPIC_API_KEY not set. Check your .env file.")
    import anthropic

    return anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=1)


def get_gemini_client(timeout_s: float) -> Any:
    """Construct a Gemini client (google-genai SDK)."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise OSError("GEMINI_API_KEY not set. Check your .env file.")
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=timeout_s * 1000),
    )


def get_nvidia_client(timeout_s: float) -> Any:
    """
    Construct an NVIDIA NIM client (OpenAI-compatible endpoint).
    max_retries=1: with a 3-tier fallback (NVIDIA -> Claude -> rule-based)
    already providing resilience, SDK-level retries just compound the
    worst-case hang time instead of adding real robustness.
    """
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise OSError("NVIDIA_API_KEY not set. Check your .env file.")
    from openai import OpenAI

    return OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key, timeout=timeout_s, max_retries=1)
