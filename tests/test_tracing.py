"""
Tests for pipeline/tracing.py — the Langfuse observability seam.

Covers the disabled (no-op) path that every other test in this suite runs
through implicitly, the deterministic trace_id derivation used to join a
ReAct gap-fill retry to its original extraction trace, and the
_mask_otel_spans redaction logic — including a regression test for the bug
where scope-name filtering silently let full call transcripts through
unredacted (fixed by redacting long string attributes on every span,
regardless of which instrumentation library produced it).

No real network calls and no real Anthropic/Gemini SDK patching: Langfuse,
AnthropicInstrumentor, and GoogleGenAIInstrumentor are all faked, since the
real instrumentors monkeypatch the shared, process-global anthropic/
google-genai SDK classes that other test files (test_llm_clients.py,
test_analyzer.py) construct real clients from.
"""

from contextlib import contextmanager

import pytest
from langfuse.types import MaskOtelSpansParams, OtelSpanIdentifier

from pipeline import tracing


@pytest.fixture(autouse=True)
def _restore_client():
    """tracing._client is a module-level global mutated by configure() and
    by tests that stub it directly — restore it after every test so state
    never leaks between tests in this file or into the rest of the suite."""
    original = tracing._client
    yield
    tracing._client = original


# ── Disabled (default) path ─────────────────────────────────────────────


class TestNoopObservation:
    def test_update_accepts_any_kwargs_and_returns_self(self):
        obs = tracing._NoopObservation()
        result = obs.update(output={"a": 1}, anything="ignored")
        assert result is obs


class TestDisabledPath:
    def test_get_client_is_none(self, monkeypatch):
        monkeypatch.setattr(tracing, "_client", None)
        assert tracing.get_client() is None

    def test_call_trace_id_is_none(self, monkeypatch):
        monkeypatch.setattr(tracing, "_client", None)
        assert tracing.call_trace_id("call-123") is None

    def test_flush_does_not_raise(self, monkeypatch):
        monkeypatch.setattr(tracing, "_client", None)
        tracing.flush()

    def test_traced_span_yields_noop_observation(self, monkeypatch):
        monkeypatch.setattr(tracing, "_client", None)
        with tracing.traced_span("extract-transcript", input={"x": 1}) as span:
            assert isinstance(span, tracing._NoopObservation)
            span.update(output={"y": 2})  # must not raise


# ── Enabled path: call_trace_id() and traced_span() ─────────────────────


class _FakeObservation:
    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.updates: list[dict] = []

    def update(self, **kwargs):
        self.updates.append(kwargs)


class _FakeLangfuseClient:
    def __init__(self):
        self.flushed = False
        self.observations: list[_FakeObservation] = []

    def create_trace_id(self, seed):
        return f"trace-id-for-{seed}"

    def flush(self):
        self.flushed = True

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        obs = _FakeObservation(kwargs)
        self.observations.append(obs)
        yield obs


@pytest.fixture
def fake_client(monkeypatch):
    client = _FakeLangfuseClient()
    monkeypatch.setattr(tracing, "_client", client)
    return client


@pytest.fixture
def fake_propagate_attributes(monkeypatch):
    """Stub langfuse.propagate_attributes — traced_span() imports it locally
    (`from langfuse import propagate_attributes`), so patching the real
    langfuse module's attribute is what call sites actually see."""
    calls: list[dict] = []

    @contextmanager
    def _fake(**kwargs):
        calls.append(kwargs)
        yield

    import langfuse

    monkeypatch.setattr(langfuse, "propagate_attributes", _fake)
    return calls


class TestCallTraceId:
    def test_deterministic_per_call_id(self, fake_client):
        assert tracing.call_trace_id("abc") == tracing.call_trace_id("abc")

    def test_delegates_to_client_create_trace_id(self, fake_client):
        assert tracing.call_trace_id("abc") == "trace-id-for-abc"

    def test_different_call_ids_differ(self, fake_client):
        assert tracing.call_trace_id("abc") != tracing.call_trace_id("xyz")


class TestTracedSpanEnabled:
    def test_opens_observation_with_name_and_input(self, fake_client, fake_propagate_attributes):
        with tracing.traced_span("extract-transcript", input={"call_date": "2026-01-01"}) as span:
            span.update(output={"ok": True})

        assert len(fake_client.observations) == 1
        obs = fake_client.observations[0]
        assert obs.kwargs["name"] == "extract-transcript"
        assert obs.kwargs["as_type"] == "span"
        assert obs.kwargs["input"] == {"call_date": "2026-01-01"}
        assert obs.updates == [{"output": {"ok": True}}]

    def test_trace_id_sets_trace_context(self, fake_client, fake_propagate_attributes):
        with tracing.traced_span("gap-fill-transcript", trace_id="deadbeef"):
            pass
        obs = fake_client.observations[0]
        assert obs.kwargs["trace_context"] == {"trace_id": "deadbeef"}

    def test_no_trace_id_omits_trace_context(self, fake_client, fake_propagate_attributes):
        with tracing.traced_span("extract-transcript"):
            pass
        obs = fake_client.observations[0]
        assert "trace_context" not in obs.kwargs

    def test_as_type_passthrough(self, fake_client, fake_propagate_attributes):
        with tracing.traced_span("some-generation", as_type="generation"):
            pass
        assert fake_client.observations[0].kwargs["as_type"] == "generation"

    def test_propagates_session_id_tags_and_metadata(self, fake_client, fake_propagate_attributes):
        with tracing.traced_span(
            "generate-insights",
            session_id="offset0_n3_seed42",
            tags=["insights", "analyze"],
            metadata={"n_calls": 3},
        ):
            pass
        assert fake_propagate_attributes == [
            {
                "session_id": "offset0_n3_seed42",
                "tags": ["insights", "analyze"],
                "metadata": {"n_calls": 3},
            }
        ]

    def test_unset_attributes_pass_through_as_none(self, fake_client, fake_propagate_attributes):
        # session_id/tags/metadata all default to None in the real
        # propagate_attributes(), so passing None through when a call site
        # doesn't set them is equivalent to omitting them entirely.
        with tracing.traced_span("extract-transcript"):
            pass
        assert fake_propagate_attributes == [{"session_id": None, "tags": None, "metadata": None}]


class TestFlushEnabled:
    def test_flush_delegates_to_client(self, fake_client):
        tracing.flush()
        assert fake_client.flushed is True


# ── _mask_otel_spans: transcript-redaction regression tests ─────────────


class _FakeSpan:
    def __init__(self, attributes, instrumentation_scope_name="some.other.library"):
        self.attributes = attributes
        self.instrumentation_scope_name = instrumentation_scope_name


def _params(spans: dict) -> MaskOtelSpansParams:
    return MaskOtelSpansParams(spans=spans)


class TestMaskOtelSpans:
    def test_long_string_attribute_is_redacted(self):
        ident = OtelSpanIdentifier(trace_id="t1", span_id="s1")
        transcript = "X" * 10_000
        span = _FakeSpan({"gen_ai.prompt.1.content": transcript})

        result = tracing._mask_otel_spans(params=_params({ident: span}))

        assert result is not None
        patch = result.span_patches[ident]
        redacted = patch.set_attributes["gen_ai.prompt.1.content"]
        assert "10000 chars" in redacted
        assert transcript not in redacted

    def test_short_string_attribute_is_untouched(self):
        ident = OtelSpanIdentifier(trace_id="t1", span_id="s1")
        span = _FakeSpan({"channel": "voice"})

        result = tracing._mask_otel_spans(params=_params({ident: span}))

        assert result is None

    def test_non_string_attributes_are_never_redacted(self):
        ident = OtelSpanIdentifier(trace_id="t1", span_id="s1")
        span = _FakeSpan(
            {
                "gen_ai.request.max_tokens": 8192,
                "gen_ai.request.temperature": 0.1,
                "some_flag": True,
                "big_list": list(range(10_000)),  # long, but not a string
            }
        )

        result = tracing._mask_otel_spans(params=_params({ident: span}))

        assert result is None

    def test_redaction_is_not_scoped_to_a_specific_instrumentation_library(self):
        """
        Regression test: the original bug filtered on
        `instrumentation_scope_name in {"anthropic", "google_genai"}`, but
        the real scope names are "opentelemetry.instrumentation.anthropic"
        and "openinference.instrumentation.google_genai" — the filter never
        matched, and full call transcripts were exported unredacted. Any
        long string, on any span, from any scope, must now be redacted.
        """
        long_value = "Y" * 1000
        spans = {
            OtelSpanIdentifier(trace_id="t1", span_id="s1"): _FakeSpan(
                {"content": long_value},
                instrumentation_scope_name="opentelemetry.instrumentation.anthropic",
            ),
            OtelSpanIdentifier(trace_id="t2", span_id="s2"): _FakeSpan(
                {"content": long_value},
                instrumentation_scope_name="openinference.instrumentation.google_genai",
            ),
            OtelSpanIdentifier(trace_id="t3", span_id="s3"): _FakeSpan(
                {"content": long_value}, instrumentation_scope_name="totally.unrelated.library"
            ),
        }

        result = tracing._mask_otel_spans(params=_params(spans))

        assert result is not None
        assert len(result.span_patches) == 3
        for patch in result.span_patches.values():
            assert long_value not in patch.set_attributes["content"]

    def test_only_offending_spans_are_patched_in_a_mixed_batch(self):
        clean_ident = OtelSpanIdentifier(trace_id="t1", span_id="s1")
        dirty_ident = OtelSpanIdentifier(trace_id="t2", span_id="s2")
        spans = {
            clean_ident: _FakeSpan({"call_id": "abc123"}),
            dirty_ident: _FakeSpan({"content": "Z" * 600}),
        }

        result = tracing._mask_otel_spans(params=_params(spans))

        assert result is not None
        assert set(result.span_patches.keys()) == {dirty_ident}

    def test_no_spans_returns_none(self):
        result = tracing._mask_otel_spans(params=_params({}))
        assert result is None

    def test_boundary_length_is_not_redacted(self):
        """A string of exactly the threshold length is not redacted —
        only strings strictly longer than it are."""
        ident = OtelSpanIdentifier(trace_id="t1", span_id="s1")
        span = _FakeSpan({"field": "A" * tracing._REDACT_THRESHOLD_CHARS})

        result = tracing._mask_otel_spans(params=_params({ident: span}))

        assert result is None


# ── configure(): wiring, without touching real SDKs or the network ──────


class _FakeInstrumentor:
    instances: list["_FakeInstrumentor"] = []

    def __init__(self):
        self.instrumented = False
        _FakeInstrumentor.instances.append(self)

    def instrument(self):
        self.instrumented = True


@pytest.fixture(autouse=True)
def _reset_fake_instrumentor_instances():
    _FakeInstrumentor.instances = []
    yield
    _FakeInstrumentor.instances = []


class TestConfigure:
    def test_disabled_when_keys_missing(self, monkeypatch):
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        monkeypatch.setattr(tracing, "TRACING_ENABLED", False)
        monkeypatch.setattr(tracing, "_client", None)

        tracing.configure()

        assert tracing.get_client() is None

    def test_enabled_constructs_client_and_instruments_both_providers(self, monkeypatch):
        monkeypatch.setattr(tracing, "TRACING_ENABLED", True)
        monkeypatch.setattr(tracing, "_client", None)

        fake_client = _FakeLangfuseClient()
        captured_kwargs = {}

        def _fake_langfuse_ctor(**kwargs):
            captured_kwargs.update(kwargs)
            return fake_client

        import langfuse
        import openinference.instrumentation.google_genai as ggi_mod
        import opentelemetry.instrumentation.anthropic as anthropic_mod

        monkeypatch.setattr(langfuse, "Langfuse", _fake_langfuse_ctor)
        monkeypatch.setattr(anthropic_mod, "AnthropicInstrumentor", _FakeInstrumentor)
        monkeypatch.setattr(ggi_mod, "GoogleGenAIInstrumentor", _FakeInstrumentor)

        tracing.configure()

        assert tracing.get_client() is fake_client
        assert captured_kwargs["mask_otel_spans"] is tracing._mask_otel_spans
        assert len(_FakeInstrumentor.instances) == 2
        assert all(inst.instrumented for inst in _FakeInstrumentor.instances)

    def test_missing_anthropic_instrumentor_package_logs_and_continues(self, monkeypatch):
        monkeypatch.setattr(tracing, "TRACING_ENABLED", True)
        monkeypatch.setattr(tracing, "_client", None)

        import langfuse

        monkeypatch.setattr(langfuse, "Langfuse", lambda **kwargs: _FakeLangfuseClient())
        monkeypatch.setitem(
            __import__("sys").modules, "opentelemetry.instrumentation.anthropic", None
        )

        tracing.configure()  # must not raise even though the import fails

        assert tracing.get_client() is not None

    def test_missing_google_genai_instrumentor_package_logs_and_continues(self, monkeypatch):
        monkeypatch.setattr(tracing, "TRACING_ENABLED", True)
        monkeypatch.setattr(tracing, "_client", None)

        import langfuse

        monkeypatch.setattr(langfuse, "Langfuse", lambda **kwargs: _FakeLangfuseClient())
        monkeypatch.setitem(
            __import__("sys").modules, "openinference.instrumentation.google_genai", None
        )

        tracing.configure()  # must not raise even though the import fails

        assert tracing.get_client() is not None
