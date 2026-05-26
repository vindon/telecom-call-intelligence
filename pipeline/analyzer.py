"""
analyzer.py  —  Node 3: Analyze
---------------------------------
Sends each transcript to Gemini 2.5 Flash Lite via Google AI Studio and extracts
structured JSON using the 70-field system prompt.

Why Gemini 2.5 Flash Lite
--------------------
  • Native JSON mode (response_mime_type="application/json") guarantees valid JSON
    output — no markdown fence stripping, no parse retries for format errors.
  • 1,500 req/day · 15 RPM free tier — far more headroom than alternatives.
  • 1M-token context window — handles the longest transcripts without truncation.
  • Uses the current google-genai SDK (google-generativeai is deprecated).

Production features
-------------------
  Token tracking   : _prompt_tokens / _completion_tokens / _total_tokens from
                     response.usage_metadata injected into every result dict.
  Checkpoint saves : Each successful result appended to
                     outputs/.checkpoint_{key}.jsonl immediately after the call.
  Structured logs  : INFO → stdout, DEBUG → outputs/pipeline.log.
  Backoff          : Exponential on 429 ResourceExhausted (rate limit).
"""

import json
import os
import time
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from tqdm import tqdm

from pipeline.config import (
    EXTRACTION_MODEL as MODEL,
)
from pipeline.config import (
    EXTRACTION_TEMPERATURE as TEMPERATURE,
)
from pipeline.config import (
    MAX_CONCURRENT_EXTRACTIONS,
    MAX_RESPONSE_BYTES,
    PROMPT_PATH,
)
from pipeline.config import (
    MAX_OUTPUT_TOKENS as MAX_TOKENS,
)
from pipeline.config import (
    OUTPUT_DIR as CHECKPOINT_DIR,
)
from pipeline.logger import get_logger
from pipeline.security import (
    GEMINI_RATE_LIMITER,
    INPUT_SANITIZER,
    OUTPUT_SANITIZER,
    SECRET_GUARD,
)

log = get_logger(__name__)


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


# ── Core analysis ─────────────────────────────────────────────────────

def analyze_transcript(
    client: genai.Client,
    system_prompt: str,
    transcript: dict,
    max_retries: int = 3,
) -> dict | None:
    """
    Analyze a single transcript via Gemini 2.5 Flash Lite.

    Native JSON mode guarantees valid JSON responses.
    Injects _prompt_tokens / _completion_tokens / _total_tokens from
    response.usage_metadata into the returned dict.

    Returns:
        Parsed result dict, or None on permanent failure.
    """
    call_id_short = transcript["call_id"][:12]

    # Sanitize input before it reaches the LLM
    transcript = INPUT_SANITIZER.sanitize_transcript(transcript)

    for attempt in range(max_retries):
        try:
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

            # Guard against response bombs and secret leakage before parsing
            SECRET_GUARD.assert_no_secrets_in_output(response.text)
            OUTPUT_SANITIZER.check_response_size(response.text, limit=MAX_RESPONSE_BYTES)

            result = json.loads(response.text)
            result  = OUTPUT_SANITIZER.sanitize_extraction_result(result)

            # Inject token usage
            if response.usage_metadata:
                result["_prompt_tokens"]     = response.usage_metadata.prompt_token_count
                result["_completion_tokens"] = response.usage_metadata.candidates_token_count
                result["_total_tokens"]      = response.usage_metadata.total_token_count
                log.debug(
                    "OK  %s  prompt=%d  completion=%d  total=%d",
                    call_id_short,
                    response.usage_metadata.prompt_token_count,
                    response.usage_metadata.candidates_token_count,
                    response.usage_metadata.total_token_count,
                )

            return result

        except json.JSONDecodeError as exc:
            log.warning(
                "JSON parse error [%s] attempt %d/%d: %s",
                call_id_short, attempt + 1, max_retries, exc,
            )
            if attempt == max_retries - 1:
                return None
            time.sleep(2)

        except genai_errors.ClientError as exc:
            if exc.code == 429:
                wait = 30 * (2 ** attempt)
                log.warning(
                    "Rate limit (Google AI Studio). Waiting %ds before retry %d/%d — %s",
                    wait, attempt + 1, max_retries, str(exc.message)[:120],
                )
                time.sleep(wait)
            else:
                log.warning(
                    "Client error [%s] attempt %d/%d: HTTP %d — %s",
                    call_id_short, attempt + 1, max_retries,
                    exc.code, str(exc.message)[:120],
                )
                if attempt == max_retries - 1:
                    return None
                time.sleep(5 * (attempt + 1))

        except genai_errors.ServerError as exc:
            wait = 10 * (attempt + 1)
            log.warning(
                "Server error [%s] attempt %d/%d: HTTP %d. Waiting %ds …",
                call_id_short, attempt + 1, max_retries, exc.code, wait,
            )
            if attempt == max_retries - 1:
                return None
            time.sleep(wait)

        except Exception as exc:
            log.exception(
                "Unexpected error [%s] attempt %d/%d: %s",
                call_id_short, attempt + 1, max_retries, exc,
            )
            if attempt == max_retries - 1:
                return None
            time.sleep(3)

    return None


# ── ReAct: targeted gap-fill call ────────────────────────────────────

# Fields whose absence meaningfully degrades downstream KPI quality
_CRITICAL_FIELDS: list[str] = [
    "issue_category",
    "fcr",
    "resolution_status",
    "customer_sentiment_start",
    "customer_sentiment_end",
    "total_duration_seconds",
    "all_issues_resolved",
]


def score_field_coverage(result: dict) -> int:
    """
    Return a 0–100 field-coverage score: percentage of critical fields
    that are non-null in `result`. Used as the ReAct 'Observe' step.
    """
    if not result:
        return 0
    present = sum(1 for f in _CRITICAL_FIELDS if result.get(f) not in (None, "", 0))
    return round(present / len(_CRITICAL_FIELDS) * 100)


def gap_fill_transcript(
    client: genai.Client,
    system_prompt: str,
    transcript: dict,
    first_pass: dict,
) -> dict:
    """
    ReAct 'Act (retry)' step: identify missing critical fields from the
    first pass and make a targeted second call to fill them in.
    Returns a merged dict (first_pass values preserved where retry returns null).
    """
    missing = [f for f in _CRITICAL_FIELDS if first_pass.get(f) in (None, "", 0)]
    if not missing:
        return first_pass

    call_id_short = transcript.get("call_id", "?")[:12]
    log.info("[ReAct] call %s: gap-fill for %d missing fields: %s",
             call_id_short, len(missing), missing)

    try:
        GEMINI_RATE_LIMITER.acquire()
        response = client.models.generate_content(
            model=MODEL,
            contents=_build_gap_fill_message(transcript, missing),
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=TEMPERATURE,
                max_output_tokens=1024,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        SECRET_GUARD.assert_no_secrets_in_output(response.text)
        retry_result = json.loads(response.text)
        retry_result = OUTPUT_SANITIZER.sanitize_extraction_result(retry_result)

        # Merge: only fill nulls — never overwrite good values from first pass
        merged = dict(first_pass)
        for field, val in retry_result.items():
            if merged.get(field) in (None, "", 0) and val not in (None, "", 0):
                merged[field] = val
        log.info("[ReAct] call %s: gap-fill improved coverage %d → %d",
                 call_id_short, score_field_coverage(first_pass), score_field_coverage(merged))
        return merged

    except Exception as exc:
        log.warning("[ReAct] gap-fill failed for call %s: %s", call_id_short, str(exc)[:120])
        return first_pass


# ── Batch orchestration ───────────────────────────────────────────────

def analyze_batch(
    transcripts: list[dict],
    inter_call_delay: float = 2.0,
    checkpoint_key: str = "",
) -> list[dict]:
    """
    Sequentially analyze all transcripts via Gemini 2.5 Flash Lite.

    Gemini free tier: 15 RPM · 1,500 req/day · 1M TPM
    Default 2s delay → ~25 req/min, safely within the free tier.

    Args:
        transcripts:       Transcript dicts from hf_loader.load_telecom_transcripts()
        inter_call_delay:  Seconds between API calls (default 2.0)
        checkpoint_key:    Unique identifier for checkpoint file

    Returns:
        List of result dicts including _prompt_tokens / _completion_tokens / _total_tokens.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise OSError("GEMINI_API_KEY not set. Check your .env file.")

    client        = genai.Client(api_key=api_key)
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

    print(f"\nAnalyzing {len(remaining)} transcripts with {MODEL} via Google AI Studio ...")
    if skipped:
        print(f"  ↩ Resuming checkpoint '{checkpoint_key}' — {skipped} calls already done")
    print(
        f"Free tier: 15 RPM · {inter_call_delay}s delay · "
        f"Est. {len(remaining) * (inter_call_delay + 3) / 60:.1f} min total\n"
    )

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
