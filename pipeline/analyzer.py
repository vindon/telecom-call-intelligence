"""
analyzer.py  —  Node 3: Analyze
---------------------------------
Sends each transcript to Llama 3.3 70B via Groq and extracts structured JSON.

Production features
-------------------
  Token tracking   : _prompt_tokens / _completion_tokens / _total_tokens injected
                     into every result dict from response.usage.
  Checkpoint saves : Each successful result is appended to
                     outputs/.checkpoint_{key}.jsonl immediately after the call.
                     On restart with the same key, completed calls are skipped,
                     so a killed process loses no work.
  Structured logs  : INFO → stdout, DEBUG → outputs/pipeline.log.
  Backoff          : Exponential on RateLimitError; linear on APIStatusError.

Groq free tier limits (as of 2025-Q2):
  30 requests / minute  ·  14,400 requests / day
  A 2 s inter-call delay keeps throughput at ~25 req/min — safely under the cap.
"""

import json
import os
import time
from pathlib import Path

from groq import Groq, RateLimitError, APIStatusError
from tqdm import tqdm

from pipeline.logger import get_logger

log = get_logger(__name__)

PROMPT_PATH    = Path(__file__).parent.parent / "prompts" / "system_prompt.txt"
CHECKPOINT_DIR = Path("outputs")
MODEL          = "llama-3.3-70b-versatile"
MAX_TOKENS     = 2048
TEMPERATURE    = 0.1   # Low → consistent, deterministic JSON across calls


# ── System prompt ─────────────────────────────────────────────────────

def load_system_prompt() -> str:
    with open(PROMPT_PATH, encoding="utf-8") as f:
        return f.read().strip()


# ── Helpers ───────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """Remove ```json ... ``` fences if the model wraps its output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        inner = lines[1:] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner).rstrip("`").strip()
    return text


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
    """
    Load persisted results for a batch key.

    Returns:
        (results, done_call_ids) — safe to call even if no checkpoint exists.
    """
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
    client: Groq,
    transcript: dict,
    system_prompt: str,
    max_retries: int = 3,
) -> dict | None:
    """
    Analyze a single transcript via Groq (Llama 3.3 70B).

    Injects _prompt_tokens / _completion_tokens / _total_tokens from
    response.usage into the returned dict.

    Returns:
        Parsed JSON result dict, or None on permanent failure.
    """
    call_id_short = transcript["call_id"][:12]

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": _build_user_message(transcript)},
                ],
            )

            raw     = response.choices[0].message.content
            cleaned = _strip_fences(raw)
            result  = json.loads(cleaned)

            # Inject Groq token usage
            if response.usage:
                result["_prompt_tokens"]     = response.usage.prompt_tokens
                result["_completion_tokens"] = response.usage.completion_tokens
                result["_total_tokens"]      = response.usage.total_tokens
                log.debug(
                    "OK  %s  prompt=%d  completion=%d  total=%d",
                    call_id_short,
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                    response.usage.total_tokens,
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

        except RateLimitError:
            wait = 30 * (2 ** attempt)
            log.warning(
                "Rate limit hit (Groq). Waiting %ds before retry %d/%d …",
                wait, attempt + 1, max_retries,
            )
            time.sleep(wait)

        except APIStatusError as exc:
            log.warning(
                "API error [%s] attempt %d/%d: HTTP %d",
                call_id_short, attempt + 1, max_retries, exc.status_code,
            )
            if attempt == max_retries - 1:
                return None
            time.sleep(5 * (attempt + 1))

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
    Sequentially analyze all transcripts via the Groq free tier.

    Checkpoint / resume behavior
    ----------------------------
    If `checkpoint_key` is non-empty:
      - On first run: results are appended to outputs/.checkpoint_{key}.jsonl
        after each successful call.
      - On restart: completed calls are loaded from disk and skipped, so only
        the remaining transcripts are sent to the API.
      - On clean completion (zero failures): the checkpoint file is deleted.
      - On partial failure: the checkpoint is kept so a retry skips successes.

    Args:
        transcripts:       Transcript dicts from hf_loader.load_telecom_transcripts()
        inter_call_delay:  Seconds between Groq calls (default 2.0 keeps rate ≤25 req/min)
        checkpoint_key:    Unique identifier for this batch (e.g. "batch_1_n20_seed42")

    Returns:
        List of result dicts (all batches combined if resuming).
        Each result includes _prompt_tokens / _completion_tokens / _total_tokens.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY not set. Check your .env file.")

    client        = Groq(api_key=api_key)
    system_prompt = load_system_prompt()

    # ── Resume from checkpoint ───────────────────────────────────────
    results:    list[dict] = []
    failed_ids: list[str]  = []
    done_ids:   set[str]   = set()

    if checkpoint_key:
        resumed, done_ids = load_checkpoint(checkpoint_key)
        if resumed:
            log.info(
                "Resuming from checkpoint '%s': %d calls already completed",
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

    print(f"\nAnalyzing {len(remaining)} transcripts with {MODEL} via Groq ...")
    if skipped:
        print(f"  ↩ Resuming checkpoint '{checkpoint_key}' — {skipped} calls already done")
    print(
        f"Free tier: 30 req/min · {inter_call_delay}s delay · "
        f"Est. {len(remaining) * (inter_call_delay + 4) / 60:.1f} min total\n"
    )

    with tqdm(total=len(remaining), desc="Calls analyzed", unit="call") as pbar:
        for i, transcript in enumerate(remaining):
            result = analyze_transcript(client, transcript, system_prompt)

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

    # ── Clean up checkpoint on clean completion ──────────────────────
    if checkpoint_key and not failed_ids:
        ckpt = checkpoint_path(checkpoint_key)
        if ckpt.exists():
            ckpt.unlink()
            log.debug("Checkpoint deleted (clean run): %s", ckpt)

    return results
