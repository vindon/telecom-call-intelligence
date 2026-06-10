"""
analyzer.py  —  Node 3: Analyze
---------------------------------
Extracts structured JSON from telecom call transcripts.

Provider hierarchy (set EXTRACTION_MODEL in config.py):
  1. Claude Haiku (primary)  — ANTHROPIC_API_KEY required
  2. Gemini 2.0 Flash Lite   — GEMINI_API_KEY required (fallback)

Production features
-------------------
  Token tracking   : _prompt_tokens / _completion_tokens / _total_tokens
                     injected into every result dict.
  Checkpoint saves : Each successful result appended to
                     outputs/.checkpoint_{key}.jsonl immediately after the call.
  Structured logs  : INFO → stdout, DEBUG → outputs/pipeline.log.
  Backoff          : Exponential on 429 ResourceExhausted (rate limit).
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from tqdm import tqdm

from pipeline.config import (
    EXTRACTION_MODEL as MODEL,
)
from pipeline.config import (
    EXTRACTION_TEMPERATURE as TEMPERATURE,
)
from pipeline.config import (
    MAX_OUTPUT_TOKENS as MAX_TOKENS,
)
from pipeline.config import (
    MAX_RESPONSE_BYTES,
    PROMPT_PATH,
)
from pipeline.config import (
    OUTPUT_DIR as CHECKPOINT_DIR,
)
from pipeline.logger import get_logger
from pipeline.security import (
    CLAUDE_RATE_LIMITER,
    GEMINI_RATE_LIMITER,
    INPUT_SANITIZER,
    OUTPUT_SANITIZER,
    SECRET_GUARD,
)

_USE_CLAUDE = MODEL.startswith("claude")

log = get_logger(__name__)

# Sentinel file persists the Gemini daily-quota exhaustion flag across
# subprocess boundaries (run_batches.py spawns one process per batch).
# Without this, each new subprocess resets the flag and burns more quota.
_QUOTA_SENTINEL = CHECKPOINT_DIR / ".react_quota_exhausted"

# Tripped on first Gemini 429 (daily quota); persisted via sentinel file so
# subsequent batch subprocesses inherit the exhausted state immediately.
_react_quota_exhausted: bool = _QUOTA_SENTINEL.exists()


# ── System prompt ─────────────────────────────────────────────────────

def load_system_prompt() -> str:
    with open(PROMPT_PATH, encoding="utf-8") as f:
        return f.read().strip()


# ── Message builder ───────────────────────────────────────────────────

def _build_user_message(transcript: dict) -> str:
    # The leading _cot_reasoning instruction implements Chain-of-Thought:
    # the LLM reasons through the call before committing to field values,
    # which measurably reduces extraction errors on ambiguous transcripts.
    return (
        "Analyze the following telecom customer care call transcript and extract "
        "all metadata according to your instructions.\n\n"
        "IMPORTANT: The first field in your JSON output MUST be `_cot_reasoning` — "
        "a 2-3 sentence step-by-step analysis covering: (1) the main customer issue, "
        "(2) whether it was resolved and how, (3) the customer sentiment trajectory. "
        "This reasoning MUST appear before all other fields in the JSON object.\n\n"
        "---\n\n"
        "CALL METADATA:\n"
        f"Call ID: {transcript['call_id']}\n"
        "Agent ID: null\n"
        "Customer ID: null\n"
        f"Call Date: {transcript['call_date']}\n"
        "Queue: unknown\n"
        "Channel: voice\n\n"
        "---\n\n"
        f"TRANSCRIPT:\n{transcript['transcript_text']}"
    )


def _build_gap_fill_message(transcript: dict, missing_fields: list[str]) -> str:
    """
    Targeted re-query prompt for the ReAct observe→reason step.
    Only asks for fields identified as missing or null in the first pass.
    """
    fields_str = ", ".join(f"`{f}`" for f in missing_fields)
    return (
        "The previous extraction left some fields null. Focus ONLY on extracting "
        f"the following missing fields from this transcript: {fields_str}.\n\n"
        "Output a JSON object containing ONLY those fields — nothing else.\n\n"
        "---\n\n"
        f"TRANSCRIPT:\n{transcript['transcript_text'][:8000]}"
    )


# ── Checkpoint I/O ────────────────────────────────────────────────────

def checkpoint_path(key: str) -> Path:
    return CHECKPOINT_DIR / f".checkpoint_{key}.jsonl"


def load_checkpoint(key: str) -> tuple[list[dict], set[str]]:
    path = checkpoint_path(key)
    if not path.exists():
        return [], set()
    results: list[dict] = []
    done_ids: set[str]  = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                results.append(r)
                done_ids.add(str(r.get("call_id", "")))
            except json.JSONDecodeError:
                log.warning("Corrupt checkpoint line skipped in %s", path)
    return results, done_ids


def _append_checkpoint(key: str, result: dict) -> None:
    CHECKPOINT_DIR.mkdir(exist_ok=True)
    with open(checkpoint_path(key), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(result) + "\n")


# ── Claude extraction helper ──────────────────────────────────────────

def _parse_json_text(text: str) -> dict:
    """Strip markdown fences if present, then parse JSON."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


def _call_claude(client: Any, system_prompt: str, user_message: str, max_tokens: int) -> tuple[str, int, int]:
    """Invoke Claude and return (text, input_tokens, output_tokens)."""
    CLAUDE_RATE_LIMITER.acquire()
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        temperature=TEMPERATURE,
    )
    text = response.content[0].text
    return text, response.usage.input_tokens, response.usage.output_tokens


# ── Core analysis ─────────────────────────────────────────────────────

def analyze_transcript(
    client: Any,
    system_prompt: str,
    transcript: dict,
    max_retries: int = 3,
) -> dict | None:
    """
    Analyze a single transcript via Claude Haiku (primary) or Gemini (fallback).

    Returns:
        Parsed result dict with _prompt_tokens/_completion_tokens/_total_tokens,
        or None on permanent failure.
    """
    call_id_short = transcript["call_id"][:12]
    transcript = INPUT_SANITIZER.sanitize_transcript(transcript)

    for attempt in range(max_retries):
        try:
            if _USE_CLAUDE:
                text, in_tok, out_tok = _call_claude(
                    client, system_prompt, _build_user_message(transcript), MAX_TOKENS
                )
            else:
                GEMINI_RATE_LIMITER.acquire()
                response = client.models.generate_content(
                    model=MODEL,
                    contents=_build_user_message(transcript),
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json",
                        temperature=TEMPERATURE,
                        max_output_tokens=MAX_TOKENS,
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                text = response.text
                in_tok  = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
                out_tok = response.usage_metadata.candidates_token_count if response.usage_metadata else 0

            SECRET_GUARD.assert_no_secrets_in_output(text)
            OUTPUT_SANITIZER.check_response_size(text, limit=MAX_RESPONSE_BYTES)

            result = _parse_json_text(text)
            result = OUTPUT_SANITIZER.sanitize_extraction_result(result)
            result["_prompt_tokens"]     = in_tok
            result["_completion_tokens"] = out_tok
            result["_total_tokens"]      = in_tok + out_tok
            log.debug("OK  %s  prompt=%d  completion=%d", call_id_short, in_tok, out_tok)
            return result

        except json.JSONDecodeError as exc:
            log.warning("JSON parse error [%s] attempt %d/%d: %s", call_id_short, attempt + 1, max_retries, exc)
            if attempt == max_retries - 1:
                return None
            time.sleep(2)

        except Exception as exc:
            exc_str = str(exc)
            # Rate limit handling — both Claude and Gemini signal 429
            if "429" in exc_str or "rate_limit" in exc_str.lower() or "overloaded" in exc_str.lower():
                wait = 30 * (2 ** attempt)
                log.warning("Rate limit [%s] attempt %d/%d. Waiting %ds — %s",
                            call_id_short, attempt + 1, max_retries, wait, exc_str[:120])
                time.sleep(wait)
            else:
                log.warning("Error [%s] attempt %d/%d: %s", call_id_short, attempt + 1, max_retries, exc_str[:120])
                if attempt == max_retries - 1:
                    return None
                time.sleep(5 * (attempt + 1))

    return None


# ── ReAct: targeted gap-fill call ────────────────────────────────────

# Fields whose absence meaningfully degrades downstream KPI quality.
# Names must match prompts/system_prompt.txt exactly — a field listed here
# that the schema doesn't define makes coverage unreachable and forces a
# wasted gap-fill call on every transcript.
_CRITICAL_FIELDS: list[str] = [
    "issue_1_category",
    "fcr_indicator",
    "escalation_required",
    "customer_sentiment_start",
    "customer_sentiment_end",
    "total_duration_seconds",
    "all_issues_resolved",
]


def _is_missing(value) -> bool:
    """A field is missing only if null/absent or empty string.
    False and 0 are legitimate extracted values (e.g. fcr_indicator=False)."""
    return value is None or value == ""


def score_field_coverage(result: dict) -> int:
    """
    Return a 0–100 field-coverage score: percentage of critical fields
    that are non-null in `result`. Used as the ReAct 'Observe' step.
    """
    if not result:
        return 0
    present = sum(1 for f in _CRITICAL_FIELDS if not _is_missing(result.get(f)))
    return round(present / len(_CRITICAL_FIELDS) * 100)


def gap_fill_transcript(
    client: Any,
    system_prompt: str,
    transcript: dict,
    first_pass: dict,
) -> dict:
    """
    ReAct 'Act (retry)' step: identify missing critical fields from the
    first pass and make a targeted second call to fill them in.
    Returns a merged dict (first_pass values preserved where retry returns null).
    """
    global _react_quota_exhausted

    # Circuit breaker: once quota is exhausted for the day, skip all retries
    # so remaining batches can complete their primary extraction.
    if _react_quota_exhausted:
        return first_pass

    missing = [f for f in _CRITICAL_FIELDS if _is_missing(first_pass.get(f))]
    if not missing:
        return first_pass

    call_id_short = transcript.get("call_id", "?")[:12]
    log.info("[ReAct] call %s: gap-fill for %d missing fields: %s",
             call_id_short, len(missing), missing)

    try:
        gap_msg = _build_gap_fill_message(transcript, missing)
        if _USE_CLAUDE:
            text, in_tok, out_tok = _call_claude(client, system_prompt, gap_msg, 1024)
        else:
            GEMINI_RATE_LIMITER.acquire()
            response = client.models.generate_content(
                model=MODEL,
                contents=gap_msg,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    temperature=TEMPERATURE,
                    max_output_tokens=1024,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            text = response.text
            in_tok  = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
            out_tok = response.usage_metadata.candidates_token_count if response.usage_metadata else 0

        SECRET_GUARD.assert_no_secrets_in_output(text)
        retry_result = _parse_json_text(text)
        retry_result = OUTPUT_SANITIZER.sanitize_extraction_result(retry_result)

        merged = dict(first_pass)
        for field, val in retry_result.items():
            if _is_missing(merged.get(field)) and not _is_missing(val):
                merged[field] = val
        # Gap-fill spend must count toward token totals — BudgetGuard and
        # token_summary() read these keys for cost enforcement and reporting.
        merged["_prompt_tokens"]     = merged.get("_prompt_tokens", 0) + in_tok
        merged["_completion_tokens"] = merged.get("_completion_tokens", 0) + out_tok
        merged["_total_tokens"]      = merged.get("_prompt_tokens", 0) + merged.get("_completion_tokens", 0)
        log.info("[ReAct] call %s: gap-fill improved coverage %d → %d",
                 call_id_short, score_field_coverage(first_pass), score_field_coverage(merged))
        return merged

    except Exception as exc:
        exc_str = str(exc)
        if "429" in exc_str or "rate_limit" in exc_str.lower():
            if not _USE_CLAUDE:
                # Gemini 429 = daily quota exhausted — circuit break across all batches
                _react_quota_exhausted = True
                CHECKPOINT_DIR.mkdir(exist_ok=True)
                _QUOTA_SENTINEL.touch()
                log.warning("[ReAct] Gemini quota exhausted — sentinel written; gap-fill disabled for all remaining batches.")
            else:
                # Claude 429 = transient per-minute limit — CLAUDE_RATE_LIMITER already backs off
                log.warning("[ReAct] Claude rate-limited on gap-fill for call %s — skipping this call only", call_id_short)
        else:
            log.warning("[ReAct] gap-fill failed for call %s: %s", call_id_short, exc_str[:120])
        return first_pass


# ── Batch orchestration ───────────────────────────────────────────────

def analyze_batch(
    transcripts: list[dict],
    inter_call_delay: float = 2.0,
    checkpoint_key: str = "",
) -> list[dict]:
    """
    Sequentially analyze all transcripts with the configured EXTRACTION_MODEL
    (Claude Haiku primary; Gemini fallback when EXTRACTION_MODEL is gemini-*).

    Rate limits are enforced by CLAUDE_RATE_LIMITER / GEMINI_RATE_LIMITER;
    the default 2s inter-call delay keeps Gemini runs inside the free tier.

    Args:
        transcripts:       Transcript dicts from hf_loader.load_telecom_transcripts()
        inter_call_delay:  Seconds between API calls (default 2.0)
        checkpoint_key:    Unique identifier for checkpoint file

    Returns:
        List of result dicts including _prompt_tokens / _completion_tokens / _total_tokens.
    """
    client: Any
    if _USE_CLAUDE:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise OSError("ANTHROPIC_API_KEY not set. Check your .env file.")
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
    else:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise OSError("GEMINI_API_KEY not set. Check your .env file.")
        client = genai.Client(api_key=api_key)

    system_prompt = load_system_prompt()

    # ── Resume from checkpoint ───────────────────────────────────────
    results:    list[dict] = []
    failed_ids: list[str]  = []
    done_ids:   set[str]   = set()

    if checkpoint_key:
        resumed, done_ids = load_checkpoint(checkpoint_key)
        if resumed:
            log.info(
                "Resuming checkpoint '%s': %d calls already completed",
                checkpoint_key, len(resumed),
            )
        results = resumed

    initial_count = len(results)
    remaining = [t for t in transcripts if t["call_id"] not in done_ids]
    skipped   = len(transcripts) - len(remaining)

    log.info(
        "Batch start: %d to analyze, %d skipped (checkpoint), key='%s'",
        len(remaining), skipped, checkpoint_key or "none",
    )

    provider_label = "Anthropic (Claude)" if _USE_CLAUDE else "Google AI Studio"
    print(f"\nAnalyzing {len(remaining)} transcripts with {MODEL} via {provider_label} ...")
    if skipped:
        print(f"  ↩ Resuming checkpoint '{checkpoint_key}' — {skipped} calls already done")
    print(f"Delay: {inter_call_delay}s · Est. {len(remaining) * (inter_call_delay + 3) / 60:.1f} min total\n")

    with tqdm(total=len(remaining), desc="Calls analyzed", unit="call") as pbar:
        for i, transcript in enumerate(remaining):
            result = analyze_transcript(client, system_prompt, transcript)

            if result is not None:
                result["_turn_count"]     = transcript.get("turn_count",     0)
                result["_agent_turns"]    = transcript.get("agent_turns",    0)
                result["_customer_turns"] = transcript.get("customer_turns", 0)
                results.append(result)

                if checkpoint_key:
                    _append_checkpoint(checkpoint_key, result)
            else:
                failed_ids.append(transcript["call_id"])
                log.warning("Permanent failure — call %s", transcript["call_id"][:12])

            pbar.update(1)
            pbar.set_postfix({
                "ok":   len(results) - initial_count,
                "fail": len(failed_ids),
            })

            if i < len(remaining) - 1:
                time.sleep(inter_call_delay)

    log.info(
        "Batch done: %d OK  |  %d failed  |  key='%s'",
        len(results), len(failed_ids), checkpoint_key or "none",
    )
    print(f"\n✓ Completed: {len(results)} OK  |  {len(failed_ids)} failed")
    if failed_ids:
        sample = ", ".join(fid[:12] for fid in failed_ids[:5])
        suffix = f" … (+{len(failed_ids) - 5} more)" if len(failed_ids) > 5 else ""
        print(f"  Failed IDs: {sample}{suffix}")

    if checkpoint_key and not failed_ids:
        ckpt = checkpoint_path(checkpoint_key)
        if ckpt.exists():
            ckpt.unlink()
            log.debug("Checkpoint deleted (clean run): %s", ckpt)

    return results
