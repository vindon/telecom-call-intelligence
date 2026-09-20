"""
Tests for pipeline/analyzer.py — JSON parsing, prompt building, checkpoint
I/O, field-coverage scoring, retry behaviour, and the ReAct gap-fill merge.
All LLM calls are stubbed; no network access.
"""

import json

import pytest

import pipeline.analyzer as analyzer
from pipeline.analyzer import (
    _CRITICAL_FIELDS,
    _build_gap_fill_message,
    _build_user_message,
    _call_gemini,
    _call_model,
    _is_missing,
    _parse_json_text,
    analyze_transcript,
    checkpoint_path,
    gap_fill_transcript,
    load_checkpoint,
    score_field_coverage,
)
from pipeline.circuit_breaker import CircuitBreaker


@pytest.fixture(autouse=True)
def isolate_analyzer(tmp_path, monkeypatch):
    """Redirect checkpoint/sentinel I/O to a temp dir and reset the quota breaker."""
    monkeypatch.setattr(analyzer, "CHECKPOINT_DIR", tmp_path)
    monkeypatch.setattr(
        analyzer, "_gemini_quota_breaker", CircuitBreaker(tmp_path / ".react_quota_exhausted")
    )
    monkeypatch.setattr(analyzer.time, "sleep", lambda s: None)


# ── JSON parsing ──────────────────────────────────────────────────────


class TestParseJsonText:
    def test_plain_json(self):
        assert _parse_json_text('{"a": 1}') == {"a": 1}

    def test_strips_json_fence(self):
        assert _parse_json_text('```json\n{"a": 1}\n```') == {"a": 1}

    def test_strips_bare_fence(self):
        assert _parse_json_text('```\n{"a": 1}\n```') == {"a": 1}

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_json_text("not json")


# ── Prompt builders ───────────────────────────────────────────────────


class TestPromptBuilders:
    def test_user_message_contains_metadata_and_transcript(self, make_transcript):
        t = make_transcript(call_id="conv-42")
        msg = _build_user_message(t)
        assert "Call ID: conv-42" in msg
        assert t["transcript_text"] in msg
        assert "_cot_reasoning" in msg  # CoT contract with the system prompt

    def test_gap_fill_message_lists_only_missing_fields(self, make_transcript):
        msg = _build_gap_fill_message(make_transcript(), ["fcr_indicator", "issue_1_category"])
        assert "`fcr_indicator`" in msg
        assert "`issue_1_category`" in msg
        assert "ONLY" in msg

    def test_gap_fill_message_truncates_long_transcripts(self, make_transcript):
        t = make_transcript(transcript_text="x" * 20_000)
        msg = _build_gap_fill_message(t, ["fcr_indicator"])
        assert len(msg) < 10_000


# ── Field coverage (ReAct Observe step) ───────────────────────────────


class TestScoreFieldCoverage:
    def test_empty_result_scores_zero(self):
        assert score_field_coverage({}) == 0
        assert score_field_coverage(None) == 0

    def test_all_critical_fields_present_scores_100(self, make_record):
        assert score_field_coverage(make_record()) == 100

    def test_false_and_zero_count_as_present(self):
        # Regression: v4.1.0 fixed False==0 being treated as missing
        result = {f: False for f in _CRITICAL_FIELDS}
        result["total_duration_seconds"] = 0
        assert score_field_coverage(result) == 100

    def test_null_and_empty_string_count_as_missing(self):
        assert _is_missing(None) is True
        assert _is_missing("") is True
        assert _is_missing(False) is False
        assert _is_missing(0) is False
        result = {f: None for f in _CRITICAL_FIELDS}
        assert score_field_coverage(result) == 0


# ── Checkpoint I/O ────────────────────────────────────────────────────


class TestCheckpointIO:
    def test_round_trip(self):
        analyzer._append_checkpoint("key1", {"call_id": "a", "x": 1})
        analyzer._append_checkpoint("key1", {"call_id": "b", "x": 2})
        results, done_ids = load_checkpoint("key1")
        assert len(results) == 2
        assert done_ids == {"a", "b"}

    def test_missing_checkpoint_returns_empty(self):
        assert load_checkpoint("nonexistent") == ([], set())

    def test_corrupt_lines_skipped(self):
        path = checkpoint_path("key2")
        path.write_text('{"call_id": "good"}\nnot-json\n\n{"call_id": "also-good"}\n')
        results, done_ids = load_checkpoint("key2")
        assert done_ids == {"good", "also-good"}
        assert len(results) == 2


# ── analyze_transcript (stubbed Claude) ───────────────────────────────


class TestAnalyzeTranscript:
    def test_success_injects_token_accounting(self, monkeypatch, make_transcript, make_record):
        payload = {k: v for k, v in make_record().items() if not k.startswith("_")}
        monkeypatch.setattr(analyzer, "_USE_CLAUDE", True)
        monkeypatch.setattr(
            analyzer,
            "_call_claude",
            lambda client, sp, msg, max_tokens: (json.dumps(payload), 1200, 800, 0, 0),
        )
        result = analyze_transcript(client=None, system_prompt="sp", transcript=make_transcript())
        assert result["_prompt_tokens"] == 1200
        assert result["_completion_tokens"] == 800
        assert result["_cache_creation_tokens"] == 0
        assert result["_cache_read_tokens"] == 0
        assert result["_total_tokens"] == 2000
        assert result["call_id"] == payload["call_id"]

    def test_success_with_cache_hit_injects_cache_accounting(
        self, monkeypatch, make_transcript, make_record
    ):
        # Regression: cache tokens must be captured, not silently dropped —
        # dropping them would undercount both total_tokens and real spend.
        payload = {k: v for k, v in make_record().items() if not k.startswith("_")}
        monkeypatch.setattr(analyzer, "_USE_CLAUDE", True)
        monkeypatch.setattr(
            analyzer,
            "_call_claude",
            lambda client, sp, msg, max_tokens: (json.dumps(payload), 600, 2145, 0, 4675),
        )
        result = analyze_transcript(client=None, system_prompt="sp", transcript=make_transcript())
        assert result["_prompt_tokens"] == 600
        assert result["_cache_creation_tokens"] == 0
        assert result["_cache_read_tokens"] == 4675
        assert result["_total_tokens"] == 600 + 2145 + 0 + 4675

    def test_persistent_json_error_returns_none(self, monkeypatch, make_transcript):
        monkeypatch.setattr(analyzer, "_USE_CLAUDE", True)
        monkeypatch.setattr(
            analyzer,
            "_call_claude",
            lambda client, sp, msg, max_tokens: ("not json at all", 10, 10, 0, 0),
        )
        assert analyze_transcript(None, "sp", make_transcript(), max_retries=2) is None

    def test_persistent_api_error_returns_none(self, monkeypatch, make_transcript):
        def boom(client, sp, msg, max_tokens):
            raise RuntimeError("connection reset")

        monkeypatch.setattr(analyzer, "_USE_CLAUDE", True)
        monkeypatch.setattr(analyzer, "_call_claude", boom)
        assert analyze_transcript(None, "sp", make_transcript(), max_retries=2) is None

    def test_gemini_success_injects_token_accounting(
        self, monkeypatch, make_transcript, make_record
    ):
        # Regression coverage for the Gemini success path — previously
        # untested (only the Gemini 429 error path had a test), which is
        # exactly the risk _call_model()'s dedup refactor needed to close.
        payload = {k: v for k, v in make_record().items() if not k.startswith("_")}
        monkeypatch.setattr(analyzer, "_USE_CLAUDE", False)
        monkeypatch.setattr(
            analyzer,
            "_call_gemini",
            lambda client, sp, msg, max_tokens: (json.dumps(payload), 500, 300, 0, 0),
        )
        result = analyze_transcript(client=None, system_prompt="sp", transcript=make_transcript())
        assert result["_prompt_tokens"] == 500
        assert result["_completion_tokens"] == 300
        assert result["_cache_creation_tokens"] == 0
        assert result["_cache_read_tokens"] == 0
        assert result["_total_tokens"] == 800
        assert result["call_id"] == payload["call_id"]


class TestCallModel:
    """_call_model() dispatches to the configured provider — see EXTRACTION_MODEL."""

    def test_dispatches_to_claude_when_use_claude(self, monkeypatch):
        monkeypatch.setattr(analyzer, "_USE_CLAUDE", True)
        monkeypatch.setattr(analyzer, "_call_claude", lambda *a: ("claude", 1, 2, 3, 4))
        monkeypatch.setattr(
            analyzer,
            "_call_gemini",
            lambda *a: (_ for _ in ()).throw(AssertionError("must not call gemini")),
        )
        assert _call_model(None, "sp", "msg", 100) == ("claude", 1, 2, 3, 4)

    def test_dispatches_to_gemini_when_not_use_claude(self, monkeypatch):
        monkeypatch.setattr(analyzer, "_USE_CLAUDE", False)
        monkeypatch.setattr(analyzer, "_call_gemini", lambda *a: ("gemini", 5, 6, 0, 0))
        monkeypatch.setattr(
            analyzer,
            "_call_claude",
            lambda *a: (_ for _ in ()).throw(AssertionError("must not call claude")),
        )
        assert _call_model(None, "sp", "msg", 100) == ("gemini", 5, 6, 0, 0)


class TestCallGemini:
    """Direct tests of the Gemini response-parsing logic extracted from the
    old inline blocks in analyze_transcript()/gap_fill_transcript()."""

    class _FakeUsageMetadata:
        def __init__(self, prompt_tokens, candidate_tokens):
            self.prompt_token_count = prompt_tokens
            self.candidates_token_count = candidate_tokens

    class _FakeResponse:
        def __init__(self, text, usage_metadata, candidates=None):
            self.text = text
            self.usage_metadata = usage_metadata
            self.candidates = candidates

    class _FakeCandidate:
        def __init__(self, finish_reason):
            self.finish_reason = finish_reason

    class _FakeGeminiClient:
        def __init__(self, response):
            self._response = response
            self.calls: list[dict] = []

        class _Models:
            def __init__(self, outer):
                self._outer = outer

            def generate_content(self, **kwargs):
                self._outer.calls.append(kwargs)
                return self._outer._response

        @property
        def models(self):
            return self._Models(self)

    def test_parses_text_and_usage(self, monkeypatch):
        monkeypatch.setattr(analyzer.GEMINI_RATE_LIMITER, "acquire", lambda: None)
        response = self._FakeResponse("hello", self._FakeUsageMetadata(120, 45))
        client = self._FakeGeminiClient(response)

        text, in_tok, out_tok, cache_create, cache_read = _call_gemini(client, "sp", "msg", 1024)

        assert text == "hello"
        assert (in_tok, out_tok) == (120, 45)
        assert (cache_create, cache_read) == (0, 0)  # Gemini has no prompt-cache equivalent
        assert client.calls[0]["contents"] == "msg"
        assert client.calls[0]["config"].max_output_tokens == 1024

    def test_missing_usage_metadata_defaults_to_zero(self, monkeypatch):
        # response.usage_metadata can be None — must not raise AttributeError.
        monkeypatch.setattr(analyzer.GEMINI_RATE_LIMITER, "acquire", lambda: None)
        response = self._FakeResponse("hello", None)
        client = self._FakeGeminiClient(response)

        _, in_tok, out_tok, _, _ = _call_gemini(client, "sp", "msg", 1024)

        assert (in_tok, out_tok) == (0, 0)

    def test_none_text_raises_clear_error_instead_of_reaching_downstream_checks(self, monkeypatch):
        # Regression: response.text is None when Gemini has no simple text
        # part (e.g. safety filtering). Previously this None flowed straight
        # into SECRET_GUARD.assert_no_secrets_in_output()/check_response_size()
        # in analyze_transcript(), which would raise a confusing
        # TypeError/AttributeError instead of a diagnosable error.
        monkeypatch.setattr(analyzer.GEMINI_RATE_LIMITER, "acquire", lambda: None)
        response = self._FakeResponse(
            None, self._FakeUsageMetadata(50, 0), candidates=[self._FakeCandidate("SAFETY")]
        )
        client = self._FakeGeminiClient(response)

        with pytest.raises(ValueError, match="SAFETY"):
            _call_gemini(client, "sp", "msg", 1024)

    def test_none_text_with_no_candidates_still_raises_clearly(self, monkeypatch):
        monkeypatch.setattr(analyzer.GEMINI_RATE_LIMITER, "acquire", lambda: None)
        response = self._FakeResponse(None, None, candidates=[])
        client = self._FakeGeminiClient(response)

        with pytest.raises(ValueError, match="no_candidates"):
            _call_gemini(client, "sp", "msg", 1024)


# ── gap_fill_transcript (ReAct Act step) ──────────────────────────────


class TestGapFillTranscript:
    def test_no_missing_fields_skips_llm_call(self, make_transcript, make_record):
        first_pass = make_record()
        # client=None would explode if any call were attempted
        assert gap_fill_transcript(None, "sp", make_transcript(), first_pass) is first_pass

    def test_quota_circuit_breaker_skips(self, monkeypatch, make_transcript, make_record):
        analyzer._gemini_quota_breaker.tripped = True
        first_pass = make_record(fcr_indicator=None)
        assert gap_fill_transcript(None, "sp", make_transcript(), first_pass) is first_pass

    def test_merge_fills_missing_and_preserves_existing(
        self, monkeypatch, make_transcript, make_record
    ):
        first_pass = make_record(fcr_indicator=None, issue_1_category=None)
        retry_payload = {
            "fcr_indicator": True,
            "issue_1_category": "technical",
            "call_summary": "should NOT overwrite the existing summary",
        }
        monkeypatch.setattr(analyzer, "_USE_CLAUDE", True)
        monkeypatch.setattr(
            analyzer,
            "_call_claude",
            lambda client, sp, msg, max_tokens: (json.dumps(retry_payload), 100, 50, 0, 0),
        )
        merged = gap_fill_transcript(None, "sp", make_transcript(), first_pass)
        assert merged["fcr_indicator"] is True
        assert merged["issue_1_category"] == "technical"
        assert merged["call_summary"] == first_pass["call_summary"]

    def test_merge_accumulates_token_spend(self, monkeypatch, make_transcript, make_record):
        # Regression: v4.1.0 fixed gap-fill tokens not counted toward BudgetGuard
        first_pass = make_record(fcr_indicator=None, _prompt_tokens=2000, _completion_tokens=1500)
        monkeypatch.setattr(analyzer, "_USE_CLAUDE", True)
        monkeypatch.setattr(
            analyzer,
            "_call_claude",
            lambda client, sp, msg, max_tokens: (
                json.dumps({"fcr_indicator": False}),
                100,
                50,
                0,
                0,
            ),
        )
        merged = gap_fill_transcript(None, "sp", make_transcript(), first_pass)
        assert merged["_prompt_tokens"] == 2100
        assert merged["_completion_tokens"] == 1550
        assert merged["_total_tokens"] == 3650

    def test_merge_accumulates_cache_tokens_too(self, monkeypatch, make_transcript, make_record):
        # Regression guard for this session's caching change: gap-fill cache
        # tokens must add onto the first pass's cache totals, not overwrite them.
        first_pass = make_record(
            fcr_indicator=None,
            _prompt_tokens=600,
            _completion_tokens=2145,
            _cache_creation_tokens=4675,
            _cache_read_tokens=0,
        )
        monkeypatch.setattr(analyzer, "_USE_CLAUDE", True)
        monkeypatch.setattr(
            analyzer,
            "_call_claude",
            lambda client, sp, msg, max_tokens: (
                json.dumps({"fcr_indicator": False}),
                100,
                50,
                0,
                4675,
            ),
        )
        merged = gap_fill_transcript(None, "sp", make_transcript(), first_pass)
        assert merged["_cache_creation_tokens"] == 4675
        assert merged["_cache_read_tokens"] == 4675
        assert merged["_total_tokens"] == 700 + 2195 + 4675 + 4675

    def test_failure_returns_first_pass_unchanged(self, monkeypatch, make_transcript, make_record):
        def boom(client, sp, msg, max_tokens):
            raise RuntimeError("some transient API failure")

        monkeypatch.setattr(analyzer, "_USE_CLAUDE", True)
        monkeypatch.setattr(analyzer, "_call_claude", boom)
        first_pass = make_record(fcr_indicator=None)
        assert gap_fill_transcript(None, "sp", make_transcript(), first_pass) is first_pass

    def test_gemini_429_writes_quota_sentinel(self, monkeypatch, make_transcript, make_record):
        # Cross-process invariant: the sentinel file is how subsequent batch
        # subprocesses inherit the exhausted-quota state.
        class FakeModels:
            def generate_content(self, **kwargs):
                raise RuntimeError("429 RESOURCE_EXHAUSTED: daily quota")

        class FakeClient:
            models = FakeModels()

        monkeypatch.setattr(analyzer, "_USE_CLAUDE", False)
        first_pass = make_record(fcr_indicator=None)
        result = gap_fill_transcript(FakeClient(), "sp", make_transcript(), first_pass)
        assert result is first_pass
        assert analyzer._gemini_quota_breaker.sentinel_path.exists()
        assert analyzer._gemini_quota_breaker.tripped is True

    def test_claude_429_does_not_write_sentinel(self, monkeypatch, make_transcript, make_record):
        def rate_limited(client, sp, msg, max_tokens):
            raise RuntimeError("429 rate_limit_error")

        monkeypatch.setattr(analyzer, "_USE_CLAUDE", True)
        monkeypatch.setattr(analyzer, "_call_claude", rate_limited)
        first_pass = make_record(fcr_indicator=None)
        result = gap_fill_transcript(None, "sp", make_transcript(), first_pass)
        assert result is first_pass
        # Claude 429 is a transient per-minute limit, not a daily quota
        assert not analyzer._gemini_quota_breaker.sentinel_path.exists()
        assert analyzer._gemini_quota_breaker.tripped is False
