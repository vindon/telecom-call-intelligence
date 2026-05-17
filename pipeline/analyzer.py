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
from google.genai import types
from google.genai import errors as genai_errors
from tqdm import tqdm

from pipeline.logger import get_logger

log = get_logger(__name__)

PROMPT_PATH    = Path(__file__).parent.parent / "prompts" / "system_prompt.txt"
CHECKPOINT_DIR = Path("outputs")
MODEL          = "gemini-2.5-flash-lite"
MAX_TOKENS     = 8192
TEMPERATURE    = 0.1


# ── System prompt ─────────────────────────────────────────────────────

def load_system_prompt() -> str:
    with open(PROMPT_PATH, encoding="utf-8") as f:
        return f.read().strip()


# ── Message builder ───────────────────────────────────────────────────

def _build_user_message(transcript: dict) -> str:
    return (
        "Analyze the following telecom customer care call transcript and extract "
        "all metadata according to your instructions. "
        "Output only the JSON object — no other text.\n\n"
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

    for attempt in range(max_retries):
        try:
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

            result = json.loads(response.text)

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
        raise EnvironmentError("GEMINI_API_KEY not set. Check your .env file.")

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
