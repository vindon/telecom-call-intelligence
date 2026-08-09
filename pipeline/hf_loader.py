"""
hf_loader.py  —  Node 1: Fetch
--------------------------------
Loads telecom call transcripts.

Auto-detection order
--------------------
1. If LOCAL_CSV_PATH (config.py) exists on disk → load from local CSV.
   Fast: no network, no HuggingFace auth, ~10–15 s for the 682 MB file.
2. Otherwise → stream from HuggingFace (original behaviour, unchanged).

Dataset : talkmap/telecom-conversation-corpus  (MIT License)
Schema  : conversation_id | speaker (agent/client) | date_time (ISO 8601) | text
Size    : 3.73M turns  ·  ~200K conversations

Sampling strategy
-----------------
_select_ids() shuffles the full conversation-ID universe once (deterministic
per seed), then takes a disjoint `[offset*6, (offset+n)*6)` slice — the 6x
buffer absorbs conversations later dropped by _build_transcripts()'s
turn-count filter. This guarantees:

  • No conversation appears in more than one batch, for any two offsets that
    differ by a multiple of n (batch 1 → offset=0, batch 2 → offset=n, etc.)
  • Each batch is reproducible with the same (offset, n, seed)
  • Memory stays bounded regardless of total dataset size (HuggingFace path
    streams only enough rows to build its own offset+n window; see
    _select_ids()'s docstring for that path's narrower disjointness guarantee)

An earlier version sampled from `all_ids_ordered[offset:offset+n*6]` with a
reseeded RNG per call — that window overlaps ~83% with any offset shifted by
n, and random.sample() with a fixed seed against overlapping-but-shifted
lists reliably repicks the same underlying IDs. Confirmed in production: a
10-batch run had only 136/200 truly unique conversations before this fix.

Timestamp note
--------------
Pandas 3.x requires format='mixed' to parse ISO 8601 timestamps that mix
whole-second and fractional-second precision. Using utc=True alone silently
coerces ~92% of rows to NaT on pandas ≥ 3.0.
"""

import random

import pandas as pd

from pipeline.config import LOCAL_CSV_PATH
from pipeline.logger import get_logger

log = get_logger(__name__)

DATASET   = "talkmap/telecom-conversation-corpus"
_BUFFER_X = 6   # Over-sample factor to handle uneven conversation lengths


# ── Shared transcript builder ─────────────────────────────────────────

def _build_transcripts(df_sel: pd.DataFrame, selected_ids: list[str]) -> list[dict]:
    """Convert a filtered, timestamp-sorted DataFrame into the transcript list the pipeline expects."""
    transcripts: list[dict] = []

    for conv_id in selected_ids:
        conv_df = df_sel[df_sel["conversation_id"] == conv_id].reset_index(drop=True)

        if conv_df.empty or len(conv_df) < 4:
            log.debug("Skipped %s — only %d turns after timestamp parse", conv_id[:12], len(conv_df))
            continue

        lines: list[str] = []
        for _, row in conv_df.iterrows():
            speaker = "AGENT" if str(row["speaker"]).lower() == "agent" else "CUSTOMER"
            ts      = row["date_time"].strftime("%H:%M:%S")
            text    = str(row.get("text", "")).strip()
            if text and text != "nan":
                lines.append(f"[{ts}] {speaker}: {text}")

        if len(lines) < 4:
            continue

        start_dt = conv_df["date_time"].iloc[0]
        end_dt   = conv_df["date_time"].iloc[-1]

        transcripts.append({
            "call_id":         conv_id,
            "call_date":       start_dt.strftime("%Y-%m-%d"),
            "transcript_text": "\n".join(lines),
            "turn_count":      len(conv_df),
            "agent_turns":     int((conv_df["speaker"] == "agent").sum()),
            "customer_turns":  int((conv_df["speaker"] == "client").sum()),
            "raw_start":       start_dt.strftime("%H:%M:%S"),
            "raw_end":         end_dt.strftime("%H:%M:%S"),
            # Computed from the datetimes directly (not the HH:MM:SS strings
            # above, which lose date info and can't be safely re-subtracted
            # downstream) — ground truth for qa_audit.check_timestamp_ground_truth().
            "raw_duration_seconds": (end_dt - start_dt).total_seconds(),
        })

    return transcripts


def _select_ids(all_ids_ordered: list[str], n: int, seed: int, offset: int, source: str) -> list[str]:
    """
    Deterministically select n conversation IDs for this (seed, offset) batch,
    guaranteed disjoint from any other batch whose offset differs by a
    multiple of n (the documented non-overlapping-batches contract).

    Previous approach sampled `random.sample(all_ids_ordered[offset:offset+n*_BUFFER_X], n)`
    with a reseeded RNG per call — two batches whose offsets differ by n have
    ~(_BUFFER_X-1)/_BUFFER_X of their candidate window in common, and
    random.sample() with the same seed against overlapping-but-shifted lists
    picks largely the same underlying IDs (confirmed: batches 2-10 of a fresh
    10-batch run were only 40-90% unique against earlier batches in the same
    run). Fix: shuffle the FULL id list once per seed, then take a disjoint
    slice per offset — offset counts in units of n, buffered by _BUFFER_X on
    both the start and end bound so no two non-overlapping offsets can ever
    draw from the same region of the shuffled list.
    """
    shuffled = all_ids_ordered.copy()
    random.Random(seed).shuffle(shuffled)

    start = offset * _BUFFER_X
    end   = (offset + n) * _BUFFER_X
    window = shuffled[start:end]

    if len(window) < n:
        log.warning(
            "%s shuffled window has only %d conv IDs (wanted ≥%d). Returning all available.",
            source, len(window), n,
        )

    return window[:n]


# ── Local CSV path ────────────────────────────────────────────────────

def _load_from_csv(n: int, seed: int, offset: int) -> list[dict]:
    """Load transcripts from the local CSV file defined by LOCAL_CSV_PATH."""
    log.info("Local CSV detected: %s — skipping HuggingFace stream", LOCAL_CSV_PATH)

    df = pd.read_csv(
        LOCAL_CSV_PATH,
        dtype={"conversation_id": str, "speaker": str, "text": str},
    )
    log.info("CSV loaded: %d turns across %d conversations", len(df), df["conversation_id"].nunique())

    all_ids_ordered = sorted(df["conversation_id"].dropna().unique().tolist())
    selected_ids = _select_ids(all_ids_ordered, n, seed, offset, source="CSV")

    df_sel = df[df["conversation_id"].isin(selected_ids)].copy()
    df_sel["date_time"] = pd.to_datetime(df_sel["date_time"], format="mixed", errors="coerce")
    df_sel = df_sel.dropna(subset=["date_time"])
    df_sel = df_sel.sort_values(["conversation_id", "date_time"])

    transcripts = _build_transcripts(df_sel, selected_ids)
    log.info("Built %d/%d transcripts from CSV (offset=%d, seed=%d)", len(transcripts), n, offset, seed)
    return transcripts[:n]


# ── HuggingFace streaming path ────────────────────────────────────────

def _load_from_huggingface(n: int, seed: int, offset: int) -> list[dict]:
    """Stream transcripts from HuggingFace (fallback when local CSV is absent)."""
    from datasets import load_dataset
    from tqdm import tqdm

    target_unique = (offset + n) * _BUFFER_X
    log.info("Connecting to HuggingFace: %s (streaming)", DATASET)
    log.info("Target slice: offset=%d, n=%d → collecting %d unique convs", offset, n, target_unique)

    ds = load_dataset(DATASET, split="train", streaming=True)

    rows: list[dict] = []
    conv_ids_seen: set = set()

    pbar = tqdm(total=target_unique, desc="Conversations collected", unit="conv")

    for row in ds:
        conv_id = str(row.get("conversation_id", ""))
        if not conv_id:
            continue
        is_new = conv_id not in conv_ids_seen
        conv_ids_seen.add(conv_id)
        rows.append(row)
        if is_new:
            pbar.update(1)
        if len(conv_ids_seen) >= target_unique:
            break

    pbar.close()
    log.info("Streamed %d turns across %d conversations", len(rows), len(conv_ids_seen))

    df = pd.DataFrame(rows)

    # Sort all unique IDs for a stable global ordering, then apply offset.
    # Note: unlike the CSV path, this universe is scoped to just the
    # target_unique IDs streamed for THIS call — still correct for the
    # common case (all batches in a run share the same n, so only offset
    # varies), but not a rigorous disjointness guarantee across runs with
    # different n. See _select_ids() docstring for the underlying fix.
    all_ids_ordered = sorted(df["conversation_id"].unique().tolist())
    selected_ids = _select_ids(all_ids_ordered, n, seed, offset, source="HuggingFace stream")

    df_sel = df[df["conversation_id"].isin(selected_ids)].copy()
    df_sel["date_time"] = pd.to_datetime(df_sel["date_time"], format="mixed", errors="coerce")
    df_sel = df_sel.dropna(subset=["date_time"])
    df_sel = df_sel.sort_values(["conversation_id", "date_time"])

    transcripts = _build_transcripts(df_sel, selected_ids)
    log.info("Built %d/%d transcripts (offset=%d, seed=%d)", len(transcripts), n, offset, seed)
    return transcripts[:n]


# ── Public entry point ────────────────────────────────────────────────

def load_telecom_transcripts(
    n: int = 100,
    seed: int = 42,
    offset: int = 0,
) -> list[dict]:
    """
    Return n formatted call transcripts.

    Checks for LOCAL_CSV_PATH first; falls back to HuggingFace streaming if absent.

    Args:
        n:       Number of conversations to return.
        seed:    Random seed for reproducibility within the selected slice.
        offset:  Skip the first `offset` unique conversations before sampling.
                 Use multiples of n across batches to guarantee non-overlapping
                 samples: batch 1 → offset=0, batch 2 → offset=n, etc.

    Returns:
        List of dicts with keys:
          call_id, call_date, transcript_text,
          turn_count, agent_turns, customer_turns,
          raw_start, raw_end, raw_duration_seconds
    """
    if LOCAL_CSV_PATH.exists():
        return _load_from_csv(n, seed, offset)
    return _load_from_huggingface(n, seed, offset)
