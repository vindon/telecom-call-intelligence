"""
pipeline/tracing.py  —  Centralized Langfuse Observability
-------------------------------------------------------------
Single seam for LLM tracing — mirrors llm_clients.py's role for client
construction and token_tracker.py's role for cost accounting.

Enabled only when LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set;
every helper below is a safe no-op otherwise, so the pipeline behaves
identically without a Langfuse account — same optional-dependency pattern
already used for NVIDIA_API_KEY in llm_clients.py.

Setup ordering
--------------
`configure()` must run before `pipeline.graph` is imported (see
run_pipeline.py). It activates OpenTelemetry auto-instrumentation for
Anthropic and Gemini, which patches those SDK classes; analyzer.py imports
`google.genai` at module level as soon as `pipeline.graph` is imported, so
configuring after that import risks missing the patch window.

Claude and Gemini need no call-site changes at all: AnthropicInstrumentor
and GoogleGenAIInstrumentor patch `anthropic.Anthropic` / `google.genai.Client`
directly, so every `client.messages.create()` / `client.models.generate_content()`
call in analyzer.py and insights_agent.py is captured automatically as a
`generation`, nested under whatever Langfuse span is active. NVIDIA NIM
(OpenAI-compatible) is covered the same way, but via Langfuse's own OpenAI
SDK wrapper instead of an OTel instrumentor — see llm_clients.get_nvidia_client().

Trace scope
-----------
One trace per transcript (`call_id`), covering the initial extraction *and*
any later ReAct gap-fill retry. The gap-fill pass runs as a separate loop
after every transcript's first-pass extraction has already completed (see
extraction_agent.py::_react_loop), so the two calls don't share a Python
call stack / OTel context. `call_trace_id()` derives a deterministic
trace_id from call_id so both calls land in the same trace instead of the
retry opening a second, disconnected one — see "Trace IDs & Distributed
Tracing" in the Langfuse docs.

Data handling
-------------
Anthropic/Gemini auto-instrumentation captures the full LLM request and
response bodies, which include the raw call transcript — the same content
InputSanitizer/PIIScanner treat as sensitive elsewhere in this pipeline
(pipeline/security.py). `_mask_otel_spans` redacts any long string
attribute on those spans before export, and every span this module opens
manually is given a hand-picked, transcript-free input/output (see call
sites in analyzer.py and insights_agent.py) rather than the full function
arguments — the same "don't let @observe capture full state" caution the
Langfuse instrumentation guide itself calls out as a common mistake.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pipeline.logger import get_logger

log = get_logger(__name__)

TRACING_ENABLED = bool(os.environ.get("LANGFUSE_PUBLIC_KEY")) and bool(
    os.environ.get("LANGFUSE_SECRET_KEY")
)

# Anything longer than this on ANY exported span is assumed to be transcript
# content, not a short structured field, and is redacted before Langfuse
# ever receives it. Deliberately not scoped to a specific instrumentation
# library's `instrumentation_scope_name` (e.g. "opentelemetry.instrumentation.
# anthropic", "openinference.instrumentation.google_genai") — matching that
# exactly is brittle against library version changes and got this wrong once
# already; every span this pipeline emits is either one of ours (small,
# structured, well under this threshold by construction — see analyzer.py/
# insights_agent.py) or an auto-instrumented LLM call whose raw prompt/
# response is exactly what must never leave the process unredacted.
_REDACT_THRESHOLD_CHARS = 500

_client: Any = None


def _mask_otel_spans(*, params: Any) -> Any:
    """mask_otel_spans hook (see pipeline/tracing.py module docstring):
    redact long string attributes on every exported span so raw call
    transcripts never leave the process."""
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    patches = {}
    for identifier, span in params.spans.items():
        redacted = {
            key: f"[redacted — {len(value)} chars of transcript content masked]"
            for key, value in span.attributes.items()
            if isinstance(value, str) and len(value) > _REDACT_THRESHOLD_CHARS
        }
        if redacted:
            patches[identifier] = OtelSpanPatch(set_attributes=redacted)
    return MaskOtelSpansResult(span_patches=patches) if patches else None


def configure() -> None:
    """
    Activate Langfuse tracing. Call once, at process startup, before
    `pipeline.graph` is imported. No-op if LANGFUSE_PUBLIC_KEY /
    LANGFUSE_SECRET_KEY are unset.
    """
    global _client
    if not TRACING_ENABLED:
        log.info(
            "[Tracing] Langfuse disabled — set LANGFUSE_PUBLIC_KEY / "
            "LANGFUSE_SECRET_KEY to enable (see .env.example)"
        )
        return

    from langfuse import Langfuse

    _client = Langfuse(mask_otel_spans=_mask_otel_spans)

    try:
        from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

        AnthropicInstrumentor().instrument()
    except ImportError:
        log.warning(
            "[Tracing] opentelemetry-instrumentation-anthropic not installed "
            "— Claude calls will not be traced (pip install -r requirements.txt)"
        )

    try:
        from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

        GoogleGenAIInstrumentor().instrument()
    except ImportError:
        log.warning(
            "[Tracing] openinference-instrumentation-google-genai not installed "
            "— Gemini calls will not be traced (pip install -r requirements.txt)"
        )

    host = os.environ.get("LANGFUSE_HOST") or os.environ.get(
        "LANGFUSE_BASE_URL", "https://cloud.langfuse.com"
    )
    log.info("[Tracing] Langfuse active — host=%s", host)


def get_client() -> Any:
    """Return the configured Langfuse client, or None if tracing is disabled."""
    return _client


def call_trace_id(call_id: str) -> str | None:
    """Deterministic trace_id for `call_id` — lets the initial extraction and
    a later ReAct gap-fill retry share one trace. None when tracing is
    disabled."""
    if _client is None:
        return None
    return _client.create_trace_id(seed=call_id)


class _NoopObservation:
    """Yielded by traced_span() when tracing is disabled — absorbs
    `.update()` so call sites don't need to branch on TRACING_ENABLED."""

    def update(self, **_kwargs: Any) -> _NoopObservation:
        return self


@contextmanager
def traced_span(
    name: str,
    *,
    as_type: str = "span",
    input: Any = None,
    trace_id: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> Iterator[Any]:
    """
    Open a Langfuse observation as the current span (or a no-op if tracing
    is disabled). Any Anthropic/Gemini/NVIDIA call made inside this block is
    automatically captured as a nested `generation` via OTel context
    propagation — see the module docstring and configure().

    Callers set the result on the yielded object once known:
        with traced_span("extract-transcript", ...) as span:
            ...
            span.update(output=safe_summary)
    """
    if _client is None:
        yield _NoopObservation()
        return

    from langfuse import propagate_attributes

    span_kwargs: dict[str, Any] = {"as_type": as_type, "name": name, "input": input}
    if trace_id is not None:
        span_kwargs["trace_context"] = {"trace_id": trace_id}

    # session_id/tags/metadata all default to None in propagate_attributes()
    # itself, so passing them through unfiltered is equivalent to omitting
    # whichever ones this call didn't set.
    with propagate_attributes(session_id=session_id, tags=tags, metadata=metadata):
        with _client.start_as_current_observation(**span_kwargs) as obs:
            yield obs


def flush() -> None:
    """
    Flush buffered traces before process exit. Required in this pipeline's
    short-lived per-batch subprocesses — an unflushed Langfuse client in a
    script that exits immediately after the last LLM call can drop the final
    batch of traces (see the Langfuse instrumentation guide's "No flush() in
    scripts" pitfall).
    """
    if _client is not None:
        _client.flush()
