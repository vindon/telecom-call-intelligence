"""
pipeline/security.py  —  Multi-Agent Security Layer
------------------------------------------------------
Defensive guardrails protecting the pipeline against external threats,
prompt injection, secret leakage, agentic scope violations, and
runaway API consumption.

Components
----------
  InputSanitizer   — sanitize transcripts before LLM; block injection attempts
  OutputSanitizer  — validate LLM outputs; block code execution and secrets
  AgentScopeGuard  — enforce per-agent tool access control
  SecretGuard      — prevent API keys leaking through state or LLM outputs
  RateLimiter      — sliding-window rate cap for external API calls

All components are stateless singletons. Import the module-level
instances rather than instantiating your own.

Usage
-----
  from pipeline.security import (
      INPUT_SANITIZER, OUTPUT_SANITIZER,
      SCOPE_GUARD, SECRET_GUARD, GEMINI_RATE_LIMITER,
      SecurityViolation,
  )
"""

from __future__ import annotations

import collections
import re
import time
from typing import Any

from pipeline.config import MAX_FIELD_STRING_LEN, MAX_TRANSCRIPT_CHARS
from pipeline.logger import get_logger

log = get_logger(__name__)


# ── Threat patterns ───────────────────────────────────────────────────

# Prompt injection: attempts to override system instructions
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)", re.IGNORECASE),
    re.compile(r"(disregard|override|bypass)\s+(your\s+)?(instructions?|guidelines?|rules?)", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all)\s+(you|your)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?!a\s+(telecom|customer|call))", re.IGNORECASE),
    re.compile(r"</?(system|user|assistant)>", re.IGNORECASE),   # XML role injection
    re.compile(r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>"),          # Llama template injection
    re.compile(r"DAN\s*mode|jailbreak", re.IGNORECASE),
    re.compile(r"roleplay\s+as\s+", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+you\s+are\s+)?(?!a\s+(telecom|customer))", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*:", re.IGNORECASE),
]

# Secrets: API keys and credentials that must never appear in state or outputs
_SECRET_PATTERNS: list[re.Pattern] = [
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),                        # Google / Gemini key
    re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"),                    # Anthropic key
    re.compile(r"sk-[A-Za-z0-9]{20,}"),                           # OpenAI key
    re.compile(r"(?:GEMINI|GOOGLE|OPENAI|ANTHROPIC|NVIDIA)_API_KEY\s*[=:]\s*\S+", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{27,}"),  # JWT
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"(?:password|passwd|pwd)\s*[=:]\s*\S+", re.IGNORECASE),
]

# Code execution: LLM outputs that could be eval()'d or injected into shell
_CODE_EXECUTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"__import__\s*\("),
    re.compile(r"\bexec\s*\(|\beval\s*\("),
    re.compile(r"subprocess\.|os\.system\b|os\.popen\b"),
    re.compile(r"\bimport\s+(os|sys|subprocess|shutil|socket)\b"),
    re.compile(r"<script[^>]*>", re.IGNORECASE),    # XSS
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"data:text/html", re.IGNORECASE),
    re.compile(r"(?:rm|del)\s+-[rf]", re.IGNORECASE),  # destructive shell
]

# Sensitive state keys that must never appear in serialised state payloads
_SENSITIVE_STATE_KEYS: frozenset[str] = frozenset({
    "api_key", "gemini_api_key", "google_api_key",
    "anthropic_api_key", "nvidia_api_key", "langchain_api_key",
    "openai_api_key", "secret", "password", "token",
    "auth", "credential", "private_key",
})


# ── Exception ─────────────────────────────────────────────────────────

class SecurityViolation(Exception):
    """Raised when a hard security check fails and the action must be blocked."""

    def __init__(self, check: str, detail: str) -> None:
        self.check  = check
        self.detail = detail
        super().__init__(f"[SecurityViolation:{check}] {detail}")


# ── 1. Input Sanitizer ────────────────────────────────────────────────

class InputSanitizer:
    """
    Validates and sanitizes all inputs before they reach the LLM.

    Called by DataIngestionAgent and ExtractionAgent on every transcript.
    Hard failures raise SecurityViolation; soft issues are redacted and logged.
    """

    def sanitize_transcript(self, transcript: dict, max_chars: int = MAX_TRANSCRIPT_CHARS) -> dict:
        """
        Return a sanitized copy of a transcript dict.
        Applies: size limits, encoding cleanup, injection neutralisation,
        secret redaction.
        """
        text = transcript.get("transcript_text", "")

        # ── Size cap (token bomb / DoS defence) ─────────────────────
        if len(text) > max_chars:
            log.warning(
                "[InputSanitizer] call %s truncated: %d → %d chars",
                str(transcript.get("call_id", "?"))[:12], len(text), max_chars,
            )
            text = text[:max_chars] + "\n[TRUNCATED-SECURITY]"

        # ── Encoding attacks ─────────────────────────────────────────
        text = text.replace("\x00", "").replace("�", "").replace("\r\n", "\n")

        # ── Prompt injection neutralisation ─────────────────────────
        injections = self._detect_injections(text)
        if injections:
            log.warning(
                "[InputSanitizer] call %s: %d injection pattern(s) — neutralising",
                str(transcript.get("call_id", "?"))[:12], len(injections),
            )
            for pat in _INJECTION_PATTERNS:
                text = pat.sub("[FILTERED]", text)

        # ── Secret leakage in source transcript ─────────────────────
        for pat in _SECRET_PATTERNS:
            if pat.search(text):
                log.error("[InputSanitizer] Secret pattern in transcript — redacting")
                text = pat.sub("[SECRET_REDACTED]", text)

        return {**transcript, "transcript_text": text}

    def validate_state_schema(self, state: dict, required_keys: list[str]) -> None:
        """
        Raise SecurityViolation if any required state key is absent.
        Guards agents from operating on an incomplete / tampered state.
        """
        for key in required_keys:
            if key not in state:
                raise SecurityViolation(
                    "state_schema",
                    f"Required state key '{key}' is missing — possible state tampering",
                )

    def _detect_injections(self, text: str) -> list[str]:
        return [pat.pattern[:60] for pat in _INJECTION_PATTERNS if pat.search(text)]


# ── 2. Output Sanitizer ───────────────────────────────────────────────

class OutputSanitizer:
    """
    Validates and sanitizes LLM outputs before they hit downstream agents.

    Blocks code execution payloads, secret leakage, and over-sized responses.
    """

    def check_response_size(self, response_text: str, limit: int = 32_768) -> None:
        """Raise SecurityViolation if response exceeds size limit (response bomb defence)."""
        size = len(response_text.encode("utf-8"))
        if size > limit:
            raise SecurityViolation(
                "response_size",
                f"LLM response {size} bytes exceeds limit {limit} — blocking",
            )

    def sanitize_extraction_result(
        self, result: dict, max_field_len: int = MAX_FIELD_STRING_LEN
    ) -> dict:
        """
        Return a sanitized copy of an extraction result dict.
        Truncates oversized fields, removes code execution payloads,
        and redacts any secrets that leaked into the output.
        """
        if not isinstance(result, dict):
            raise SecurityViolation("output_type", "LLM output must be a JSON object")

        sanitized: dict[str, Any] = {}
        for key, value in result.items():
            if isinstance(value, str):
                # Truncate runaway fields
                if len(value) > max_field_len:
                    value = value[:max_field_len] + "...[TRUNCATED]"

                # Block code execution
                for pat in _CODE_EXECUTION_PATTERNS:
                    if pat.search(value):
                        log.error(
                            "[OutputSanitizer] Code execution in field '%s' — filtering", key
                        )
                        value = "[CONTENT_FILTERED]"
                        break

                # Redact leaked secrets
                for pat in _SECRET_PATTERNS:
                    if pat.search(value):
                        log.error("[OutputSanitizer] Secret in field '%s' — redacting", key)
                        value = "[SECRET_REDACTED]"
                        break

            sanitized[key] = value

        return sanitized

    def sanitize_insights(self, insights: dict) -> dict:
        """
        Sanitize InsightsAgent output.
        Logs (but doesn't raise on) missing structural keys — the caller's
        fallback logic handles partial results.
        """
        if not isinstance(insights, dict):
            raise SecurityViolation("output_type", "Insights output must be a JSON object")
        for key in ("executive_summary", "top_recommendations", "quick_wins", "risk_flags"):
            if key not in insights:
                log.warning("[OutputSanitizer] Missing key '%s' in insights output", key)
        return self.sanitize_extraction_result(insights)


# ── 3. Agent Scope Guard ──────────────────────────────────────────────

class AgentScopeGuard:
    """
    Enforces that each agent only calls tools within its authorised scope.

    A prompt-injected or compromised agent that tries to invoke a tool
    belonging to a different agent is blocked here before the call executes.
    """

    _ALLOWED_TOOLS: dict[str, frozenset[str]] = {
        "DataIngestionAgent":  frozenset({"fetch_transcripts"}),
        "ExtractionAgent":     frozenset({"score_extraction"}),
        "QualityAgent":        frozenset({"score_extraction"}),
        "AggregationAgent":    frozenset({"compute_kpis"}),
        "InsightsAgent":       frozenset({"generate_insights"}),
        "ExportAgent":         frozenset({"export_results"}),
    }

    def check(self, agent: str, tool: str) -> None:
        """
        Raise SecurityViolation if `agent` is not authorised to call `tool`.
        """
        allowed = self._ALLOWED_TOOLS.get(agent, frozenset())
        if tool not in allowed:
            raise SecurityViolation(
                "scope_violation",
                f"Agent '{agent}' attempted to call tool '{tool}'; "
                f"authorised scope: {sorted(allowed) or 'none'}",
            )
        log.debug("[AgentScopeGuard] %s → %s: authorised", agent, tool)

    def allowed_tools(self, agent: str) -> frozenset[str]:
        return self._ALLOWED_TOOLS.get(agent, frozenset())


# ── 4. Secret Guard ───────────────────────────────────────────────────

class SecretGuard:
    """
    Prevents API keys and credentials from leaking through state
    serialisation, log messages, or LLM outputs.
    """

    def scrub_state(self, state: dict) -> dict:
        """
        Return a log-safe copy of state with sensitive keys redacted.
        Never use the original state dict in log calls — use this instead.
        """
        return {
            k: "[REDACTED]" if k.lower() in _SENSITIVE_STATE_KEYS else v
            for k, v in state.items()
        }

    def assert_no_secrets_in_output(self, text: str) -> None:
        """
        Raise SecurityViolation if a secret pattern appears in LLM output.
        Call this on every raw LLM response before JSON parsing.
        """
        for pat in _SECRET_PATTERNS:
            if pat.search(text):
                raise SecurityViolation(
                    "secret_in_output",
                    "Secret / API-key pattern detected in LLM response — blocking downstream",
                )

    def redact_for_log(self, message: str) -> str:
        """Redact secret patterns from a string before it is written to any log."""
        result = message
        for pat in _SECRET_PATTERNS:
            result = pat.sub("[REDACTED]", result)
        return result


# ── 5. Rate Limiter ───────────────────────────────────────────────────

class RateLimiter:
    """
    Sliding-window rate limiter for external API calls.

    Prevents runaway consumption from infinite ReAct loops, bugs, or
    prompt-injection-driven tool calls.

    Thread-safe for single-threaded pipelines; add a threading.Lock
    for concurrent access patterns.
    """

    def __init__(self, max_calls: int, window_s: float) -> None:
        self.max_calls = max_calls
        self.window_s  = window_s
        self._timestamps: collections.deque[float] = collections.deque()

    def acquire(self) -> None:
        """Block until this call is within the rate window, then record it."""
        now = time.monotonic()
        # Evict expired timestamps
        while self._timestamps and self._timestamps[0] < now - self.window_s:
            self._timestamps.popleft()

        if len(self._timestamps) >= self.max_calls:
            sleep_s = self.window_s - (now - self._timestamps[0])
            if sleep_s > 0:
                log.info("[RateLimiter] Rate limit reached (%d/%d) — sleeping %.1fs",
                         len(self._timestamps), self.max_calls, sleep_s)
                time.sleep(sleep_s)

        self._timestamps.append(time.monotonic())

    @property
    def current_usage(self) -> int:
        now = time.monotonic()
        return sum(1 for t in self._timestamps if t >= now - self.window_s)


# ── Module-level singletons ───────────────────────────────────────────

INPUT_SANITIZER     = InputSanitizer()
OUTPUT_SANITIZER    = OutputSanitizer()
SCOPE_GUARD         = AgentScopeGuard()
SECRET_GUARD        = SecretGuard()

# 15 calls / 60 s matches the Gemini free-tier RPM limit.
# Raise max_calls to match your paid-tier quota.
GEMINI_RATE_LIMITER = RateLimiter(max_calls=15, window_s=60.0)

# Claude Haiku has a much higher rate limit; 50/min is a conservative safe cap.
CLAUDE_RATE_LIMITER = RateLimiter(max_calls=50, window_s=60.0)
