"""
hf_loader.py  —  Node 1: Fetch
--------------------------------
Loads telecom call transcripts from HuggingFace.

Dataset : talkmap/telecom-conversation-corpus  (MIT License)
Schema  : conversation_id | speaker (agent/client) | date_time (ISO 8601) | text
Size    : 3.73M turns  ·  ~200K conversations

Streaming strategy
------------------
We never download the full dataset. Instead we stream rows until we have
collected (offset + n) × 6 unique conversation IDs (6× buffer handles the
uneven turn distribution), then randomly sample exactly n IDs from the
slice starting at `offset`. This guarantees:

  • No conversation appears in more than one batch
  • Each batch is reproducible with the same (offset, n, seed)
  • Memory stays bounded regardless of total dataset size

Timestamp note
--------------
Pandas 3.x requires format='mixed' to parse ISO 8601 timestamps that mix
whole-second and fractional-second precision. Using utc=True alone silently
coerces ~92% of rows to NaT on pandas ≥ 3.0.
"""

import random

import pandas as pd
from datasets import load_dataset
from tqdm import tqdm

from pipeline.logger import get_logger

log = get_logger(__name__)

DATASET   = "talkmap/telecom-conversation-corpus"
_BUFFER_X = 6   # Over-sample factor to handle uneven conversation lengths


def load_telecom_transcripts(
    n: int = 100,
    seed: int = 42,
    offset: int = 0,
) -> list[dict]:
    """
    Return n formatted call transcripts from the HuggingFace telecom corpus.

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
          raw_start, raw_end
    """
    target_unique = (offset + n) * _BUFFER_X
    log.info("Connecting to HuggingFace: %s (streaming)", DATASET)
    log.info("Target slice: offset=%d, n=%d → collecting %d unique convs", offset, n, target_unique)

    ds = load_dataset(DATASET, split="train", streaming=True)

    rows: list[dict]  = []
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

    # Sort all unique IDs to get a stable global ordering, then apply offset
    all_ids_ordered = sorted(df["conversation_id"].unique().tolist())
    slice_ids = all_ids_ordered[offset: offset + n * _BUFFER_X]

    if len(slice_ids) < n:
        log.warning("Slice has only %d conv IDs (wanted ≥%d). Returning all available.", len(slice_ids), n)

    random.seed(seed)
    selected_ids = random.sample(slice_ids, min(n, len(slice_ids)))

    df_sel = df[df["conversation_id"].isin(selected_ids)].copy()
    df_sel["date_time"] = pd.to_datetime(df_sel["date_time"], format="mixed", errors="coerce")
    df_sel = df_sel.dropna(subset=["date_time"])
    df_sel = df_sel.sort_values(["conversation_id", "date_time"])

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
            "call_id":          conv_id,
            "call_date":        start_dt.strftime("%Y-%m-%d"),
            "transcript_text":  "\n".join(lines),
            "turn_count":       len(conv_df),
            "agent_turns":      int((conv_df["speaker"] == "agent").sum()),
            "customer_turns":   int((conv_df["speaker"] == "client").sum()),
            "raw_start":        start_dt.strftime("%H:%M:%S"),
            "raw_end":          end_dt.strftime("%H:%M:%S"),
        })

    log.info("Built %d/%d transcripts (offset=%d, seed=%d)", len(transcripts), n, offset, seed)
    return transcripts[:n]
